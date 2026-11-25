"""Experimental teaching instructions from measured movement facts only (spec 15).

Every statement is derived from landmarks that were reliably measured in the section. Body parts
that were not tracked are never described. Text is produced for both viewing perspectives:

- `mirror` (default, like a dance-class mirror): the reference video is flipped, so the learner
  uses the same body side as the dancer — the dancer's left arm is "your left arm";
- `direct` (video not flipped): a learner following the screen moves like a reflection, so the
  dancer's left arm is "your right arm" and travel to the dancer's left is "to your right".

Sides use MediaPipe's convention (LEFT_* = the dancer's own left). Directions assume the dancer
faces the camera; facing is only estimated (experimental yaw), so all text is labelled experimental.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

from app.pose import landmarks as L

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]

INSTRUCTIONS_VERSION = "instr-1"

Side = Literal["left", "right"]
_OTHER: dict[Side, Side] = {"left": "right", "right": "left"}


@dataclass(frozen=True)
class SectionInput:
    """Measured features for the analysed frames inside one section."""

    norm: FloatArray  # (T,33,2) hip-centred torso units, image axes (y down), NaN = unreliable
    angles: dict[str, FloatArray]  # degrees, NaN = unreliable
    travel: FloatArray  # (T,2) torso units from the clip's first valid frame
    lean: FloatArray  # (T,) degrees, + = toward image right
    energy: FloatArray  # (T,)
    valid: BoolArray  # (T,)
    clip_energy: float  # median motion energy over the whole clip (for relative pace)


@dataclass
class Fact:
    kind: str
    side: Side | Literal["both"] | None  # dancer-relative side, if any
    mirror: str
    direct: str
    value: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "side": self.side,
            "value": self.value,
            "mirror": self.mirror,
            "direct": self.direct,
        }


@dataclass
class SectionDescription:
    coverage: float
    instruction_mirror: str
    instruction_direct: str
    facts: list[Fact] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": INSTRUCTIONS_VERSION,
            "experimental": True,
            "coverage": round(self.coverage, 4),
            "instruction_mirror": self.instruction_mirror,
            "instruction_direct": self.instruction_direct,
            "facts": [f.as_dict() for f in self.facts],
            "untracked": self.untracked,
        }


def _learner_side(dancer_side: Side, perspective: Literal["mirror", "direct"]) -> Side:
    return dancer_side if perspective == "mirror" else _OTHER[dancer_side]


def _image_dir_to_dancer_side(dx: float) -> Side:
    # Facing the camera, the dancer's own left appears on the image's right.
    return "left" if dx > 0 else "right"


def _round_to(v: float, step: int = 10) -> int:
    return int(step * round(v / step))


def _thirds(mask: BoolArray) -> list[BoolArray]:
    n = len(mask)
    edges = [0, n // 3, (2 * n) // 3, n]
    out = []
    for a, b in zip(edges[:-1], edges[1:], strict=True):
        m = np.zeros(n, dtype=bool)
        m[a:b] = True
        out.append(m & mask)
    return out


def _arm_fact(inp: SectionInput, side: Side) -> tuple[str, float] | None:
    wrist = L.L_WRIST if side == "left" else L.R_WRIST
    shoulder = L.L_SHOULDER if side == "left" else L.R_SHOULDER
    wy, sy = inp.norm[:, wrist, 1], inp.norm[:, shoulder, 1]
    known = inp.valid & ~np.isnan(wy) & ~np.isnan(sy)
    if inp.valid.sum() == 0 or known.sum() < max(3, 0.4 * inp.valid.sum()):
        return None
    above = known & (wy < sy)  # image y grows downward
    frac = float(above.sum() / known.sum())
    parts = [p for p in _thirds(known) if p.sum() >= 2]
    if len(parts) >= 2:
        first = float((above & parts[0]).sum() / parts[0].sum())
        last = float((above & parts[-1]).sum() / parts[-1].sum())
        if first < 0.3 and last > 0.6:
            return "raise", frac
        if first > 0.6 and last < 0.3:
            return "lower", frac
    if frac > 0.6:
        return "keep_up", frac
    if 0.15 <= frac <= 0.6:
        return "lift_briefly", frac
    return None


_ARM_TEXT = {
    "raise": "Raise {arm} above shoulder level",
    "lower": "Bring {arm} down from above your shoulder",
    "keep_up": "Keep {arm} above shoulder level",
    "lift_briefly": "Lift {arm} above shoulder level briefly",
}


def _arm_phrase(side: Side | Literal["both"], perspective: Literal["mirror", "direct"]) -> str:
    if side == "both":
        return "both arms"
    return f"your {_learner_side(side, perspective)} arm"


def _reliable_fraction(values: FloatArray, valid: BoolArray) -> float:
    n = int(valid.sum())
    return float((valid & ~np.isnan(values)).sum() / n) if n else 0.0


def describe_section(inp: SectionInput) -> SectionDescription:
    n = len(inp.valid)
    coverage = float(inp.valid.sum() / n) if n else 0.0
    untracked: list[str] = []
    if coverage < 0.5:
        text = "Tracking is limited in this section — follow the video."
        return SectionDescription(coverage, text, text, [], ["most of this section"])

    facts: list[Fact] = []

    # Arms: wrist relative to shoulder height.
    sides: tuple[Side, Side] = ("left", "right")
    arm = {s: _arm_fact(inp, s) for s in sides}
    for s in ("left", "right"):
        if (
            arm[s] is None
            and _reliable_fraction(
                inp.norm[:, L.L_WRIST if s == "left" else L.R_WRIST, 1], inp.valid
            )
            < 0.4
        ):
            untracked.append(f"{s} arm")
    la, ra = arm["left"], arm["right"]
    if la and ra and la[0] == ra[0]:
        tmpl = _ARM_TEXT[la[0]]
        facts.append(
            Fact(
                f"arm_{la[0]}",
                "both",
                tmpl.format(arm="both arms"),
                tmpl.format(arm="both arms"),
                round((la[1] + ra[1]) / 2, 2),
            )
        )
    else:
        for side, res in (("left", la), ("right", ra)):
            if res is None:
                continue
            tmpl = _ARM_TEXT[res[0]]
            facts.append(
                Fact(
                    f"arm_{res[0]}",
                    side,  # type: ignore[arg-type]
                    tmpl.format(arm=_arm_phrase(side, "mirror")),  # type: ignore[arg-type]
                    tmpl.format(arm=_arm_phrase(side, "direct")),  # type: ignore[arg-type]
                    round(res[1], 2),
                )
            )

    # Travel across the frame (horizontal root displacement inside the section).
    tx = inp.travel[:, 0]
    known_t = inp.valid & ~np.isnan(tx)
    if known_t.sum() >= 3:
        idx = np.flatnonzero(known_t)
        dx = float(tx[idx[-1]] - tx[idx[0]])
        if abs(dx) >= 0.6:
            side = _image_dir_to_dancer_side(dx)
            facts.append(
                Fact(
                    "travel",
                    side,
                    f"Travel to your {_learner_side(side, 'mirror')}",
                    f"Travel to your {_learner_side(side, 'direct')}",
                    round(dx, 2),
                )
            )

    # Knees: only when the legs were actually measured.
    knees = []
    for s, name in (("left", "left_knee"), ("right", "right_knee")):
        vals = inp.angles.get(name)
        if vals is None or _reliable_fraction(vals, inp.valid) < 0.5:
            untracked.append(f"{s} leg")
            continue
        knees.append(float(np.nanpercentile(vals[inp.valid], 10)))
    if len(knees) == 2 and min(knees) < 150:
        deg = _round_to(min(knees))
        text = f"Bend your knees (to about {deg}°)"
        facts.append(Fact("knee_bend", "both", text, text, float(deg)))

    # Elbows: a clear bend that changes during the section.
    elbows: dict[Side, int] = {}
    for s, name in (("left", "left_elbow"), ("right", "right_elbow")):
        vals = inp.angles.get(name)
        if vals is None or _reliable_fraction(vals, inp.valid) < 0.4:
            continue
        v = vals[inp.valid & ~np.isnan(vals)]
        lo, hi = float(np.percentile(v, 10)), float(np.percentile(v, 90))
        if lo < 110 and hi - lo > 40:
            elbows[s] = _round_to(lo)  # type: ignore[index]
    if len(elbows) == 2:
        a, b = elbows["left"], elbows["right"]
        if a == b:
            text = f"Bend both elbows to about {a}°"
            facts.append(Fact("elbow_bend", "both", text, text, float(a)))
        else:
            m_text = f"Bend both elbows (left about {a}°, right about {b}°)"
            d_text = f"Bend both elbows (left about {b}°, right about {a}°)"
            facts.append(Fact("elbow_bend", "both", m_text, d_text, float(min(a, b))))
    else:
        for side, deg in elbows.items():
            facts.append(
                Fact(
                    "elbow_bend",
                    side,
                    f"Bend your {_learner_side(side, 'mirror')} elbow to about {deg}°",
                    f"Bend your {_learner_side(side, 'direct')} elbow to about {deg}°",
                    float(deg),
                )
            )

    # Torso lean held through most of the section.
    lv = inp.lean[inp.valid & ~np.isnan(inp.lean)]
    if lv.size >= 3 and abs(float(np.median(lv))) >= 12:
        med = float(np.median(lv))
        side = _image_dir_to_dancer_side(med)
        deg = _round_to(abs(med), 5)
        facts.append(
            Fact(
                "lean",
                side,
                f"Lean your torso to your {_learner_side(side, 'mirror')} (about {deg}°)",
                f"Lean your torso to your {_learner_side(side, 'direct')} (about {deg}°)",
                float(deg),
            )
        )

    # Relative pace against the rest of this dance.
    ev = inp.energy[inp.valid & ~np.isnan(inp.energy)]
    pace: Fact | None = None
    if ev.size and math.isfinite(inp.clip_energy) and inp.clip_energy > 0:
        ratio = float(np.median(ev)) / inp.clip_energy
        if ratio >= 1.3:
            t = "One of the faster parts of this dance — start at 0.5×"
            pace = Fact("pace_fast", None, t, t, round(ratio, 2))
        elif ratio <= 0.5:
            t = "Small, slow movements here — match the shapes closely"
            pace = Fact("pace_slow", None, t, t, round(ratio, 2))

    chosen = facts[:3]
    if pace is not None and len(chosen) < 3:
        chosen.append(pace)
    if not chosen:
        t = "Follow the arm path at half speed"
        chosen = [Fact("follow", None, t, t)]

    def join(key: Literal["mirror", "direct"]) -> str:
        return ". ".join(getattr(f, key) for f in chosen) + "."

    return SectionDescription(coverage, join("mirror"), join("direct"), chosen, untracked)
