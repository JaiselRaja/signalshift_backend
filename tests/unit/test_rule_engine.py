"""Unit tests for tournament rule engine."""

import uuid
import pytest

from app.tournaments.rule_engine import QualificationEngine, _safe_eval_formula
from app.tournaments.schemas import RuleSetRead, TeamStanding


def _make_standing(
    team_name: str, points: int, gf: int, ga: int,
    played: int = 3, wins: int = 0, draws: int = 0, losses: int = 0,
    hours: float = 5.0,
) -> TeamStanding:
    return TeamStanding(
        team_id=uuid.uuid4(),
        team_name=team_name,
        played=played,
        wins=wins, draws=draws, losses=losses,
        goals_for=gf, goals_against=ga,
        goal_difference=gf - ga,
        points=points,
        hours_played=hours,
    )


def _make_rule(rule_def: dict) -> RuleSetRead:
    return RuleSetRead(
        id=uuid.uuid4(),
        tournament_id=uuid.uuid4(),
        rule_category="qualification",
        rule_name="test_rule",
        priority=0,
        rule_definition=rule_def,
        is_active=True,
    )


class TestTopNQualification:
    def test_top_2_by_points(self):
        standings = [
            _make_standing("A", 9, 10, 2),
            _make_standing("B", 6, 7, 5),
            _make_standing("C", 3, 4, 8),
            _make_standing("D", 1, 2, 9),
        ]
        rule = _make_rule({
            "type": "top_n", "n": 2,
            "sort_by": ["points", "goal_difference", "goals_for"],
        })

        engine = QualificationEngine()
        result = engine.evaluate(standings, rule)

        assert len(result.qualified_teams) == 2
        assert result.qualified_teams[0].team_name == "A"
        assert result.qualified_teams[1].team_name == "B"
        assert all(t.is_qualified for t in result.qualified_teams)

    def test_with_min_matches(self):
        standings = [
            _make_standing("A", 9, 10, 2, played=3),
            _make_standing("B", 6, 7, 5, played=1),
        ]
        rule = _make_rule({
            "type": "top_n", "n": 2,
            "sort_by": ["points"],
            "min_matches_played": 2,
        })

        engine = QualificationEngine()
        result = engine.evaluate(standings, rule)

        assert len(result.qualified_teams) == 1
        assert result.qualified_teams[0].team_name == "A"


class TestFormulaQualification:
    def test_simple_formula(self):
        standings = [
            _make_standing("A", 9, 10, 2),
            _make_standing("B", 3, 4, 8),
        ]
        rule = _make_rule({
            "type": "formula",
            "expression": "points * 2 + goal_difference",
            "threshold": 15,
            "operator": ">=",
        })

        engine = QualificationEngine()
        result = engine.evaluate(standings, rule)

        # A: 9*2 + 8 = 26 >= 15 ✓
        # B: 3*2 + (-4) = 2 >= 15 ✗
        assert len(result.qualified_teams) == 1
        assert result.qualified_teams[0].team_name == "A"


class TestMinHoursQualification:
    def test_min_hours(self):
        standings = [
            _make_standing("A", 9, 10, 2, hours=10.0),
            _make_standing("B", 6, 7, 5, hours=3.0),
        ]
        rule = _make_rule({"type": "min_hours", "min_hours": 5.0})

        engine = QualificationEngine()
        result = engine.evaluate(standings, rule)

        assert len(result.qualified_teams) == 1
        assert result.qualified_teams[0].team_name == "A"


class TestSafeFormulaEval:
    def test_basic_arithmetic(self):
        team = _make_standing("X", 9, 10, 2)
        result = _safe_eval_formula("points + goals_for", team)
        assert result == 19.0

    def test_division(self):
        team = _make_standing("X", 10, 8, 4, hours=5.0)
        result = _safe_eval_formula("points / hours_played", team)
        assert result == 2.0

    def test_rejects_function_calls(self):
        team = _make_standing("X", 9, 10, 2)
        with pytest.raises(ValueError, match="Unsafe AST node"):
            _safe_eval_formula("__import__('os').system('rm -rf /')", team)

    def test_rejects_attribute_access(self):
        team = _make_standing("X", 9, 10, 2)
        with pytest.raises(ValueError, match="Unsafe AST node"):
            _safe_eval_formula("team.__class__", team)
