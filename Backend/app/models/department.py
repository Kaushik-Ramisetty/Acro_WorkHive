from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. DEP001
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    head_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", use_alter=True, name="fk_department_head"), nullable=True)
    parent_department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"), nullable=True)

    parent: Mapped["Department | None"] = relationship(remote_side="Department.id", foreign_keys=[parent_department_id])
    head: Mapped["Employee | None"] = relationship(foreign_keys=[head_id], post_update=True)  # type: ignore[name-defined]
    employees: Mapped[list["Employee"]] = relationship(back_populates="department", foreign_keys="Employee.department_id")  # type: ignore[name-defined]
