from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.mysql import INTEGER as MUINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class GoogleHealthToken(Base):
    __tablename__ = 'google_health_tokens'

    id = mapped_column(MUINT(unsigned=True), primary_key=True, autoincrement=True)
    user_id = mapped_column(MUINT(unsigned=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    google_email = mapped_column(String(255), nullable=True)
    access_token = mapped_column(Text, nullable=False)
    refresh_token = mapped_column(Text, nullable=True)
    token_expiry = mapped_column(DateTime, nullable=True)
    scopes = mapped_column(JSON, nullable=True)
    is_active = mapped_column(Boolean, default=True, nullable=False)
    last_synced_at = mapped_column(DateTime, nullable=True)
    created_at = mapped_column(DateTime, server_default=func.now())
    updated_at = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship('User', back_populates='google_health_token')