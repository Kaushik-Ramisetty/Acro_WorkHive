from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Optional


HTML_MAPPING_FILE = Path(__file__).resolve().parent / "app" / "designation_department_mapping.html"

OFFICIAL_DEPARTMENTS: list[dict[str, object]] = [
    {"id": "DEP002", "name": "Product",                "parent_department_id": None},
    {"id": "DEP003", "name": "HR",                     "parent_department_id": None},
    {"id": "DEP012", "name": "Sales",                  "parent_department_id": None},
    {"id": "DEP016", "name": "Operations",             "parent_department_id": None},
    {"id": "DEP017", "name": "Delivery",               "parent_department_id": None},
    {"id": "DEP018", "name": "Learning & Development", "parent_department_id": None},
    {"id": "DEP020", "name": "Management",             "parent_department_id": None},
    {"id": "DEP021", "name": "Solutioning",            "parent_department_id": None},
]

DEPARTMENT_NAME_TO_ID = {row["name"]: row["id"] for row in OFFICIAL_DEPARTMENTS}
OFFICIAL_DEPARTMENT_IDS = set(DEPARTMENT_NAME_TO_ID.values())

# Designation titles and levels remain part of the seed contract; department
# assignments are always sourced from the HTML mapping file.
OFFICIAL_DESIGNATIONS: list[dict[str, object]] = [
    {"id": "D1",  "title": "Delivery Head",                            "level": 10},
    {"id": "D2",  "title": "Delivery Manager",                         "level": 7},
    {"id": "D3",  "title": "Associate Delivery Manager",               "level": 6},
    {"id": "D4",  "title": "Developer",                                "level": 3},
    {"id": "D5",  "title": "Junior Developer",                         "level": 2},
    {"id": "D6",  "title": "Senior Developer",                         "level": 5},
    {"id": "D7",  "title": "Senior AI & Automation Solution Architect", "level": 8},
    {"id": "D8",  "title": "AI Engineer",                              "level": 4},
    {"id": "D9",  "title": "Quality Analyst",                          "level": 3},
    {"id": "D10", "title": "Senior DevOps Engineer",                   "level": 6},
    {"id": "D11", "title": "Senior Designer",                          "level": 6},
    {"id": "D12", "title": "Chief AI Officer",                         "level": 12},
    {"id": "D13", "title": "Junior Tester",                            "level": 2},
    {"id": "D14", "title": "Tester",                                   "level": 3},
    {"id": "D15", "title": "Data Analyst",                             "level": 3},
    {"id": "D16", "title": "Tableau Administrator",                    "level": 3},
    {"id": "D17", "title": "Lead Developer",                           "level": 6},
    {"id": "D18", "title": "Team Lead",                                "level": 6},
    {"id": "D19", "title": "Project Manager",                          "level": 7},
    {"id": "D20", "title": "Associate Project Manager",                "level": 6},
    {"id": "D21", "title": "Program Manager",                          "level": 8},
    {"id": "D22", "title": "Business Analyst",                         "level": 4},
    {"id": "D23", "title": "Junior Business Analyst",                  "level": 2},
    {"id": "D24", "title": "Senior Business Analyst",                  "level": 6},
    {"id": "D25", "title": "Solution Architect",                       "level": 8},
    {"id": "D26", "title": "Engagement Manager",                       "level": 7},
    {"id": "D27", "title": "Junior Solution Architect",                "level": 5},
    {"id": "D28", "title": "Senior Solution Architect",                "level": 9},
    {"id": "D29", "title": "Technical Architect",                      "level": 8},
    {"id": "D30", "title": "Junior Technical Architect",               "level": 5},
    {"id": "D31", "title": "Senior Technical Architect",               "level": 9},
    {"id": "D32", "title": "Consultant",                               "level": 4},
    {"id": "D33", "title": "Senior Consultant",                        "level": 6},
    {"id": "D34", "title": "Junior Consultant",                        "level": 2},
    {"id": "D35", "title": "Support Engineer",                         "level": 3},
    {"id": "D36", "title": "Technical Trainer",                        "level": 5},
    {"id": "D37", "title": "Senior Technical Trainer",                 "level": 6},
    {"id": "D38", "title": "Infrastructure Support Engineer",          "level": 3},
    {"id": "D39", "title": "Infrastructure Engineer",                  "level": 4},
    {"id": "D40", "title": "Senior Data Analyst",                      "level": 6},
    {"id": "D41", "title": "Data Scientist",                           "level": 5},
    {"id": "D42", "title": "Senior Data Scientist",                    "level": 6},
    {"id": "D43", "title": "Lead Data Scientist",                      "level": 7},
    {"id": "D44", "title": "Senior Data Engineer",                     "level": 6},
    {"id": "D45", "title": "Data Engineer",                            "level": 4},
    {"id": "D46", "title": "Trainee",                                  "level": 1},
    {"id": "D47", "title": "Intern",                                   "level": 1},
    {"id": "D48", "title": "Product Technical Lead",                   "level": 7},
    {"id": "D49", "title": "Product Manager",                          "level": 7},
    {"id": "D50", "title": "Product Architect",                        "level": 8},
    {"id": "D51", "title": "QA Engineer",                              "level": 3},
    {"id": "D52", "title": "DevOps Engineer",                          "level": 4},
    {"id": "D53", "title": "UI/UX Designer",                           "level": 3},
    {"id": "D54", "title": "Senior UI/UX Developer",                   "level": 6},
    {"id": "D55", "title": "AI Designer",                              "level": 4},
    {"id": "D56", "title": "Product Support Manager",                  "level": 7},
    {"id": "D57", "title": "Product Support Engineer",                 "level": 3},
    {"id": "D58", "title": "Sales Head",                               "level": 10},
    {"id": "D59", "title": "Sales Manager",                            "level": 7},
    {"id": "D60", "title": "Account Manager",                          "level": 7},
    {"id": "D61", "title": "Account Executive",                        "level": 4},
    {"id": "D62", "title": "Business Development Manager",             "level": 7},
    {"id": "D63", "title": "Manager - Partnerships & Alliances",       "level": 7},
    {"id": "D64", "title": "Head of Finance",                          "level": 9},
    {"id": "D65", "title": "Finance Manager",                          "level": 7},
    {"id": "D66", "title": "Senior Finance Executive",                 "level": 5},
    {"id": "D67", "title": "HR Head",                                  "level": 10},
    {"id": "D68", "title": "HR & Recruitment Manager",                 "level": 7},
    {"id": "D69", "title": "HR Executive",                             "level": 3},
    {"id": "D70", "title": "Recruitment Manager",                      "level": 7},
    {"id": "D71", "title": "Lead Recruiter",                           "level": 6},
    {"id": "D72", "title": "Junior Recruiter",                         "level": 2},
    {"id": "D73", "title": "Senior Recruiter",                         "level": 5},
    {"id": "D74", "title": "Recruiter",                                "level": 3},
    {"id": "D75", "title": "Talent Acquisition Specialist",            "level": 4},
    {"id": "D76", "title": "IT Manager",                               "level": 7},
    {"id": "D77", "title": "IT Admin",                                 "level": 3},
    {"id": "D78", "title": "Operations Head",                          "level": 10},
    {"id": "D79", "title": "Operations Manager",                       "level": 7},
    {"id": "D80", "title": "Admin",                                    "level": 3},
    {"id": "D81", "title": "Leadership",                               "level": 11},
    {"id": "D82", "title": "Junior Automation Developer",              "level": 2},
    {"id": "D83", "title": "Junior Technical Trainer",                 "level": 3},
    {"id": "D84", "title": "Head of Learning & Development",           "level": 9},
    {"id": "D85", "title": "Tech Lead",                                "level": 6},
    {"id": "D86", "title": "Junior QA Engineer",                       "level": 2},
    {"id": "D87", "title": "Product Delivery Manager",                 "level": 7},
    {"id": "D88", "title": "Head of Sales and Solutioning",            "level": 10},
    {"id": "D89", "title": "Associate Solution Architect",             "level": 5},
    {"id": "D90", "title": "Full Stack Developer",                     "level": 4},
    {"id": "D91", "title": "Junior Finance Executive",                 "level": 2},
    {"id": "D92", "title": "Power Platform Developer",                 "level": 4},
    {"id": "D93", "title": "Automation Edge Developer",                "level": 3},
    {"id": "D94", "title": "Scrum Master",                             "level": 6},
    {"id": "D95", "title": "Inside Sales Executive",                   "level": 3},
    {"id": "D96", "title": "Data Science Intern",                      "level": 1},
]

OFFICIAL_DESIGNATION_IDS = {row["id"] for row in OFFICIAL_DESIGNATIONS}


def _load_html_mapping() -> tuple[dict[str, str], Counter[str]]:
    if not HTML_MAPPING_FILE.is_file():
        raise FileNotFoundError(f"Missing designation mapping file: {HTML_MAPPING_FILE}")

    html = HTML_MAPPING_FILE.read_text(encoding="utf-8", errors="ignore")
    blocks = re.findall(
        r'name:\s*"([^"]+)"\s*,\s*color:\s*"[^"]+"\s*,\s*roles:\s*\[(.*?)\]\s*\}',
        html,
        flags=re.S,
    )

    title_to_department_name: dict[str, str] = {}
    department_distribution: Counter[str] = Counter()
    for department_name, roles_block in blocks:
        roles = re.findall(r'"([^"]+)"', roles_block)
        if department_name == "Solutioning":
            fixed_roles: list[str] = []
            for role in roles:
                if role == "Chief AI OfficerAI Engineer":
                    fixed_roles.append("Chief AI Officer")
                else:
                    fixed_roles.append(role)
            roles = fixed_roles

        department_distribution[department_name] = len(roles)
        for role in roles:
            if role in title_to_department_name and title_to_department_name[role] != department_name:
                raise ValueError(f"Designation '{role}' appears in multiple departments in HTML mapping.")
            title_to_department_name[role] = department_name

    if len(blocks) != 8:
        raise ValueError(f"Expected 8 departments in HTML mapping, found {len(blocks)}.")
    if len(title_to_department_name) != 96:
        raise ValueError(f"Expected 96 designations in HTML mapping, found {len(title_to_department_name)}.")

    return title_to_department_name, department_distribution


HTML_DESIGNATION_TO_DEPARTMENT_NAME, HTML_DEPARTMENT_DISTRIBUTION = _load_html_mapping()
HTML_DESIGNATION_TO_DEPARTMENT_ID = {
    title: DEPARTMENT_NAME_TO_ID[department_name]
    for title, department_name in HTML_DESIGNATION_TO_DEPARTMENT_NAME.items()
}


def normalize_department_id(value: Optional[str]) -> Optional[str]:
    clean = (str(value or "").strip() or None)
    return clean if clean in OFFICIAL_DEPARTMENT_IDS else None


def sync_master_data(session, *, overwrite_department_id: bool = True) -> None:
    """Upsert canonical master data without touching user-created records.

    Only inserts missing canonical rows and updates existing canonical rows.
    Non-canonical departments and designations (user-created) are preserved.
    """
    from app.models import Department, Designation

    for row in OFFICIAL_DEPARTMENTS:
        if session.get(Department, row["id"]) is None:
            session.add(Department(
                id=row["id"],
                name=row["name"],
                parent_department_id=row["parent_department_id"],
            ))
    session.flush()

    for row in OFFICIAL_DESIGNATIONS:
        title = row["title"]
        department_id = HTML_DESIGNATION_TO_DEPARTMENT_ID.get(title)
        if not department_id:
            raise KeyError(f"Designation '{title}' is missing from HTML mapping.")

        if session.get(Designation, row["id"]) is None:
            session.add(Designation(
                id=row["id"],
                title=title,
                level=row["level"],
                department_id=department_id,
            ))

