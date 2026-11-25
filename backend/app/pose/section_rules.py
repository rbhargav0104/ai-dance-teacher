"""Section rules shared by the API and the segmentation maths (no numpy, so LIMITED mode can
still list sections). See app/pose/segmentation.py for the automatic algorithm."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SegmentationConfig:
    min_len: float = 2.0  # never cut a section shorter than this automatically
    max_len: float = 8.0
    pref_min: float = 3.0
    pref_max: float = 7.0
    pref_len: float = 5.0
    smooth_window_s: float = 0.5
    reversal_window_s: float = 0.33
    pause_window_s: float = 0.5
    boundary_penalty: float = 0.08  # mild preference for fewer sections
    unknown_cost: float = 0.6  # cutting inside a tracking gap: allowed, slightly discouraged
    min_edit_len: float = 0.5  # manual edits: shortest section a user may create
    max_sections: int = 40


class InvalidSections(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def validate_sections(
    sections: list[tuple[float, float]],
    duration: float,
    cfg: SegmentationConfig | None = None,
    tolerance: float = 0.01,
) -> list[tuple[float, float]]:
    """Server-side check for edited sections. Returns them snapped to exact full coverage.

    Rules: ordered, contiguous (no gap or overlap), first starts at 0, last ends at the video
    duration, each at least `min_edit_len` long, at most `max_sections`.
    """
    cfg = cfg or SegmentationConfig()
    if not sections:
        raise InvalidSections("sections_empty", "A dance needs at least one section.")
    if len(sections) > cfg.max_sections:
        raise InvalidSections(
            "too_many_sections", f"A dance can have at most {cfg.max_sections} sections."
        )
    duration = round(float(duration), 3)
    out: list[tuple[float, float]] = []
    for idx, (s, e) in enumerate(sections):
        if not (math.isfinite(s) and math.isfinite(e)):
            raise InvalidSections("invalid_section_time", "Section times must be numbers.")
        if idx == 0 and abs(s) > tolerance:
            raise InvalidSections("sections_gap", "The first section must start at 0:00.")
        if idx > 0:
            gap = s - out[-1][1]
            if gap > tolerance:
                raise InvalidSections(
                    "sections_gap", f"There is a gap before section {idx + 1:02d}."
                )
            if gap < -tolerance:
                raise InvalidSections(
                    "sections_overlap", f"Section {idx + 1:02d} overlaps the previous one."
                )
        start = 0.0 if idx == 0 else out[-1][1]
        end = round(float(e), 3)
        if end - start < cfg.min_edit_len - 1e-9:
            raise InvalidSections(
                "section_too_short",
                f"Section {idx + 1:02d} is shorter than {cfg.min_edit_len:g} s.",
            )
        out.append((start, end))
    if abs(out[-1][1] - duration) > tolerance:
        raise InvalidSections(
            "sections_incomplete", "The last section must end where the video ends."
        )
    out[-1] = (out[-1][0], duration)
    if out[-1][1] - out[-1][0] < cfg.min_edit_len - 1e-9:
        raise InvalidSections(
            "section_too_short",
            f"Section {len(out):02d} is shorter than {cfg.min_edit_len:g} s.",
        )
    return out
