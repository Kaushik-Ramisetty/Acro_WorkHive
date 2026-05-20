from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)

# ── 2FA OTP schemas ───────────────────────────────────────────────────

class LoginResponse(BaseModel):
    """Returned after successful credential check (OTP flow).
    A JWT is NOT included -- it's issued only after /verify-otp."""
    success: bool = True
    requires_2fa: bool = True
    user_id: int


class VerifyOtpRequest(BaseModel):
    user_id: int
    otp: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class OtpTokenResponse(BaseModel):
    """Returned after successful OTP verification."""
    success: bool = True
    access_token: str
    token_type: str = "bearer"


class ResendOtpRequest(BaseModel):
    user_id: int


class ResendOtpResponse(BaseModel):
    success: bool = True
    message: str



class TokenPayload(BaseModel):
    sub: str
    role: Optional[str] = None
    exp: int
    iat: int


class UserOut(BaseModel):
    id: int
    employee_code: Optional[str] = None
    email: EmailStr
    first_name: str
    last_name: Optional[str] = None
    full_name: str
    role: Optional[str] = None
    designation: Optional[str] = None
    designation_id: Optional[str] = None
    department: Optional[str] = None
    department_id: Optional[str] = None
    employment_status: str
    profile_photo_url: Optional[str] = None

    # Personal
    phone: Optional[str] = None
    secondary_phone: Optional[str] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    date_of_birth: Optional[date] = None
    date_of_joining: Optional[date] = None

    # Emergency contact
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    # Reporting line
    reporting_manager_id: Optional[int] = None
    manager_name: Optional[str] = None

    # Locale / personal (added in v2)
    location: Optional[str] = None
    nationality: Optional[str] = None
    marital_status: Optional[str] = None
    time_zone: Optional[str] = None

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: UserOut
