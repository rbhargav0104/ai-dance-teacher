#!/usr/bin/env python3
"""Generate multi-person fixtures from REAL committed reference footage with FFmpeg
(spec amendment A2: "choose the dancer"). Both Mixkit clips were shot on the same green
backdrop, so two real dancers can be placed side by side, swapped, or chroma-keyed so one
walks across the other. No landmarks are fabricated: each fixture is a real video that goes
through the real pose pipeline like any upload.

Usage: python3 scripts/make_multi_person_fixtures.py   (rewrites fixtures/multi/*.mp4 and the
"multi_person" list in fixtures/fixture_manifest.json; needs ffmpeg on PATH)
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "fixtures"
OUT = FIX / "multi"
GIRL = "mixkit_girl_earphones_28306"
BOY = "mixkit_boy_funny_28289"
BACKDROP = "0x6ef711"  # measured backdrop colour of both clips (110, 247, 17)

ENCODE = ["-an", "-c:v", "libx264", "-preset", "medium", "-crf", "28", "-pix_fmt", "yuv420p",
          "-threads", "1", "-movflags", "+faststart", "-map_metadata", "-1"]
SECONDS = 8

# Inputs: [0] = girl clip, [1] = boy clip. Every output is 640x360 @ 24 fps, 8 s unless noted.
_GIRL_HALF = "[0:v]scale=640:360,crop=320:360:130:0[g]"
_BOY_HALF = "[1:v]scale=640:360,crop=320:360:160:0[b]"

VARIANTS: list[dict[str, str]] = [
    {
        "id": "duo_girl_left",
        "filter": f"{_GIRL_HALF};{_BOY_HALF};[g][b]hstack,fps=24[v]",
        "relationship": "two real dancers side by side for the whole clip (girl left, boy right): "
        "analysis must stop at 'Who should we follow?' with two candidates; following the left "
        "person must reproduce the girl's movement, the right person the boy's.",
    },
    {
        "id": "duo_boy_left",
        "filter": f"{_GIRL_HALF};{_BOY_HALF};[b][g]hstack,fps=24[v]",
        "relationship": "the same two dancers with positions swapped (boy left, girl right): the "
        "left choice must now follow the boy.",
    },
    {
        "id": "duo_girl_leaves",
        "filter": f"{_GIRL_HALF};{_BOY_HALF};[g][b]hstack,fps=24,"
        f"drawbox=x=0:y=0:w=320:h=360:color={BACKDROP}@1:t=fill:enable='between(t,3,5.5)'[v]",
        "relationship": "side by side, but the girl (left) vanishes from 3 s to 5.5 s while the boy "
        "keeps dancing: following the girl must mask 3-5.5 s ('lost the dancer you chose'), "
        "never switch to the boy.",
    },
    {
        "id": "crossing",
        "filter": f"[0:v]scale=640:360,fps=24[bg];[1:v]scale=640:360,fps=24,"
        f"chromakey={BACKDROP}:0.18:0.08[fg];[bg][fg]overlay=x='-220+t*46':y=0:shortest=1[v]",
        "seconds": "10",
        "relationship": "the boy (chroma-keyed, in front) drifts from the left edge to the right "
        "across the girl (behind) and covers her around 3-6 s: whoever is followed is kept or masked while they "
        "overlap, never silently swapped.",
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


def build(variant: dict[str, str], refs: dict[str, dict[str, object]]) -> dict[str, object]:
    seconds = variant.get("seconds", str(SECONDS))
    girl = FIX / str(refs[GIRL]["file"])
    boy = FIX / str(refs[BOY]["file"])
    dest = OUT / f"{variant['id']}.mp4"
    args = ["-i", str(girl), "-i", str(boy), "-filter_complex", variant["filter"],
            "-map", "[v]", "-t", seconds]
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args, *ENCODE,
                    str(dest)], check=True)
    return {
        "id": variant["id"],
        "file": f"multi/{dest.name}",
        "derived_from": [GIRL, BOY],
        "sha256": sha256(dest),
        "bytes": dest.stat().st_size,
        **probe(dest),
        "fps": 24,
        "transform": f"ffmpeg -i {girl.name} -i {boy.name} -filter_complex "
        f"\"{variant['filter']}\" -map [v] -t {seconds} {' '.join(ENCODE)} {dest.name}",
        "expected_relationship": variant["relationship"],
        "license": "Mixkit Free License",
        "generated_by": "scripts/make_multi_person_fixtures.py",
    }


def main() -> int:
    manifest_path = FIX / "fixture_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    refs = {str(r["id"]): r for r in manifest["references"]}
    OUT.mkdir(parents=True, exist_ok=True)
    entries = []
    for v in VARIANTS:
        entry = build(v, refs)
        print(f"{entry['id']}: {entry['duration']} s, {entry['bytes']} bytes")
        entries.append(entry)
    manifest["multi_person"] = entries
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
