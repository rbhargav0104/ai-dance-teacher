#!/usr/bin/env python3
"""Generate learner-attempt fixtures from REAL committed reference footage with FFmpeg
(docs/SOURCING.md "Learner-attempt fixtures"). No landmarks are fabricated: each variant is
a real video that goes through the real pose pipeline like any learner upload.

Usage: python3 scripts/make_attempt_fixtures.py   (rewrites fixtures/attempts/*.mp4 and the
"attempts" list in fixtures/fixture_manifest.json; needs ffmpeg on PATH)
"""

from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "fixtures"
OUT = FIX / "attempts"
GIRL = "mixkit_girl_earphones_28306"
BOY = "mixkit_boy_funny_28289"
GREEN = "0x5fd900"  # close to the clips' chroma backdrop, so padding reads as more studio

# Small, fast-to-analyse learner clips: 640x360 H.264, 24 fps, no audio.
ENCODE = ["-an", "-c:v", "libx264", "-preset", "medium", "-crf", "28", "-pix_fmt", "yuv420p",
          "-threads", "1", "-movflags", "+faststart", "-map_metadata", "-1"]
BASE = "scale=640:360,fps=24"

VARIANTS: list[dict[str, object]] = [
    {
        "id": "girl_good",
        "reference": GIRL,
        "vf": BASE,
        "relationship": "same performance re-encoded at 640x360: should score highest of all "
        "variants (upper bound).",
    },
    {
        "id": "girl_scaled_translated",
        "reference": GIRL,
        "vf": f"scale=384:216,pad=640:360:232:120:color={GREEN},fps=24",
        "relationship": "same performance at 60% size, shifted right/down: after normalization "
        "pose scores should stay close to girl_good (position/size must not dominate).",
    },
    {
        "id": "girl_late_0_4s",
        "reference": GIRL,
        "vf": f"{BASE},tpad=start_duration=0.4:start_mode=clone",
        "relationship": "same performance starting 0.4 s late (first frame held): pose similar "
        "to good, timing component lower; feedback should say 'late'.",
    },
    {
        "id": "girl_speed_0_9x",
        "reference": GIRL,
        "vf": f"setpts=PTS/0.9,{BASE}",
        "relationship": "same performance played at 0.9x (slower): alignment should pair the "
        "moves; timing component lower than good.",
    },
    {
        "id": "girl_speed_1_1x",
        "reference": GIRL,
        "vf": f"setpts=PTS/1.1,{BASE}",
        "relationship": "same performance played at 1.1x (faster): alignment should pair the "
        "moves; timing component lower than good.",
    },
    {
        "id": "girl_mirrored",
        "reference": GIRL,
        "vf": f"hflip,{BASE}",
        "relationship": "horizontally flipped: direct comparison should differ on left/right "
        "limbs; mirror-aware comparison should match closely.",
    },
    {
        "id": "girl_missing_middle",
        "reference": GIRL,
        "vf": f"{BASE},trim=0:5,setpts=PTS-STARTPTS,tpad=stop_duration=4:stop_mode=clone,"
        "fps=24",
        "relationship": "first 5 s of the performance, then a 4 s freeze, then 9-14 s: the hold "
        "window (5-9 s) should score clearly lower than the rest.",
    },
    {
        "id": "girl_occluded",
        "reference": GIRL,
        "vf": f"{BASE},drawbox=x=0:y=150:w=640:h=210:color=0x303030@1:t=fill:"
        "enable='between(t,5,8)'",
        "relationship": "hips and lower torso covered by a grey band from 5 s to 8 s: those "
        "frames must lose tracking (lower coverage, partial_coverage warning) and be masked, "
        "not scored as wrong.",
    },
    {
        "id": "boy_wrong_dance",
        "reference": GIRL,
        "source": BOY,
        "vf": f"{BASE},trim=0:14,setpts=PTS-STARTPTS",
        "relationship": "a different dance (Mixkit 28289) compared against the girl reference: "
        "should score clearly lower than every girl_* variant.",
    },
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe(path: Path) -> dict[str, float]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    data = json.loads(out)
    s = data["streams"][0]
    return {"width": s["width"], "height": s["height"],
            "duration": round(float(data["format"]["duration"]), 3)}


def build(variant: dict[str, object], refs: dict[str, dict[str, object]]) -> dict[str, object]:
    src_id = str(variant.get("source", variant["reference"]))
    src = FIX / str(refs[src_id]["file"])
    dest = OUT / f"{variant['id']}.mp4"
    if variant["id"] == "girl_missing_middle":
        # [0-5 s] + 4 s hold of the 5 s frame + [9-14 s]
        fc = (
            f"[0:v]{BASE},split=2[a][b];"
            "[a]trim=0:5,setpts=PTS-STARTPTS,tpad=stop_duration=4:stop_mode=clone[p1];"
            "[b]trim=9:14,setpts=PTS-STARTPTS[p2];[p1][p2]concat=n=2:v=1:a=0[v]"
        )
        args = ["-i", str(src), "-filter_complex", fc, "-map", "[v]"]
        transform = f"ffmpeg -i {src.name} -filter_complex \"{fc}\" -map [v]"
    else:
        args = ["-i", str(src), "-vf", str(variant["vf"])]
        transform = f"ffmpeg -i {src.name} -vf \"{variant['vf']}\""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args, *ENCODE, str(dest)]
    subprocess.run(cmd, check=True)
    meta = probe(dest)
    return {
        "id": variant["id"],
        "file": f"attempts/{dest.name}",
        "reference": variant["reference"],
        "derived_from": src_id,
        "sha256": sha256(dest),
        "bytes": dest.stat().st_size,
        **meta,
        "fps": 24,
        "transform": f"{transform} {shlex.join(ENCODE)} {dest.name}",
        "expected_relationship": variant["relationship"],
        "license": refs[src_id]["license"],
        "generated_by": "scripts/make_attempt_fixtures.py",
    }


def main() -> int:
    manifest_path = FIX / "fixture_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    refs = {str(r["id"]): r for r in manifest["references"]}
    OUT.mkdir(parents=True, exist_ok=True)
    attempts = []
    for v in VARIANTS:
        entry = build(v, refs)
        print(f"{entry['id']}: {entry['duration']} s, {entry['bytes']} bytes")
        attempts.append(entry)
    manifest["attempts"] = attempts
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
