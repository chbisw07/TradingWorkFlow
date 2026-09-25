"""User-owned preferences and immutable change metadata."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from twf.infrastructure.database import Base


class PreferenceProfile(Base):
    __tablename__ = "preference_profiles"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    values: Mapped[dict[str, str]] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserPreferences(Base):
    __tablename__ = "user_preferences"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    values: Mapped[dict[str, str]] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    active_profile_id: Mapped[UUID | None] = mapped_column(ForeignKey("preference_profiles.id"))
    applied_profile_revision: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PreferenceChange(Base):
    __tablename__ = "preference_changes"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    target: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(24))
    revision: Mapped[int] = mapped_column(Integer)
    request_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
