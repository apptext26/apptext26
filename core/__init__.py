"""API pública del motor del predictor."""

from .cut_parser import parse_cut, normalize_library
from .optimizer import generate
from .validation import validate
from .plan_optimizer import (
    MarkerPlan,
    ProposedMarker,
    PlanGenerationError,
    generate_marker_plan,
    marker_summary,
)

__all__ = [
    "parse_cut",
    "normalize_library",
    "generate",
    "validate",
    "MarkerPlan",
    "ProposedMarker",
    "PlanGenerationError",
    "generate_marker_plan",
    "marker_summary",
]
