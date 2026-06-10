"""One-off: reduce existing Sick Leave (LT001) balances for the current year
from the old quota (12) to the new quota (7).

Run from the Backend directory:
    python -m scripts.fix_sick_leave_quota
"""
from __future__ import annotations

from app.db.session import SessionLocal
from app.models.leave import LeaveBalance
from utils.time_utils import now_utc

NEW_QUOTA = 7
LEAVE_TYPE_ID = "LT001"


def main() -> None:
    year = now_utc().year
    db = SessionLocal()
    try:
        rows = (
            db.query(LeaveBalance)
            .filter(
                LeaveBalance.leave_type_id == LEAVE_TYPE_ID,
                LeaveBalance.year == year,
            )
            .all()
        )
        updated = 0
        for bal in rows:
            if (bal.opening_balance or 0) <= NEW_QUOTA:
                continue
            delta = (bal.opening_balance or 0) - NEW_QUOTA
            bal.opening_balance = NEW_QUOTA
            bal.current_balance = max(0, (bal.current_balance or 0) - delta)
            updated += 1
        db.commit()
        print(f"Updated {updated} LeaveBalance row(s) for {LEAVE_TYPE_ID} year={year} to quota={NEW_QUOTA}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
