"""
Tournament qualification engine — fully data-driven.

Uses a strategy registry pattern: new qualification types
are added by decorating a pure function with @register("type_name").
Zero modifications to existing code.
"""

from __future__ import annotations

import ast
import operator
import re
from collections.abc import Callable
from datetime import datetime, timezone

from app.tournaments.schemas import QualificationResult, RuleSetRead, TeamStanding

# Allowed variables in formula expressions
_ALLOWED_VARS = frozenset({
    "wins", "draws", "losses", "points", "goals_for",
    "goals_against", "goal_difference", "hours_played", "played",
})


class QualificationEngine:
    """
    Data-driven qualification evaluator.
    Strategy functions are registered in _EVALUATORS.
    """

    _EVALUATORS: dict[str, Callable] = {}

    @classmethod
    def register(cls, rule_type: str):
        """Decorator to register a qualification strategy."""
        def decorator(fn: Callable):
            cls._EVALUATORS[rule_type] = fn
            return fn
        return decorator

    def evaluate(
        self,
        standings: list[TeamStanding],
        rule: RuleSetRead,
    ) -> QualificationResult:
        rule_def = rule.rule_definition
        rule_type = rule_def.get("type")

        evaluator = self._EVALUATORS.get(rule_type)
        if not evaluator:
            raise ValueError(f"Unknown qualification rule type: {rule_type}")

        qualified, eliminated = evaluator(standings, rule_def)

        for i, team in enumerate(qualified, start=1):
            team.is_qualified = True
            team.rank = i
        for team in eliminated:
            team.is_qualified = False

        return QualificationResult(
            tournament_id=rule.tournament_id,
            stage=rule_def.get("from_stage", "group_stage"),
            qualified_teams=qualified,
            eliminated_teams=eliminated,
            rule_applied=rule,
            computed_at=datetime.now(timezone.utc),
        )


# ═══════════════════════════════════════════
#  BUILT-IN EVALUATORS
# ═══════════════════════════════════════════

@QualificationEngine.register("top_n")
def _eval_top_n(
    standings: list[TeamStanding], rule_def: dict
) -> tuple[list[TeamStanding], list[TeamStanding]]:
    """Top N teams by configurable sort criteria."""
    sort_keys = rule_def.get("sort_by", ["points", "goal_difference", "goals_for"])
    min_played = rule_def.get("min_matches_played", 0)
    n = rule_def["n"]

    eligible = [s for s in standings if s.played >= min_played]
    eligible.sort(
        key=lambda s: tuple(getattr(s, k, 0) for k in sort_keys),
        reverse=True,
    )
    return eligible[:n], eligible[n:]


@QualificationEngine.register("formula")
def _eval_formula(
    standings: list[TeamStanding], rule_def: dict
) -> tuple[list[TeamStanding], list[TeamStanding]]:
    """Custom formula — safely evaluated via AST, NEVER eval()."""
    expression = rule_def["expression"]
    threshold = rule_def["threshold"]
    op_str = rule_def.get("operator", ">=")

    ops = {
        ">=": operator.ge, ">": operator.gt,
        "==": operator.eq, "<=": operator.le,
        "<": operator.lt,
    }
    compare = ops[op_str]

    qualified, eliminated = [], []
    for team in standings:
        score = _safe_eval_formula(expression, team)
        team.custom_score = score
        if compare(score, threshold):
            qualified.append(team)
        else:
            eliminated.append(team)

    qualified.sort(key=lambda t: t.custom_score or 0, reverse=True)
    return qualified, eliminated


@QualificationEngine.register("min_hours")
def _eval_min_hours(
    standings: list[TeamStanding], rule_def: dict
) -> tuple[list[TeamStanding], list[TeamStanding]]:
    """Qualify teams with ≥ min_hours played."""
    min_hours = rule_def["min_hours"]
    qualified = [s for s in standings if s.hours_played >= min_hours]
    eliminated = [s for s in standings if s.hours_played < min_hours]
    qualified.sort(key=lambda t: t.hours_played, reverse=True)
    return qualified, eliminated


# ═══════════════════════════════════════════
#  SAFE FORMULA EVALUATOR (AST-based)
# ═══════════════════════════════════════════

def _safe_eval_formula(expression: str, team: TeamStanding) -> float:
    """
    Safely evaluate math expression with team stat variables.
    Uses Python AST — only arithmetic operators allowed.
    """
    variables = {
        name: float(getattr(team, name, 0))
        for name in _ALLOWED_VARS
    }
    # Prevent division by zero
    variables["hours_played"] = variables.get("hours_played") or 0.001

    # Substitute variables
    resolved = expression
    for var, val in sorted(variables.items(), key=lambda x: -len(x[0])):
        resolved = re.sub(rf"\b{var}\b", str(val), resolved)

    # Parse and walk AST
    tree = ast.parse(resolved, mode="eval")
    return float(_walk_ast(tree.body))


def _walk_ast(node: ast.AST) -> float:
    """Recursively evaluate an AST node — only safe arithmetic."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp):
        left = _walk_ast(node.left)
        right = _walk_ast(node.right)
        ops = {
            ast.Add: operator.add, ast.Sub: operator.sub,
            ast.Mult: operator.mul, ast.Div: operator.truediv,
        }
        op_fn = ops.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op_fn(left, right)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_walk_ast(node.operand)
    raise ValueError(f"Unsafe AST node: {type(node).__name__}")
