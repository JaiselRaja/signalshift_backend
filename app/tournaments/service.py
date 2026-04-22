"""Tournament business logic."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.event_bus import event_bus
from app.core.exceptions import (
    AuthorizationError, ConflictError, NotFoundError, ValidationError,
)
from app.teams.models import Team, TeamMembership
from app.tournaments.models import (
    Tournament, TournamentMatch, TournamentRegistration, TournamentRuleSet,
)
from app.tournaments.rule_engine import QualificationEngine
from app.tournaments.schemas import (
    MatchCreate, MatchRead, MatchResultUpdate,
    QualificationResult, RegistrationRead,
    RuleSetCreate, RuleSetRead,
    TeamStanding, TournamentCreate, TournamentRead, TournamentUpdate,
)
from app.tournaments.standing_calculator import StandingCalculator
from app.users.models import User

logger = logging.getLogger(__name__)


class TournamentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.standing_calc = StandingCalculator()
        self.qualification_engine = QualificationEngine()

    # ─── Tournament CRUD ─────────────────────────────

    async def create_tournament(
        self, user: User, data: TournamentCreate
    ) -> TournamentRead:
        """Create tournament with optional inline rules (single transaction)."""
        existing = await self.db.execute(
            select(Tournament).where(and_(
                Tournament.tenant_id == user.tenant_id,
                Tournament.slug == data.slug,
            ))
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Tournament '{data.slug}' already exists")

        # Create tournament
        tournament = Tournament(
            tenant_id=user.tenant_id,
            turf_id=data.turf_id,
            name=data.name,
            slug=data.slug,
            sport_type=data.sport_type,
            format=data.format,
            tournament_starts=data.tournament_starts,
            tournament_ends=data.tournament_ends,
            registration_starts=data.registration_starts,
            registration_ends=data.registration_ends,
            max_teams=data.max_teams,
            min_teams=data.min_teams,
            entry_fee=float(data.entry_fee),
            prize_pool=data.prize_pool,
            config=data.config,
        )
        self.db.add(tournament)
        await self.db.flush()

        # Add inline rules
        for rule_data in data.rules:
            rule = TournamentRuleSet(
                tournament_id=tournament.id,
                **rule_data.model_dump(),
            )
            self.db.add(rule)

        await self.db.commit()
        await self.db.refresh(tournament)
        return TournamentRead.model_validate(tournament)

    async def get_tournament(self, tournament_id: uuid.UUID) -> TournamentRead:
        result = await self.db.execute(
            select(Tournament)
            .options(selectinload(Tournament.rule_sets))
            .where(Tournament.id == tournament_id)
        )
        tournament = result.scalar_one_or_none()
        if not tournament:
            raise NotFoundError("Tournament", str(tournament_id))
        return TournamentRead.model_validate(tournament)

    async def list_tournaments(
        self, tenant_id: uuid.UUID, status: str | None = None
    ) -> list[TournamentRead]:
        query = select(Tournament).where(Tournament.tenant_id == tenant_id)
        if status:
            query = query.where(Tournament.status == status)
        query = query.order_by(Tournament.tournament_starts.desc())

        result = await self.db.execute(query)
        return [TournamentRead.model_validate(t) for t in result.scalars().all()]

    async def update_tournament(
        self, tournament_id: uuid.UUID, data: TournamentUpdate
    ) -> TournamentRead:
        tournament = await self.db.get(Tournament, tournament_id)
        if not tournament:
            raise NotFoundError("Tournament", str(tournament_id))

        for key, value in data.model_dump(exclude_unset=True).items():
            if key == "entry_fee" and value is not None:
                value = float(value)
            setattr(tournament, key, value)

        await self.db.commit()
        await self.db.refresh(tournament)
        return TournamentRead.model_validate(tournament)

    # ─── Rule management ─────────────────────────────

    async def add_rule(
        self, tournament_id: uuid.UUID, data: RuleSetCreate
    ) -> RuleSetRead:
        tournament = await self.db.get(Tournament, tournament_id)
        if not tournament:
            raise NotFoundError("Tournament", str(tournament_id))

        rule = TournamentRuleSet(tournament_id=tournament_id, **data.model_dump())
        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)
        return RuleSetRead.model_validate(rule)

    async def get_rules(
        self, tournament_id: uuid.UUID, category: str | None = None
    ) -> list[RuleSetRead]:
        query = select(TournamentRuleSet).where(
            TournamentRuleSet.tournament_id == tournament_id
        )
        if category:
            query = query.where(TournamentRuleSet.rule_category == category)
        query = query.order_by(TournamentRuleSet.priority)

        result = await self.db.execute(query)
        return [RuleSetRead.model_validate(r) for r in result.scalars().all()]

    # ─── Registration ────────────────────────────────

    async def register_team(
        self, user: User, tournament_id: uuid.UUID, team_id: uuid.UUID
    ) -> RegistrationRead:
        tournament = await self.db.get(Tournament, tournament_id)
        if not tournament:
            raise NotFoundError("Tournament", str(tournament_id))

        if tournament.status != "registration_open":
            raise ValidationError("Registration is not open for this tournament")

        # Verify user is team manager/captain
        membership = await self.db.execute(
            select(TeamMembership).where(and_(
                TeamMembership.team_id == team_id,
                TeamMembership.user_id == user.id,
                TeamMembership.role.in_(["manager", "captain"]),
                TeamMembership.is_active.is_(True),
            ))
        )
        if not membership.scalar_one_or_none():
            raise AuthorizationError("Must be team manager or captain to register")

        # Check not already registered
        existing = await self.db.execute(
            select(TournamentRegistration).where(and_(
                TournamentRegistration.tournament_id == tournament_id,
                TournamentRegistration.team_id == team_id,
            ))
        )
        if existing.scalar_one_or_none():
            raise ConflictError("Team is already registered")

        # Check max teams
        if tournament.max_teams:
            count_result = await self.db.execute(
                select(func.count(TournamentRegistration.id)).where(and_(
                    TournamentRegistration.tournament_id == tournament_id,
                    TournamentRegistration.status.in_(["pending", "approved"]),
                ))
            )
            current_count = count_result.scalar() or 0
            if current_count >= tournament.max_teams:
                raise ValidationError("Tournament is full")

        registration = TournamentRegistration(
            tournament_id=tournament_id,
            team_id=team_id,
            registered_by=user.id,
            payment_status="unpaid" if tournament.entry_fee > 0 else "paid",
        )
        self.db.add(registration)
        await self.db.commit()
        await self.db.refresh(registration)

        await event_bus.emit("tournament.registered", {
            "tournament_id": str(tournament_id),
            "team_id": str(team_id),
            "captain_id": str(user.id),
            "payment_status": registration.payment_status,
        })

        return RegistrationRead.model_validate(registration)

    async def list_registrations(
        self, tournament_id: uuid.UUID
    ) -> list[RegistrationRead]:
        result = await self.db.execute(
            select(TournamentRegistration)
            .where(TournamentRegistration.tournament_id == tournament_id)
            .order_by(TournamentRegistration.created_at)
        )
        return [RegistrationRead.model_validate(r) for r in result.scalars().all()]

    # ─── Matches ─────────────────────────────────────

    async def create_match(
        self, tournament_id: uuid.UUID, data: MatchCreate
    ) -> MatchRead:
        match = TournamentMatch(tournament_id=tournament_id, **data.model_dump())
        self.db.add(match)
        await self.db.commit()
        await self.db.refresh(match)
        return MatchRead.model_validate(match)

    async def update_result(
        self, match_id: uuid.UUID, data: MatchResultUpdate
    ) -> MatchRead:
        match = await self.db.get(TournamentMatch, match_id)
        if not match:
            raise NotFoundError("Match", str(match_id))

        match.home_score = data.home_score
        match.away_score = data.away_score
        match.extra_data = data.extra_data
        match.status = "completed"

        # Determine winner
        if data.home_score > data.away_score:
            match.winner_team_id = match.home_team_id
            match.is_draw = False
        elif data.home_score < data.away_score:
            match.winner_team_id = match.away_team_id
            match.is_draw = False
        else:
            match.winner_team_id = None
            match.is_draw = True

        await self.db.commit()
        await self.db.refresh(match)
        return MatchRead.model_validate(match)

    async def list_matches(
        self, tournament_id: uuid.UUID, round_name: str | None = None
    ) -> list[MatchRead]:
        query = select(TournamentMatch).where(
            TournamentMatch.tournament_id == tournament_id
        )
        if round_name:
            query = query.where(TournamentMatch.round_name == round_name)
        query = query.order_by(TournamentMatch.match_number)

        result = await self.db.execute(query)
        return [MatchRead.model_validate(m) for m in result.scalars().all()]

    # ─── Standings & Qualification ────────────────────

    async def compute_standings(
        self, tournament_id: uuid.UUID, group_name: str | None = None
    ) -> list[TeamStanding]:
        """Compute live standings from match results + scoring rules."""
        # Load matches
        result = await self.db.execute(
            select(TournamentMatch).where(
                TournamentMatch.tournament_id == tournament_id
            )
        )
        matches = list(result.scalars().all())

        # Load scoring rule
        scoring_result = await self.db.execute(
            select(TournamentRuleSet).where(and_(
                TournamentRuleSet.tournament_id == tournament_id,
                TournamentRuleSet.rule_category == "scoring",
                TournamentRuleSet.is_active.is_(True),
            )).limit(1)
        )
        scoring_rule = scoring_result.scalar_one_or_none()

        # Build team name map
        team_names = await self._get_team_names(tournament_id)

        return self.standing_calc.compute(
            matches, scoring_rule, team_names, group_name
        )

    async def evaluate_qualification(
        self, tournament_id: uuid.UUID, stage: str = "group_stage"
    ) -> QualificationResult:
        """Apply qualification rules to computed standings."""
        standings = await self.compute_standings(tournament_id)

        # Load qualification rule
        result = await self.db.execute(
            select(TournamentRuleSet).where(and_(
                TournamentRuleSet.tournament_id == tournament_id,
                TournamentRuleSet.rule_category == "qualification",
                TournamentRuleSet.is_active.is_(True),
            )).order_by(TournamentRuleSet.priority).limit(1)
        )
        rule = result.scalar_one_or_none()
        if not rule:
            raise ValidationError("No qualification rule configured")

        rule_read = RuleSetRead.model_validate(rule)
        return self.qualification_engine.evaluate(standings, rule_read)

    # ─── Helpers ─────────────────────────────────────

    async def _get_team_names(
        self, tournament_id: uuid.UUID
    ) -> dict[uuid.UUID, str]:
        result = await self.db.execute(
            select(Team.id, Team.name)
            .join(TournamentRegistration, Team.id == TournamentRegistration.team_id)
            .where(TournamentRegistration.tournament_id == tournament_id)
        )
        return {row[0]: row[1] for row in result.all()}
