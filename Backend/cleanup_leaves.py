"""One-shot cleanup: wipe all leave activity from the DB.

What this deletes:
  - leave_requests          (all rows)
  - leave_audit_logs        (all rows -- reference leave_requests)
  - worked_on_leave_requests(all rows -- reference leave_requests)
  - notifications           (only the ones tied to a leave_request_id)
  - comp_off_credits        (all rows -- comp-off grants tracked separately)

What this resets:
  - leave_balances for non-comp-off types: used=0, reserved=0,
    current_balance=opening_balance.
  - leave_balances for Compensatory_leave: opening_balance=0, used=0,
    reserved=0, current_balance=0. Comp-off only accrues when manager
    grants and HR approves; never from a yearly seed.

Run from the Backend folder:

    cd Backend
    python cleanup_leaves.py
"""
import sys
sys.path.insert(0, ".")

from app.db.session import SessionLocal
from app.models import (
    LeaveRequest, LeaveAuditLog, WorkedOnLeaveRequest,
    Notification, CompOffCredit, LeaveBalance, LeaveType,
)


def main():
    print("Cleaning leave activity...")
    with SessionLocal() as db:
        n_audit  = db.query(LeaveAuditLog).delete()
        n_wol    = db.query(WorkedOnLeaveRequest).delete()
        n_notif  = (
            db.query(Notification)
            .filter(Notification.leave_request_id.is_not(None))
            .delete(synchronize_session=False)
        )
        n_co     = db.query(CompOffCredit).delete()
        n_req    = db.query(LeaveRequest).delete()

        comp_type_ids = {
            t.id for t in db.query(LeaveType).filter(LeaveType.name.ilike("%comp%")).all()
        }

        n_bal_reset = 0
        n_bal_zeroed = 0
        for b in db.query(LeaveBalance).all():
            if b.leave_type_id in comp_type_ids:
                # Comp-off: zero everything out so only grants can refill
                b.opening_balance = 0
                b.used = 0
                b.reserved = 0
                b.current_balance = 0
                n_bal_zeroed += 1
            else:
                # Other types: reset usage/reserved, restore quota
                b.used = 0
                b.reserved = 0
                b.current_balance = b.opening_balance or 0
                n_bal_reset += 1

        db.commit()

    print(f"  - leave_requests deleted          : {n_req}")
    print(f"  - leave_audit_logs deleted        : {n_audit}")
    print(f"  - worked_on_leave_requests deleted: {n_wol}")
    print(f"  - leave-tied notifications deleted: {n_notif}")
    print(f"  - comp_off_credits deleted        : {n_co}")
    print(f"  - leave_balances reset (non-comp) : {n_bal_reset}")
    print(f"  - leave_balances zeroed (comp-off): {n_bal_zeroed}")
    print()
    print("Done. The leave module now starts from a clean slate.")
    print("Comp-off balances are zero -- employees can only apply comp-off")
    print("after a manager grants and HR approves a credit.")
    print()
    print("Refresh the frontend to see the empty state.")


if __name__ == "__main__":
    main()
