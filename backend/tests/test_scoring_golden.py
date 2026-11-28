"""Outcome 7 golden-set relationship tests on REAL footage.

Both committed Mixkit references are analysed by the real worker + MediaPipe; every attempt is
a committed FFmpeg variant of real footage (fixtures/attempts, provenance in
fixtures/fixture_manifest.json). Scores come from the versioned scorer through the public
`/report` API. The expected *relationships* (not absolute numbers) live in the manifest under
`scoring_relations`, so the claims and the fixtures stay together (spec 18 'Calibration',
spec 28 'Golden fixtures').
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.test_practice_analysis import ATTEMPTS, attempt
from tests.test_reference_analysis import auth, real, run_jobs  # noqa: F401

MANIFEST = ATTEMPTS.parent / "fixture_manifest.json"
REFERENCES = {"girl": "mixkit_girl_earphones_28306", "boy": "mixkit_boy_funny_28289"}

pytestmark = pytest.mark.skipif(not ATTEMPTS.is_dir(), reason="attempt fixtures missing")


def relations() -> list[dict[str, Any]]:
    rel: list[dict[str, Any]] = json.loads(MANIFEST.read_text())["scoring_relations"]
    return rel


def metric(report: dict[str, Any], name: str) -> float:
    if name == "overall":
        v = report["overall"]
    elif name.startswith("coverage."):
        v = report["coverage"][name.split(".", 1)[1]]
    else:
        v = report["components"][name]
    assert isinstance(v, int | float), (name, report["status"], report.get("reason"))
    return float(v)


def check(rel: dict[str, Any], reports: dict[str, dict[str, Any]]) -> None:
    """Evaluate one manifest relation. Raises AssertionError with the measured numbers."""
    ref = rel["reference"]

    def rep(att: str) -> dict[str, Any]:
        return reports[f"{ref}:{att}"]

    kind, m = rel["type"], rel.get("metric", "overall")
    margin = float(rel.get("margin", 0))
    a = rep(rel["a"])
    if kind == "highest":
        others = [metric(rep(o), m) for o in rel["others"]]
        assert metric(a, m) >= max(others) + margin, (rel["id"], metric(a, m), others)
    elif kind == "within":
        va, vb = metric(a, m), metric(rep(rel["b"]), m)
        assert abs(va - vb) <= margin, (rel["id"], va, vb)
    elif kind == "lower":
        va, vb = metric(a, m), metric(rep(rel["b"]), m)
        assert va <= vb - margin, (rel["id"], va, vb)
    elif kind == "drops_more":  # a vs baseline b: `metric` drops more than `than`
        b = rep(rel["b"])
        d1 = metric(b, m) - metric(a, m)
        d2 = metric(b, rel["than"]) - metric(a, rel["than"])
        assert d1 >= d2 + margin, (rel["id"], d1, d2)
    elif kind == "below":
        assert metric(a, m) <= margin, (rel["id"], metric(a, m))
    elif kind == "warning":
        assert rel["has"] in a["warnings"], (rel["id"], a["warnings"])
    elif kind == "status":
        assert a["status"] in rel["in"], (rel["id"], a["status"], a.get("reason"))
    else:  # pragma: no cover - manifest typo
        raise AssertionError(f"unknown relation type {kind}")


def test_golden_scoring_relationships_on_real_footage(
    real: TestClient,  # noqa: F811
    auth: dict[str, str],  # noqa: F811
) -> None:
    rels = relations()
    wanted: dict[str, set[str]] = {}
    for rel in rels:
        names = {rel["a"], *rel.get("others", []), *([rel["b"]] if "b" in rel else [])}
        wanted.setdefault(rel["reference"], set()).update(names)
    sessions: dict[str, str] = {}
    jobs = 0
    for ref, names in sorted(wanted.items()):
        res = real.post("/api/projects/sample", headers=auth, json={"sample_id": REFERENCES[ref]})
        assert res.status_code == 201, res.text
        pid = res.json()["id"]
        jobs += run_jobs()  # the reference itself (+ earlier attempts), analysed for real
        assert real.get(f"/api/projects/{pid}", headers=auth).json()["status"] == "analyzed"
        for name in sorted(names):
            sessions[f"{ref}:{name}"] = attempt(real, auth, pid, name)["id"]
    assert jobs + run_jobs() == len(wanted) + len(sessions)

    reports: dict[str, dict[str, Any]] = {}
    for key, sid in sessions.items():
        res = real.get(f"/api/practice-sessions/{sid}/report", headers=auth)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["cached"] is False
        reports[key] = body["report"]
    if os.environ.get("SCORE_DEBUG"):
        for key, r in sorted(reports.items()):
            print(
                f"{key:28s} {r['status']:10s} overall={r['overall']} {r['components']} "
                f"conf={r['coverage']['confidence']} frames={r['coverage']['compared_frames']} "
                f"{r['warnings']}"
            )

    # Every report: versioned, bounded, evidence-linked, coverage block present.
    for key, r in reports.items():
        assert r["version"] == "score-1" and r["alignment_version"] == "align-1", key
        assert r["weights"]["pose"] == 0.30
        for v in [r["overall"], *r["components"].values()]:
            assert v is None or 0 <= v <= 100, key
        cov = r["coverage"]
        for field in (
            "reference_tracking",
            "learner_tracking",
            "compared_frames",
            "visible_joint_coverage",
            "alignment_confidence",
            "confidence",
        ):
            assert field in cov, (key, field)
        if r["overall"] is not None:
            assert r["evidence"]["pose"]["pairs"] > 0
            assert r["moments"]["worst"] and r["moments"]["best"], key
            assert len(r["sections"]) >= 2, key  # full-dance attempt → per-section breakdown

    failures = []
    for rel in rels:
        try:
            check(rel, reports)
        except AssertionError as exc:
            failures.append(f"{rel['id']}: {rel['claim']} -> {exc}")
    assert not failures, "\n".join(failures)

    # A second request is served from the stored row (determinism of the maths itself is
    # covered in test_scoring_math.py).
    sid = sessions["girl:girl_good"]
    again = real.get(f"/api/practice-sessions/{sid}/report", headers=auth).json()
    assert again["cached"] is True and again["report"] == reports["girl:girl_good"]
