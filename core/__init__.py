"""API pública del motor del predictor."""

from .cut_parser import parse_cut, normalize_library
from .validation import validate, estimate_feasibility
from .plan_optimizer import (
    MarkerPlan,
    ProposedMarker,
    PlanGenerationError,
    generate_marker_plan,
    marker_summary,
)
from .relaxation import PreferenceSolution, RelaxationStep, solve_with_preferences

__all__ = [
    "parse_cut",
    "normalize_library",
    "validate",
    "estimate_feasibility",
    "MarkerPlan",
    "ProposedMarker",
    "PlanGenerationError",
    "generate_marker_plan",
    "marker_summary",
    "PreferenceSolution",
    "RelaxationStep",
    "solve_with_preferences",
]
