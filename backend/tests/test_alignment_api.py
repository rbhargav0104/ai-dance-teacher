"""Outcome 6 exit gate on REAL footage: attempts are FFmpeg variants of the committed Mixkit
clip (fixtures/attempts), measured by the real MediaPipe pipeline, then aligned to the
reference with the mirror-aware bounded DTW. Nothing here is synthetic.

Exit gate: scale/translation/speed variants behave as intended (stay close to the good
attempt) while wrong-limb (mirror without mirror handling), late, missing-movement and
different-dance attempts remain distinguishable.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.test_practice_analysis import ATTEMPTS, analysed_girl, attempt
from tests.test_reference_analysis import GIRL, auth, ffmpeg, real, run_jobs  # noqa: F401

# Extra real-footage variants made in the test (full resolution, so MediaPipe sees the dancer
# as well as in the reference): pure translation and a moderate zoom-out.
GENERATED = {
    "girl_shifted": "crop=1080:720:0:0,pad=1280:720:200:0:color=0x5fd900",
    "girl_zoom_0_8": "scale=1024:576,pad=1280:720:128:72:color=0x5fd900",
}

pytestmark = pytest.mark.skipif(not ATTEMPTS.is_dir(), reason="attempt fixtures missing")

VARIANTS = (
    "girl_good",
    "girl_scaled_translated",
    "girl_speed_0_9x",
    "girl_speed_1_1x",
    "girl_late_0_4s",
    "girl_mirrored",
    "girl_missing_middle",
    "girl_occluded",
    "boy_wrong_dance",
)


def alignment(c: TestClient, headers: dict[str, str], sid: str) -> dict[str, Any]:
    res = c.get(f"/api/practice-sessions/{sid}/alignment", headers=headers)
    assert res.status_code == 200, res.text
    body: dict[str, Any] = res.json()
    return body


def upload_file(c: TestClient, headers: dict[str, str], pid: str, path: Path) -> str:
    with path.open("rb") as fh:
        res = c.post(
            f"/api/projects/{pid}/practice-sessions",
            headers=headers,
            files={"file": (path.name, fh, "video/mp4")},
        )
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


def test_real_attempts_align_with_invariance_and_sensitivity(
    real: TestClient,  # noqa: F811
    auth: dict[str, str],  # noqa: F811
    tmp_path: Path,
) -> None:
    project = analysed_girl(real, auth)
    pid = project["id"]
    ids = {name: attempt(real, auth, pid, name)["id"] for name in VARIANTS}
    for name, vf in GENERATED.items():
        out_path = tmp_path / f"{name}.mp4"
        ffmpeg("-i", str(GIRL), "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "23", "-pix_fmt", "yuv420p", str(out_path))  # fmt: skip
        ids[name] = upload_file(real, auth, pid, out_path)
    sections = real.get(f"/api/projects/{pid}/segments", headers=auth).json()["sections"]
    # A learner practising section 2 records just that section (here: the good attempt cut to
    # the section's window, real footage).
    s2 = sections[1]
    cut = tmp_path / "girl_section2.mp4"
    ffmpeg("-ss", f"{s2['start']:.3f}", "-i", str(ATTEMPTS / "girl_good.mp4"), "-t",
           f"{s2['end'] - s2['start']:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast",
           "-pix_fmt", "yuv420p", str(cut))  # fmt: skip
    with cut.open("rb") as fh:
        res = real.post(
            f"/api/projects/{pid}/practice-sessions",
            headers=auth,
            files={"file": (cut.name, fh, "video/mp4")},
            data={"segment_id": s2["id"]},
        )
    assert res.status_code == 201, res.text
    sec_id = res.json()["id"]
    assert run_jobs() == len(ids) + 1

    if dump := os.environ.get("ALIGN_DUMP"):  # developer aid: raw frames for offline tuning
        ref_frames = real.get(f"/api/projects/{pid}/poses", headers=auth).json()["frames"]
        att = {
            n: real.get(f"/api/practice-sessions/{sid}/poses", headers=auth).json()["frames"]
            for n, sid in ids.items()
        }
        with open(dump, "w") as fh:
            json.dump({"reference": ref_frames, "attempts": att, "sections": sections}, fh)
    out = {name: alignment(real, auth, sid) for name, sid in ids.items()}
    al = {k: v["alignment"] for k, v in out.items()}
    if os.environ.get("ALIGN_DEBUG"):
        print(
            json.dumps(
                {
                    k: {
                        "status": a["status"],
                        "mirror": a.get("mirror"),
                        "size": a.get("body_size_factor"),
                        "summary": a.get("summary"),
                        "timing": a.get("timing"),
                        "warp": a.get("warp"),
                        "missing": a.get("missing_spans"),
                        "masked": a.get("masked_spans"),
                        "energy": a.get("reference_median_energy"),
                    }
                    for k, a in al.items()
                },
                indent=1,
            )
        )
    assert all(v["cached"] is False for v in out.values())
    again = alignment(real, auth, ids["girl_good"])
    assert again["cached"] is True and again["alignment"] == al["girl_good"]

    def cost(name: str) -> float:
        v = al[name]["summary"]["mean_cost"]
        assert isinstance(v, float), (name, al[name]["status"])
        return v

    good = cost("girl_good")
    for name in ids:
        a = al[name]
        if name == "boy_wrong_dance":
            continue
        assert a["status"] == "aligned" and a["scorable"] is True, (name, a["status"])
        assert a["version"] == "align-1"
    wrong = cost("boy_wrong_dance")

    # Invariance. "gap" = share of the distance from the good attempt to a different dance.
    def gap(name: str) -> float:
        return (cost(name) - good) / (wrong - good)

    assert good < 0.12
    for name in ("girl_shifted", "girl_speed_0_9x", "girl_speed_1_1x", "girl_late_0_4s"):
        assert cost(name) < good + 0.03, (name, cost(name), good)  # position + speed: ~free
    # Smaller pictures are measured less precisely by the pose model itself (the scale-free
    # joint-angle and lean errors grow too, ~2x at 80 % and ~4x at 60 % size), and the
    # reference crops the hips at the frame edge. They stay far nearer the good attempt than
    # a different dance. Measured 2026-11-27: zoom 0.8 gap 0.21, 60 % gap 0.34.
    assert gap("girl_zoom_0_8") < 0.3, gap("girl_zoom_0_8")
    assert gap("girl_scaled_translated") < 0.45, gap("girl_scaled_translated")
    for name in ("girl_shifted", "girl_zoom_0_8", "girl_scaled_translated"):
        assert 0.75 < al[name]["body_size_factor"] < 1.33, name
    # ... while timing is preserved, not erased.
    sp = {n: al[n]["timing"]["speed_ratio"] for n in ("girl_speed_0_9x", "girl_speed_1_1x")}
    assert sp["girl_speed_0_9x"] == pytest.approx(1 / 0.9, abs=0.04), sp
    assert sp["girl_speed_1_1x"] == pytest.approx(1 / 1.1, abs=0.04), sp
    for n in sp:
        assert al[n]["summary"]["equal_time_cost"] > cost(n) + 0.05  # naive pairing is worse
    assert al["girl_good"]["timing"]["speed_ratio"] == pytest.approx(1.0, abs=0.03)
    assert abs(al["girl_good"]["timing"]["median_offset_s"]) <= 0.09
    assert al["girl_late_0_4s"]["timing"]["median_offset_s"] == pytest.approx(0.4, abs=0.1)

    # Mirroring: detected and recorded; without it the flipped attempt would look wrong.
    m = al["girl_mirrored"]["mirror"]
    assert m["chosen"] == "mirrored" and m["decision"] == "clear", m
    assert m["mean_cost"]["direct"] > 3 * cost("girl_mirrored")  # wrong-side limbs stand out
    assert gap("girl_mirrored") < 0.35, gap("girl_mirrored")  # hflip is re-measured too
    assert (m["mean_cost"]["direct"] - good) / (wrong - good) > 1.0  # wrong side ≈ wrong dance
    for n in ids:
        if n.startswith("girl_") and n != "girl_mirrored":
            assert al[n]["mirror"]["chosen"] == "direct", n

    # Missing movement: the 4 s freeze (5-9 s of the reference) is reported there.
    miss = al["girl_missing_middle"]["missing_spans"]
    assert any(lo < 8.5 and hi > 5.5 for lo, hi in miss), miss
    assert all(lo >= 4.5 for lo, _ in miss), miss

    # Occlusion is masked, never scored as wrong.
    masked = al["girl_occluded"]["masked_spans"]
    assert any(lo <= 5.6 and hi >= 7.5 for lo, hi in masked), masked
    occ_frames = [f for f in al["girl_occluded"]["frames"] if 5.6 <= f["ref_t"] <= 7.4]
    assert occ_frames and all(f["cost"] is None for f in occ_frames)

    # A different dance is clearly worse than every girl variant.
    worst_girl = max(cost(n) for n in ids if n.startswith("girl_"))
    assert wrong > worst_girl + 0.2, (wrong, worst_girl)

    # A section attempt is aligned against that section's window of the reference.
    sec = alignment(real, auth, sec_id)["alignment"]
    assert sec["window"]["segment_id"] == sections[1]["id"]
    assert sec["window"]["start"] == pytest.approx(sections[1]["start"], abs=1e-3)
    assert sec["frames"][0]["ref_src_t"] >= sections[1]["start"] - 1e-3
    assert sec["status"] == "aligned"
    assert sec["warp"]["learner_start_s"] == pytest.approx(0.0, abs=0.25)
    assert abs(sec["timing"]["median_offset_s"]) <= 0.1
    assert sec["summary"]["mean_cost"] < good + 0.05

    # Moving the section's boundary invalidates its cached alignment.
    moved = round((sections[1]["start"] + 0.5) * 24) / 24
    body = [
        {"id": s["id"], "start": s["start"], "end": s["end"], "title": s["title"]} for s in sections
    ]
    body[0]["end"] = body[1]["start"] = moved
    res = real.patch(f"/api/projects/{pid}/segments", headers=auth, json={"sections": body})
    assert res.status_code == 200, res.text
    redo = alignment(real, auth, sec_id)
    assert redo["cached"] is False
    assert redo["alignment"]["window"]["start"] == pytest.approx(moved, abs=1e-3)


def test_alignment_refusals_are_honest(
    real: TestClient,  # noqa: F811
    auth: dict[str, str],  # noqa: F811
) -> None:
    project = analysed_girl(real, auth)
    pid = project["id"]
    queued = attempt(real, auth, pid, "girl_good")
    res = real.get(f"/api/practice-sessions/{queued['id']}/alignment", headers=auth)
    assert res.status_code == 409 and res.json()["error"]["code"] == "not_analyzed"
    other = {"Authorization": f"Bearer {real.post('/api/session').json()['token']}"}
    res = real.get(f"/api/practice-sessions/{queued['id']}/alignment", headers=other)
    assert res.status_code == 404
    assert run_jobs() == 1
    assert (
        real.get(f"/api/practice-sessions/{queued['id']}/alignment", headers=auth).status_code
        == 200
    )
