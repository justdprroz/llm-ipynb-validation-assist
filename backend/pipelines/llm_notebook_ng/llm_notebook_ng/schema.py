"""Internal value model: ternary scale + GradeLab status mapping."""

from __future__ import annotations

from dataclasses import dataclass, field

TERNARY = (0.0, 0.5, 1.0)
MAX_SCORE = 10.0  # cosmetic, matches sibling pipelines


def quantize(value: object, *, allowed: tuple[float, ...] = TERNARY) -> float:
    """Snap an arbitrary model number to the nearest allowed ternary level."""
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    v = max(0.0, min(1.0, v))
    return min(allowed, key=lambda a: abs(a - v))


def status_from_mark(mark: float, *, failed: bool = False) -> str:
    if failed:
        return "error"
    if mark >= 1.0:
        return "pass"
    if mark > 0.0:
        return "partial"
    return "fail"


@dataclass
class TaskSpec:
    """One canonical task, shared across the whole cohort."""

    task_id: str
    description: str
    output_type: str = "none"  # "text" | "plot" | "none"
    skeleton_cell_ids: list[int] = field(default_factory=list)
    match_text: str = ""  # skeleton prompt text, used to locate student cells

    @property
    def expects_image(self) -> bool:
        return self.output_type == "plot"
