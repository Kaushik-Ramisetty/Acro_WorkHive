"""PMS Excel import/export service.

Handles parsing of the Acronotics Goals workbook format and generating
.xlsx exports that mirror the same layout.
"""
from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session


# ── Filename period parser ─────────────────────────────────────────


def _parse_period_from_filename(filename: str) -> Optional[str]:
    """Extract a year/FY period from a filename like 'Acronotics_Goals-2026_...' ."""
    # Try FY-style first: FY2026, FY2025-26, FY 2026
    m = re.search(r"FY\s*(\d{4}(?:-\d{2,4})?)", filename, re.IGNORECASE)
    if m:
        return m.group(0).replace(" ", "").upper()
    # Bare four-digit year
    m = re.search(r"(20\d{2})", filename)
    if m:
        return m.group(1)
    return None


# ── Workbook parser ────────────────────────────────────────────────


def _cell_float(cell) -> float:
    """Safely coerce a cell value to float, returning 0.0 on failure."""
    v = cell.value
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _is_blank_row(row) -> bool:
    return all(c.value is None or str(c.value).strip() == "" for c in row)


def _resolve_designation(db: Optional[Session], name: str) -> Optional[str]:
    """Case-insensitive lookup of a Designation row by title."""
    if db is None:
        return None
    try:
        from app.models.designation import Designation
        row = (
            db.query(Designation)
            .filter(Designation.title.ilike(name.strip()))
            .first()
        )
        return row.id if row else None
    except Exception:
        return None


def _is_kra_row(cell) -> bool:
    """Return True if the cell appears to be bold (KRA category row)."""
    try:
        return bool(cell.font and cell.font.bold)
    except Exception:
        return False


def _parse_single_designation_sheet(
    ws,
    period: Optional[str],
    db: Optional[Session],
    warnings: List[str],
    filename: str,
) -> Optional[dict]:
    """Parse a worksheet that has ONE designation column (B) — the export format.

    Layout:
      Row 1: | blank | DesignationName |
      Row 2: | KRA Title | weightage |
      Row 3: | KPI Title | weightage |
      ...
      blank row between KRA sections
      Competencies section: header row "Competencies" / "COMPETENCIES"
        | Competency Title | weightage |

    Returns a designation dict or None if the sheet is empty / not a goals sheet.
    """
    rows = list(ws.iter_rows())
    if len(rows) < 2:
        return None

    header_row = rows[0]
    if len(header_row) < 2:
        return None

    # Column B in header must be the designation name
    desig_name_cell = header_row[1]
    desig_name = str(desig_name_cell.value or "").strip()
    if not desig_name or re.match(r"^overall", desig_name, re.IGNORECASE):
        return None

    designation_id = _resolve_designation(db, desig_name)
    if designation_id is None:
        warnings.append(
            f"Sheet '{ws.title}': Designation '{desig_name}' not found in DB — "
            "template will be created without designation_id."
        )

    kras: List[dict] = []
    competencies: List[dict] = []
    current_kra: Optional[dict] = None
    kra_sort_order = 0
    in_competency_section = False

    for ri, row in enumerate(rows[1:], start=1):
        if not row or len(row) == 0:
            current_kra = None
            continue

        col_a_val = row[0].value
        col_a_str = str(col_a_val or "").strip()

        if not col_a_str:
            # Blank label — separator between sections
            current_kra = None
            continue

        # Overall row — skip
        if re.match(r"^overall", col_a_str, re.IGNORECASE):
            continue

        # Detect competency section header
        if re.match(r"^competenc", col_a_str, re.IGNORECASE) and (
            len(row) < 2 or row[1].value is None or _cell_float(row[1]) == 0.0
        ):
            in_competency_section = True
            current_kra = None
            continue

        weightage_val = _cell_float(row[1]) if len(row) >= 2 else 0.0
        weightage = round(weightage_val * 100, 2) if weightage_val <= 1.0 else round(weightage_val, 2)

        if in_competency_section:
            if weightage > 0 or True:  # include all competencies regardless of weight
                competencies.append({
                    "title": col_a_str,
                    "description": None,
                    "weightage": weightage,
                })
            continue

        # Determine if this is a KRA row: bold formatting OR preceded by a blank row
        is_kra = _is_kra_row(row[0])
        if not is_kra:
            # Fall back to blank-row heuristic
            prev_row = rows[ri - 1] if ri > 0 else None
            is_kra = (prev_row is None or _is_blank_row(prev_row))

        if is_kra:
            kra_sort_order += 1
            current_kra = {
                "title": col_a_str,
                "description": None,
                "weightage": weightage,
                "sort_order": kra_sort_order,
                "kpis": [],
            }
            kras.append(current_kra)
        else:
            # KPI row
            if weightage > 0 or col_a_str:
                if current_kra is None:
                    # KPI without a KRA — create implicit "General" KRA
                    kra_sort_order += 1
                    current_kra = {
                        "title": "General",
                        "description": None,
                        "weightage": 0.0,
                        "sort_order": kra_sort_order,
                        "kpis": [],
                    }
                    kras.append(current_kra)
                current_kra["kpis"].append({
                    "title": col_a_str,
                    "description": None,
                    "weightage": weightage,
                })

    # Drop KRAs with no KPIs and weightage 0 (likely header artefacts)
    kras = [k for k in kras if k["kpis"] or k["weightage"] > 0]
    if not kras and not competencies:
        return None

    return {
        "designation_name": desig_name,
        "designation_id": designation_id,
        "kras": kras,
        "competencies": competencies,
    }


def _parse_multi_designation_sheet(
    ws,
    period: Optional[str],
    db: Optional[Session],
    warnings: List[str],
) -> List[dict]:
    """Parse a worksheet where Row 1 = header with multiple designation columns.

    Layout:
      Row 1: | blank | Desig1 | Desig2 | ...
      Row 2: | KRA Title | 0.40 | 0.35 | ...
      Row 3: | KPI Title | 0.10 | 0.08 | ...
      blank row between KRAs
      Competencies section header: "Competencies" in col A
        | Comp Title | 0.xx | 0.xx | ...

    Returns a list of designation dicts.
    """
    rows = list(ws.iter_rows())
    if not rows:
        return []

    # Header row: detect designation columns (B onward, non-empty)
    header_row = rows[0]
    designation_cols: List[Tuple[int, str]] = []
    for ci, cell in enumerate(header_row):
        if ci == 0:
            continue
        v = cell.value
        if v is not None and str(v).strip() and not re.match(r"^overall", str(v).strip(), re.IGNORECASE):
            designation_cols.append((ci, str(v).strip()))

    if not designation_cols:
        return []

    # Initialize accumulators
    desig_data: Dict[int, dict] = {}
    for ci, dname in designation_cols:
        did = _resolve_designation(db, dname)
        if did is None:
            warnings.append(
                f"Designation '{dname}' not found in DB — template will be created without designation_id."
            )
        desig_data[ci] = {
            "designation_name": dname,
            "designation_id": did,
            "kras": [],
            "competencies": [],
        }

    current_kra: Dict[int, Optional[dict]] = {ci: None for ci, _ in designation_cols}
    kra_sort_order = 0
    in_competency_section = False

    for ri, row in enumerate(rows[1:], start=1):
        if _is_blank_row(row):
            for ci, _ in designation_cols:
                current_kra[ci] = None
            continue

        col_a_val = row[0].value
        col_a_str = str(col_a_val or "").strip()

        if not col_a_str:
            for ci, _ in designation_cols:
                current_kra[ci] = None
            continue

        if re.match(r"^overall", col_a_str, re.IGNORECASE):
            continue

        # Detect competency section header
        all_weights_zero = all(
            (_cell_float(row[ci]) if ci < len(row) else 0.0) == 0.0
            for ci, _ in designation_cols
        )
        if re.match(r"^competenc", col_a_str, re.IGNORECASE) and all_weights_zero:
            in_competency_section = True
            for ci, _ in designation_cols:
                current_kra[ci] = None
            continue

        if in_competency_section:
            for ci, _ in designation_cols:
                w = _cell_float(row[ci]) if ci < len(row) else 0.0
                weightage = round(w * 100, 2) if w <= 1.0 else round(w, 2)
                desig_data[ci]["competencies"].append({
                    "title": col_a_str,
                    "description": None,
                    "weightage": weightage,
                })
            continue

        # Determine if this is a KRA row: bold OR previous row blank
        any_bold = any(_is_kra_row(row[0]) for _ in [1])  # single check
        prev_blank = _is_blank_row(rows[ri - 1]) if ri > 1 else True
        is_category = any_bold or prev_blank

        if is_category:
            kra_sort_order += 1
            for ci, _ in designation_cols:
                w = _cell_float(row[ci]) if ci < len(row) else 0.0
                weightage = round(w * 100, 2) if w <= 1.0 else round(w, 2)
                kra_dict = {
                    "title": col_a_str,
                    "description": None,
                    "weightage": weightage,
                    "sort_order": kra_sort_order,
                    "kpis": [],
                }
                current_kra[ci] = kra_dict
                if weightage > 0 or not any_bold:
                    desig_data[ci]["kras"].append(kra_dict)
        else:
            # KPI row
            for ci, _ in designation_cols:
                w = _cell_float(row[ci]) if ci < len(row) else 0.0
                weightage = round(w * 100, 2) if w <= 1.0 else round(w, 2)
                if weightage <= 0:
                    continue
                kra = current_kra.get(ci)
                if kra is None:
                    kra_sort_order += 1
                    kra = {
                        "title": "General",
                        "description": None,
                        "weightage": 0.0,
                        "sort_order": kra_sort_order,
                        "kpis": [],
                    }
                    current_kra[ci] = kra
                    desig_data[ci]["kras"].append(kra)
                kra["kpis"].append({
                    "title": col_a_str,
                    "description": None,
                    "weightage": weightage,
                })

    return [v for v in desig_data.values() if v["kras"] or v["competencies"]]


def _validate_parsed_templates(designations: List[dict]) -> List[str]:
    """Return a list of validation error messages for the parsed templates."""
    errors: List[str] = []
    seen_names: set = set()
    for d in designations:
        name = d.get("designation_name") or d.get("name") or "(unnamed)"
        if name in seen_names:
            errors.append(f"Duplicate template for designation '{name}'.")
        seen_names.add(name)

        kras = d.get("kras") or []
        if not kras:
            errors.append(f"Designation '{name}': No KRAs found.")
            continue

        total_kra_weight = sum(k.get("weightage", 0) for k in kras)
        if total_kra_weight > 0 and not (95.0 <= total_kra_weight <= 105.0):
            errors.append(
                f"Designation '{name}': KRA weightages sum to {total_kra_weight:.1f}% (expected ~100%)."
            )

        seen_kra_titles: set = set()
        for kra in kras:
            kra_title = kra.get("title", "")
            if kra_title in seen_kra_titles:
                errors.append(f"Designation '{name}': Duplicate KRA title '{kra_title}'.")
            seen_kra_titles.add(kra_title)

            kpis = kra.get("kpis") or []
            seen_kpi_titles: set = set()
            for kpi in kpis:
                kpi_title = kpi.get("title", "")
                if kpi_title in seen_kpi_titles:
                    errors.append(
                        f"Designation '{name}', KRA '{kra_title}': Duplicate KPI '{kpi_title}'."
                    )
                seen_kpi_titles.add(kpi_title)

    return errors


def parse_goals_workbook(
    file_bytes: bytes,
    filename: str,
    db: Optional[Session] = None,
) -> dict:
    """Parse an Acronotics Goals .xlsx workbook.

    Supports two formats:
    1. Single-column format (one sheet per template, column B = designation):
       Generated by template_export. Sheet name is the designation/template name.
    2. Multi-column format (one "Goals" sheet, columns B+ = designations).

    Returns a dict matching ImportPreviewOut schema:
      {
        period, source_filename,
        designations: [{designation_name, designation_id, kras: [...], competencies: [...]}],
        warnings: [str],
      }
    Raises ValueError on critical parse errors or validation failures.
    """
    warnings: List[str] = []
    period = _parse_period_from_filename(filename)

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)

    designations: List[dict] = []

    # --- Strategy 1: Look for a "Goals" sheet (multi-column format) ---
    goals_sheet = None
    for sname in wb.sheetnames:
        if sname.strip().lower() == "goals":
            goals_sheet = wb[sname]
            break

    if goals_sheet is not None:
        ws = goals_sheet
        rows = list(ws.iter_rows())
        if not rows:
            raise ValueError("Goals sheet is empty.")

        # Check if the header row has multiple designation columns (multi-column format)
        header_row = rows[0]
        multi_col = False
        for ci, cell in enumerate(header_row[1:], start=1):
            if cell.value and str(cell.value).strip():
                multi_col = True
                break

        if multi_col:
            # Check if column B header looks like a designation vs a generic label
            b_val = str(header_row[1].value or "").strip() if len(header_row) > 1 else ""
            # If there are 2+ non-empty columns in the header, parse as multi-designation
            non_empty = [
                ci for ci, c in enumerate(header_row) if ci > 0 and c.value and str(c.value).strip()
            ]
            if len(non_empty) >= 2:
                designations = _parse_multi_designation_sheet(ws, period, db, warnings)
            else:
                # Single column — treat as single-designation sheet
                d = _parse_single_designation_sheet(ws, period, db, warnings, filename)
                if d:
                    designations = [d]
        else:
            d = _parse_single_designation_sheet(ws, period, db, warnings, filename)
            if d:
                designations = [d]

    else:
        # --- Strategy 2: No "Goals" sheet — try each worksheet as a separate template ---
        for sname in wb.sheetnames:
            ws = wb[sname]
            rows = list(ws.iter_rows())
            if not rows:
                continue
            # Check if there are multiple designation columns (multi-column per sheet)
            header_row = rows[0]
            non_empty_cols = [
                ci for ci, c in enumerate(header_row) if ci > 0 and c.value and str(c.value).strip()
            ]
            if len(non_empty_cols) >= 2:
                sheet_desigs = _parse_multi_designation_sheet(ws, period, db, warnings)
                designations.extend(sheet_desigs)
            else:
                d = _parse_single_designation_sheet(ws, period, db, warnings, filename)
                if d:
                    designations.append(d)

    if not designations:
        raise ValueError(
            "No templates could be extracted. Ensure the file has a 'Goals' sheet "
            "or individual designation sheets with KRA/KPI data."
        )

    # --- CHANGE 6: Validate before returning ---
    validation_errors = _validate_parsed_templates(designations)
    if validation_errors:
        # Surface as warnings rather than hard errors so HR can still preview and decide
        for e in validation_errors:
            warnings.append(f"[VALIDATION] {e}")

    return {
        "period": period,
        "source_filename": filename,
        "designations": designations,
        "warnings": warnings,
    }


# ── Workbook builder (export) ──────────────────────────────────────


def _slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug."""
    slug = re.sub(r"[^\w\s-]", "", text)
    slug = re.sub(r"[\s-]+", "_", slug)
    return slug.strip("_")


def build_workbook_for_template(template, db: Session) -> bytes:
    """Build a Goals .xlsx for a single GoalTemplate. Returns raw bytes."""

    # Resolve designation title
    desig_title = None
    if template.designation_id:
        try:
            from app.models.designation import Designation
            d = db.query(Designation).filter(Designation.id == template.designation_id).first()
            if d:
                desig_title = d.title
        except Exception:
            pass
    if desig_title is None:
        # Fall back: extract from template name (after " — " or " - ")
        parts = re.split(r"\s+[—\-]\s+", template.name, maxsplit=1)
        desig_title = parts[-1] if len(parts) > 1 else template.name

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Goals"

    header_font = Font(bold=True)
    category_font = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="D9E1F2")
    category_fill = PatternFill("solid", fgColor="E2EFDA")

    # Row 1: header
    ws["A1"] = ""
    ws["B1"] = desig_title
    ws["A1"].font = header_font
    ws["B1"].font = header_font
    ws["B1"].fill = header_fill

    # Set column widths
    ws.column_dimensions["A"].width = 45
    ws.column_dimensions["B"].width = 16

    current_row = 2
    kras = sorted(template.kras or [], key=lambda k: (k.sort_order, k.id))
    total_weight = 0.0

    for idx, kra in enumerate(kras):
        # Blank separator between categories (not before the first)
        if idx > 0:
            ws.cell(row=current_row, column=1).value = None
            ws.cell(row=current_row, column=2).value = None
            current_row += 1

        # Category row
        cat_cell_a = ws.cell(row=current_row, column=1, value=kra.title)
        cat_val = round(kra.weightage / 100, 4)
        cat_cell_b = ws.cell(row=current_row, column=2, value=cat_val)
        cat_cell_a.font = category_font
        cat_cell_b.font = category_font
        cat_cell_a.fill = category_fill
        cat_cell_b.fill = category_fill
        ws.cell(row=current_row, column=2).number_format = "0.00%"
        total_weight += kra.weightage
        current_row += 1

        # KPI rows
        kpis = sorted(kra.kpis or [], key=lambda p: p.id)
        for kpi in kpis:
            ws.cell(row=current_row, column=1, value=kpi.title)
            kpi_val = round(kpi.weightage / 100, 4)
            ws.cell(row=current_row, column=2, value=kpi_val)
            ws.cell(row=current_row, column=2).number_format = "0.00%"
            current_row += 1

    # Blank row before totals
    current_row += 1

    # Overall % totals row
    total_cell_a = ws.cell(row=current_row, column=1, value="Overall %")
    total_cell_b = ws.cell(row=current_row, column=2, value=round(total_weight / 100, 4))
    total_cell_a.font = header_font
    total_cell_b.font = header_font
    ws.cell(row=current_row, column=2).number_format = "0.00%"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def template_export_filename(template) -> str:
    """Generate the export filename for a template."""
    slug = _slugify(template.name)
    version = getattr(template, "template_version", 1) or 1
    return f"{slug}_v{version}.xlsx"
