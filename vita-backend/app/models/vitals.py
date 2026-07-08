from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Vitals(Base):
    __tablename__ = "vitals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)

    heart_rate: Mapped[float | None] = mapped_column(Float, nullable=True)    # bpm
    spo2: Mapped[float | None] = mapped_column(Float, nullable=True)          # %
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)   # °C
    humidity: Mapped[float | None] = mapped_column(Float, nullable=True)      # %
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)        # kg
    steps: Mapped[int | None] = mapped_column(Integer, nullable=True)

    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="vitals")  # noqa: F821
    device: Mapped["Device"] = relationship(back_populates="vitals")  # noqa: F821
