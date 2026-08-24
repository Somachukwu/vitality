from datetime import datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SleepSession(Base):
    __tablename__ = 'sleep_sessions'

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    sleep_date = mapped_column(Date, nullable=False, index=True)
    sleep_start = mapped_column(DateTime, nullable=True)
    sleep_end = mapped_column(DateTime, nullable=True)
    duration_min = mapped_column(Integer, nullable=True)
    light_min = mapped_column(Integer, nullable=True)
    deep_min = mapped_column(Integer, nullable=True)
    rem_min = mapped_column(Integer, nullable=True)
    awake_min = mapped_column(Integer, nullable=True)
    source = mapped_column(String(50), nullable=True, default='google_fit')
    created_at = mapped_column(DateTime, server_default=func.now())

    user = relationship('User', back_populates='sleep_sessions')