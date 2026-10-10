from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    age: Mapped[int | None] = mapped_column(Integer)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    goal: Mapped[str] = mapped_column(String(40), default="general_fitness")
    # SHA-256 of the user's API token; the token itself is never stored.
    api_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    biometrics: Mapped[list["DailyBiometrics"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    integrations: Mapped[list["IntegrationAccount"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class DailyBiometrics(Base):
    __tablename__ = "daily_biometrics"
    # One row per user per day: makes every sync an idempotent upsert on this key.
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_biometrics_user_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    hrv_ms: Mapped[float | None] = mapped_column(Float)
    sleep_score: Mapped[int | None] = mapped_column(Integer)
    sleep_minutes: Mapped[int | None] = mapped_column(Integer)
    resting_hr_bpm: Mapped[int | None] = mapped_column(Integer)
    calories_kcal: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(20), default="seed")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="biometrics")


class IntegrationAccount(Base):
    """A user's connection to an external data provider. Tokens are Fernet-encrypted at rest."""

    __tablename__ = "integration_accounts"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_integration_user_provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    access_token_enc: Mapped[str] = mapped_column(Text)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text)
    # OAuth 1.0 (FatSecret) signs requests with a per-user token secret instead of using refresh tokens.
    token_secret_enc: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="integrations")
