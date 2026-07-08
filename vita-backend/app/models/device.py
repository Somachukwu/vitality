from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    device_uid: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)  # ESP32 MAC / chip ID
    device_name: Mapped[str] = mapped_column(String(100), nullable=False, default="ESP32 Device")
    api_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    device_type: Mapped[str] = mapped_column(Enum("wearable", "station"), nullable=False, default="wearable")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="devices")  # noqa: F821
    vitals: Mapped[list["Vitals"]] = relationship(back_populates="device")  # noqa: F821
