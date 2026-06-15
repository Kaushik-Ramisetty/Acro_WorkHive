"""
utils/id_generator.py — Auto-generate formatted IDs for employees and candidates.

`generate_temp_password` uses the `secrets` module (CSPRNG) instead of
`random` because the output gates employee logins. `random.choices` is
predictable enough that it's not safe for credentials.
"""

import secrets
import string
from sqlalchemy.orm import Session


# def generate_employee_code(db: Session, model) -> str:
#     """
#     Generate next sequential employee code: AIN001, AIN002, …
#     Finds the current max and increments.
#     """
#     from sqlalchemy import func

#     last = db.query(func.max(model.employee_code)).scalar()
#     if last:
#         try:
#             num = int(last.replace("AIN", "").strip()) + 1
#         except ValueError:
#             num = 1
#     else:
#         num = 1
#     return f"AIN{num:04d}"

def generate_employee_code(db: Session, model) -> str:
    from sqlalchemy import func

    last = db.query(func.max(model.employee_code)).scalar()

    print("DEBUG last employee code =", last)

    if last:
        try:
            num = int(last.replace("AIN", "").strip()) + 1
        except ValueError:
            num = 1
    else:
        num = 1

    generated = f"AIN{num}"
    print("DEBUG generated code =", generated)

    return generated


def generate_candidate_ref() -> str:
    """Generate a short human-readable candidate reference: CAND-XXXXXX."""
    alphabet = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(alphabet) for _ in range(6))
    return f"CAND-{suffix}"


def generate_temp_password(length: int = 10) -> str:
    """
    Generate a cryptographically-random temporary password for newly
    activated employees. Uses `secrets.choice` (CSPRNG) — the previous
    implementation used `random.choices` which is predictable.
    """
    chars = string.ascii_letters + string.digits + "@#$!"
    return "".join(secrets.choice(chars) for _ in range(length))
