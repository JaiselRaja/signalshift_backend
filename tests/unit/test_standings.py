"""Unit tests for the standing calculator."""

import uuid
from unittest.mock import MagicMock

from app.tournaments.standing_calculator import StandingCalculator


def _make_match(
    home_id, away_id, home_score, away_score,
    status="completed", group=None,
):
    match = MagicMock()
    match.home_team_id = home_id
    match.away_team_id = away_id
    match.home_score = home_score
    match.away_score = away_score
    match.status = status
    match.group_name = group
    return match


class TestStandingCalculator:
    def test_basic_standings(self):
        t1, t2 = uuid.uuid4(), uuid.uuid4()
        names = {t1: "Red", t2: "Blue"}

        matches = [
            _make_match(t1, t2, 3, 1),
            _make_match(t2, t1, 2, 2),
        ]

        calc = StandingCalculator()
        standings = calc.compute(matches, None, names)

        assert len(standings) == 2
        red = next(s for s in standings if s.team_name == "Red")
        blue = next(s for s in standings if s.team_name == "Blue")

        assert red.wins == 1
        assert red.draws == 1
        assert red.points == 4  # 3 + 1
        assert blue.wins == 0
        assert blue.draws == 1
        assert blue.losses == 1
        assert blue.points == 1

    def test_custom_scoring_rule(self):
        t1, t2 = uuid.uuid4(), uuid.uuid4()
        names = {t1: "A", t2: "B"}

        # Custom: win=2, draw=1, loss=0
        rule = MagicMock()
        rule.rule_definition = {"win": 2, "draw": 1, "loss": 0}

        matches = [_make_match(t1, t2, 1, 0)]

        calc = StandingCalculator()
        standings = calc.compute(matches, rule, names)

        a = next(s for s in standings if s.team_name == "A")
        assert a.points == 2

    def test_bonus_points(self):
        t1, t2 = uuid.uuid4(), uuid.uuid4()
        names = {t1: "X", t2: "Y"}

        rule = MagicMock()
        rule.rule_definition = {
            "win": 3, "draw": 1, "loss": 0,
            "bonus_goal_threshold": 3, "bonus_points": 1,
        }

        matches = [_make_match(t1, t2, 4, 0)]

        calc = StandingCalculator()
        standings = calc.compute(matches, rule, names)

        x = next(s for s in standings if s.team_name == "X")
        assert x.points == 4  # 3 (win) + 1 (bonus for 4 goals >= 3 threshold)

    def test_ranks_assigned(self):
        t1, t2, t3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        names = {t1: "A", t2: "B", t3: "C"}

        matches = [
            _make_match(t1, t2, 2, 0),
            _make_match(t2, t3, 1, 0),
            _make_match(t1, t3, 3, 0),
        ]

        calc = StandingCalculator()
        standings = calc.compute(matches, None, names)

        assert standings[0].rank == 1
        assert standings[0].team_name == "A"
        assert standings[1].rank == 2
        assert standings[2].rank == 3
