from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Vitals(Base):
    __tablename__ = "vitals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)

    # --- Wearable / Google Health metrics ---
    heart_rate: Mapped[float | None] = mapped_column(Float, nullable=True)         # bpm
    spo2: Mapped[float | None] = mapped_column(Float, nullable=True)               # %
    steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    calories_burned: Mapped[float | None] = mapped_column(Float, nullable=True)    # kcal
    distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)        # km
    floors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)     # heart/active zone minutes
    body_fat_pct: Mapped[float | None] = mapped_column(Float, nullable=True)       # % — from smart scale

    # --- Hardware station metrics (smart scale / env sensor) ---
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)             # kg — from smart scale ONLY
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)        # °C (skin temp from Fitbit OR ambient from station)

    # --- Data source tag ---
    # "google_health" = synced from Google Health API | NULL or "station" = pushed by hardware device
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)

    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="vitals")  # noqa: F821
    device: Mapped["Device"] = relationship(back_populates="vitals")  # noqa: F821
