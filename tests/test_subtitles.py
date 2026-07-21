from media.subtitles import _srt_timestamp, build_srt


def test_srt_timestamp_formats_hours_minutes_seconds_ms():
    assert _srt_timestamp(3661.5) == "01:01:01,500"


def test_srt_timestamp_clamps_negative_to_zero():
    assert _srt_timestamp(-5) == "00:00:00,000"


def test_build_srt_writes_valid_entries(tmp_path):
    srt_path = tmp_path / "out.srt"
    lines = [
        {"text": "Hello", "start": 0.0, "end": 1.5},
        {"text": "World", "start": 1.5, "end": 3.0},
    ]
    assert build_srt(lines, str(srt_path)) is True
    content = srt_path.read_text(encoding="utf-8")
    assert "Hello" in content
    assert "00:00:00,000 --> 00:00:01,500" in content


def test_build_srt_skips_blank_and_zero_duration_lines(tmp_path):
    srt_path = tmp_path / "out.srt"
    lines = [
        {"text": "  ", "start": 0.0, "end": 1.0},
        {"text": "ok", "start": 1.0, "end": 1.0},
    ]
    assert build_srt(lines, str(srt_path)) is False
    assert not srt_path.exists()
