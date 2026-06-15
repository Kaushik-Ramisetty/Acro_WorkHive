"""Employee skill tags. Many rows per employee.

Sync semantics from the resource-management feature: when an admin saves
skills via PUT /admin/employee/{id}/resource-details, the service deletes
every existing row for the employee and re-inserts the new set. The unique
constraint on (employee_id, skill) is a belt-and-suspenders guard against
duplicate inserts.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EmployeeSkill(Base):
    __tablename__ = "employee_skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )
    skill: Mapped[str] = mapped_column(String(80), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    employee: Mapped["Employee"] = relationship()  # type: ignore[name-defined]

    __table_args__ = (
        UniqueConstraint("employee_id", "skill", name="uq_employee_skill"),
    )
