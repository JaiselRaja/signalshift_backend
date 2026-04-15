"""
Standing calculator — computes live standings from match results + scoring rules.
"""

from __future__ import annotations

import uuid

from app.tournaments.models import TournamentMatch, TournamentRuleSet
from app.tournaments.schemas import TeamStanding


class StandingCalculator:
    """
    Compute standings from completed matches + scoring rule.

    Standings are NEVER stored — always derived (CQRS lite).
    """

    def compute(
        self,
        matches: list[TournamentMatch],
        scoring_rule: TournamentRuleSet | None,
        team_names: dict[uuid.UUID, str],
        group_name: str | None = None,
    ) -> list[TeamStanding]:
        """
        Build standings from match results.

        scoring_rule.rule_definition example:
        {
            "type": "points_based",
            "win": 3, "draw": 1, "loss": 0,
            "bonus_goal_threshold": 4, "bonus_points": 1
        }
        """
        # Default scoring if no rule defined
        if scoring_rule and scoring_rule.rule_definition:
            rule = scoring_rule.rule_definition
        else:
            rule = {"win": 3, "draw": 1, "loss": 0}

        win_pts = rule.get("win", 3)
        draw_pts = rule.get("draw", 1)
        loss_pts = rule.get("loss", 0)
        bonus_threshold = rule.get("bonus_goal_threshold")
        bonus_pts = rule.get("bonus_points", 0)

        # Filter matches
        relevant = [
            m for m in matches
            if m.status == "completed"
            and (group_name is None or m.group_name == group_name)
        ]

        # Build standings map
        standings: dict[uuid.UUID, TeamStanding] = {}

        def _get_standing(team_id: uuid.UUID) -> TeamStanding:
            if team_id not in standings:
                standings[team_id] = TeamStanding(
                    team_id=team_id,
                    team_name=team_names.get(team_id, "Unknown"),
                    group_name=group_name,
                )
            return standings[team_id]

        for match in relevant:
            if not match.home_team_id or not match.away_team_id:
                continue
            if match.home_score is None or match.away_score is None:
                continue

            home = _get_standing(match.home_team_id)
            away = _get_standing(match.away_team_id)

            home.played += 1
            away.played += 1
            home.goals_for += match.home_score
            home.goals_against += match.away_score
            away.goals_for += match.away_score
            away.goals_against += match.home_score

            if match.home_score > match.away_score:
                home.wins += 1
                away.losses += 1
                home.points += win_pts
                away.points += loss_pts
            elif match.home_score < match.away_score:
                away.wins += 1
                home.losses += 1
                away.points += win_pts
                home.points += loss_pts
            else:
                home.draws += 1
                away.draws += 1
                home.points += draw_pts
                away.points += draw_pts

            # Bonus points for high-scoring
            if bonus_threshold:
                if match.home_score >= bonus_threshold:
                    home.points += bonus_pts
                if match.away_score >= bonus_threshold:
                    away.points += bonus_pts

        # Compute derived fields
        for s in standings.values():
            s.goal_difference = s.goals_for - s.goals_against

        # Sort by points → goal difference → goals scored
        result = sorted(
            standings.values(),
            key=lambda s: (s.points, s.goal_difference, s.goals_for),
            reverse=True,
        )

        # Assign ranks
        for i, s in enumerate(result, start=1):
            s.rank = i

        return result
