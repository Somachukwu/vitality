from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sex: Mapped[str | None] = mapped_column(Enum("male", "female", "other"), nullable=True)
    height: Mapped[float | None] = mapped_column(Float, nullable=True)        # cm
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)        # kg
    daily_calorie_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goal_type: Mapped[str | None] = mapped_column(
        Enum("weight_loss", "weight_gain", "maintenance"), nullable=True
    )
    dietary_restrictions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    notification_preferences: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    vitals: Mapped[list["Vitals"]] = relationship(back_populates="user")  # noqa: F821
    meals: Mapped[list["Meal"]] = relationship(back_populates="user")  # noqa: F821
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="user")  # noqa: F821
    devices: Mapped[list["Device"]] = relationship(back_populates="user")  # noqa: F821
