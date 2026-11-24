"""Pure validation rules over FFprobe JSON (no media needed): fps, timing, rotation, formats."""

from __future__ import annotations

from typing import Any

import pytest

from app.media.probe import MediaRejected, check_extension, parse_rate, validate_probe


def probe_json(**overrides: Any) -> dict[str, Any]:
    stream: dict[str, Any] = {
        "codec_type": "video",
        "codec_name": "h264",
        "width": 1280,
        "height": 720,
        "avg_frame_rate": "30000/1001",
        "r_frame_rate": "30000/1001",
    }
    stream.update(overrides.pop("stream", {}))
    data: dict[str, Any] = {
        "streams": [stream],
        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "12.5"},
    }
    data["format"].update(overrides.pop("format", {}))
    data.update(overrides)
    return data


def code_of(data: dict[str, Any], max_duration: float = 120) -> str:
    with pytest.raises(MediaRejected) as exc:
        validate_probe(data, max_duration=max_duration)
    return exc.value.code


def test_valid_probe() -> None:
    r = validate_probe(probe_json(), max_duration=120)
    assert (r.width, r.height, r.duration) == (1280, 720, 12.5)
    assert r.fps == pytest.approx(29.97, abs=0.01)
    assert r.has_audio is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [("30/1", 30.0), ("24000/1001", 23.976), ("0/0", None), ("", None), ("abc", None),
     ("-5/1", None), (None, None), ("1/0", None)],
)  # fmt: skip
def test_parse_rate(value: object, expected: float | None) -> None:
    got = parse_rate(value)
    assert (got is None) if expected is None else got == pytest.approx(expected, abs=1e-3)


def test_falls_back_to_r_frame_rate() -> None:
    r = validate_probe(
        probe_json(stream={"avg_frame_rate": "0/0", "r_frame_rate": "25/1"}), max_duration=120
    )
    assert r.fps == 25


@pytest.mark.parametrize("rate", ["0/0", "500/1", "1/2"])
def test_invalid_fps(rate: str) -> None:
    assert (
        code_of(probe_json(stream={"avg_frame_rate": rate, "r_frame_rate": rate}))
        == "invalid_frame_rate"
    )


@pytest.mark.parametrize("duration", ["N/A", "nan", "inf", "0", "-3"])
def test_invalid_timing(duration: str) -> None:
    assert code_of(probe_json(format={"duration": duration})) == "invalid_timing"


def test_duration_bounds() -> None:
    assert code_of(probe_json(format={"duration": "0.5"})) == "too_short"
    assert code_of(probe_json(format={"duration": "121"})) == "too_long"


def test_dimension_bounds() -> None:
    assert code_of(probe_json(stream={"width": 100, "height": 720})) == "dimensions_too_small"
    assert code_of(probe_json(stream={"width": 8000, "height": 720})) == "dimensions_too_large"
    assert code_of(probe_json(stream={"width": 0, "height": 0})) == "unreadable_media"


def test_audio_only_and_cover_art_only() -> None:
    audio = {"codec_type": "audio", "codec_name": "aac"}
    assert code_of(probe_json(streams=[audio])) == "audio_only"
    cover = {"codec_type": "video", "codec_name": "mjpeg", "disposition": {"attached_pic": 1}}
    assert code_of(probe_json(streams=[audio, cover])) == "audio_only"


def test_non_video_container_rejected() -> None:
    assert code_of(probe_json(format={"format_name": "gif"})) == "unsupported_type"


def test_rotation_swaps_display_dimensions() -> None:
    r = validate_probe(probe_json(stream={"side_data_list": [{"rotation": -90}]}), max_duration=120)
    assert r.rotation == 270
    assert (r.display_width, r.display_height) == (720, 1280)


@pytest.mark.parametrize("name", ["a.MP4", "b.mov", "c.webm"])
def test_accepted_extensions(name: str) -> None:
    assert check_extension(name).startswith(".")


@pytest.mark.parametrize("name", ["a.avi", "b", "", None, "x.mp4.exe", "../x.mkv"])
def test_rejected_extensions(name: str | None) -> None:
    with pytest.raises(MediaRejected) as exc:
        check_extension(name)
    assert exc.value.status_code == 415


def test_filename_cleaning() -> None:
    from app.services.intake import clean_filename, title_from

    assert clean_filename("../../etc/pa\x00ss wd.mp4") == "pass wd.mp4"
    assert clean_filename("C:\\Users\\me\\dance.mov") == "dance.mov"
    assert title_from(None, "my_cool-dance.mp4") == "my cool dance"
    assert title_from("  x  ", "y.mp4") == "x"
