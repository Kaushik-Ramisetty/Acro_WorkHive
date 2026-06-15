from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Role(Base):
    """Application-level roles: 'admin', 'manager', 'employee'."""
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    employees: Mapped[list["Employee"]] = relationship(back_populates="role")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return f"<Role {self.name}>"
