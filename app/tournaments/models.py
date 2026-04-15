"""Tournament, TournamentRuleSet, Registration, Match models."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, ForeignKey, Integer, Numeric,
    String, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, UUIDMixin


class Tournament(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tournaments"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    turf_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("turfs.id")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    sport_type: Mapped[str] = mapped_column(String(50), nullable=False)
    format: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")

    registration_starts: Mapped[date | None] = mapped_column(Date)
    registration_ends: Mapped[date | None] = mapped_column(Date)
    tournament_starts: Mapped[date] = mapped_column(Date, nullable=False)
    tournament_ends: Mapped[date | None] = mapped_column(Date)

    max_teams: Mapped[int | None] = mapped_column(Integer)
    min_teams: Mapped[int] = mapped_column(Integer, default=2)
    entry_fee: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    prize_pool: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Relationships
    rule_sets: Mapped[list["TournamentRuleSet"]] = relationship(
        back_populates="tournament", lazy="selectin", cascade="all, delete-orphan"
    )
    registrations: Mapped[list["TournamentRegistration"]] = relationship(
        back_populates="tournament", cascade="all, delete-orphan"
    )
    matches: Mapped[list["TournamentMatch"]] = relationship(
        back_populates="tournament", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_tournaments_tenant_slug"),
    )


class TournamentRuleSet(Base, UUIDMixin):
    """Data-driven rule — the heart of configurable tournament logic."""
    __tablename__ = "tournament_rule_sets"

    tournament_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_category: Mapped[str] = mapped_column(String(50), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rule_definition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    tournament: Mapped[Tournament] = relationship(back_populates="rule_sets")

    __table_args__ = (
        UniqueConstraint(
            "tournament_id", "rule_category", "rule_name",
            name="uq_ruleset_tournament_cat_name",
        ),
    )


class TournamentRegistration(Base, UUIDMixin):
    __tablename__ = "tournament_registrations"

    tournament_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tournaments.id"), nullable=False
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False
    )
    registered_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    payment_status: Mapped[str] = mapped_column(String(30), nullable=False, default="unpaid")
    seed: Mapped[int | None] = mapped_column(Integer)
    group_name: Mapped[str | None] = mapped_column(String(10))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    tournament: Mapped[Tournament] = relationship(back_populates="registrations")
    team: Mapped["Team"] = relationship("Team")

    __table_args__ = (
        UniqueConstraint(
            "tournament_id", "team_id", name="uq_registration_tournament_team"
        ),
    )


class TournamentMatch(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tournament_matches"

    tournament_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tournaments.id"), nullable=False
    )
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("bookings.id")
    )
    round_name: Mapped[str] = mapped_column(String(50), nullable=False)
    group_name: Mapped[str | None] = mapped_column(String(10))
    match_number: Mapped[int | None] = mapped_column(Integer)

    home_team_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("teams.id")
    )
    away_team_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("teams.id")
    )
    scheduled_at: Mapped[datetime | None] = mapped_column()
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="scheduled")

    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)
    winner_team_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("teams.id")
    )
    is_draw: Mapped[bool] = mapped_column(Boolean, default=False)
    extra_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    tournament: Mapped[Tournament] = relationship(back_populates="matches")
    home_team: Mapped["Team | None"] = relationship("Team", foreign_keys=[home_team_id])
    away_team: Mapped["Team | None"] = relationship("Team", foreign_keys=[away_team_id])
