import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import Employee
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    OtpTokenResponse,
    ResendOtpRequest,
    ResendOtpResponse,
    UserOut,
    VerifyOtpRequest,
)
from app.services import otp_service
from app.services.auth_service import issue_token, login_service, resend_otp_service


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_payload(db: Session, user: Employee) -> UserOut:
    manager_name = None
    if user.reporting_manager_id:
        mgr = db.get(Employee, user.reporting_manager_id)
        if mgr:
            manager_name = mgr.full_name

    return UserOut(
        id=user.id,
        employee_code=user.employee_code,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        role=user.role.name if user.role else None,
        designation=user.designation.title if user.designation else None,
        designation_id=user.designation_id,
        department=user.department.name if user.department else None,
        department_id=user.department_id,
        employment_status=user.employment_status,
        profile_photo_url=user.profile_photo_url,
        phone=user.phone,
        secondary_phone=user.secondary_phone,
        gender=user.gender,
        blood_group=user.blood_group,
        date_of_birth=user.date_of_birth,
        date_of_joining=user.date_of_joining,
        emergency_contact_name=user.emergency_contact_name,
        emergency_contact_phone=user.emergency_contact_phone,
        reporting_manager_id=user.reporting_manager_id,
        manager_name=manager_name,
        location=user.location,
        nationality=user.nationality,
        marital_status=user.marital_status,
        time_zone=user.time_zone,
    )


@router.post("/login", response_model=LoginResponse,
             summary="Step 1 of 2FA: validate credentials and trigger OTP")
async def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> LoginResponse:
    """Validate credentials. Returns user_id + requires_2fa. No JWT yet --
    the JWT is issued only after /verify-otp."""
    try:
        result = await run_in_threadpool(login_service, payload.email, payload.password, db)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Audit the credential success
    try:
        from app.tasks.activity import log_login_activity
        log_login_activity.delay(
            user_id=result["user_id"],
            email=payload.email,
            role=None,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except Exception:
        pass

    return LoginResponse(**result)


@router.post("/verify-otp", response_model=OtpTokenResponse,
             summary="Step 2 of 2FA: verify OTP and issue JWT")
async def verify_otp(
    payload: VerifyOtpRequest,
    db: Session = Depends(get_db),
) -> OtpTokenResponse:
    """Verify the 6-digit OTP and issue a JWT on success."""
    try:
        await otp_service.verify_otp(payload.user_id, payload.otp)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )

    def _fetch_user():
        return (
            db.query(Employee)
            .filter(Employee.id == payload.user_id, Employee.is_deleted.is_(False))
            .first()
        )

    user = await run_in_threadpool(_fetch_user)
    if not user or user.employment_status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or has been deactivated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = issue_token(user)
    return OtpTokenResponse(
        success=True,
        access_token=token["access_token"],
        token_type=token.get("token_type", "bearer"),
    )


@router.post("/resend-otp", response_model=ResendOtpResponse,
             summary="Re-send OTP for an in-progress 2FA flow")
async def resend_otp(
    payload: ResendOtpRequest,
    db: Session = Depends(get_db),
) -> ResendOtpResponse:
    try:
        result = await run_in_threadpool(resend_otp_service, payload.user_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return ResendOtpResponse(**result)


@router.get("/me", response_model=UserOut)
def me(current: Employee = Depends(get_current_user), db: Session = Depends(get_db)):
    return _user_payload(db, current)
