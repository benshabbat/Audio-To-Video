import pytest

from core.generation import _scene_count_for_duration, _reconcile_scene_durations


def test_short_song_gets_floor_of_two_scenes():
    assert _scene_count_for_duration(6.0) == 2


def test_song_just_long_enough_for_two_scenes():
    assert _scene_count_for_duration(10.0) == 2


def test_song_long_enough_for_three_scenes():
    assert _scene_count_for_duration(15.0) == 3


def test_typical_song_length_caps_at_default_six():
    assert _scene_count_for_duration(180.0) == 6


def test_very_short_duration_still_floors_at_two():
    assert _scene_count_for_duration(0.5) == 2


def test_reconcile_scales_durations_to_sum_exactly_to_song_duration():
    result = _reconcile_scene_durations([10, 20, 30], song_duration=90.0)
    assert result == pytest.approx([15.0, 30.0, 45.0])
    assert sum(result) == pytest.approx(90.0)


def test_reconcile_never_produces_zero_or_negative_scene():
    # A last scene whose own Gemini-reported end lines up with (or past) the
    # real song end previously drove scene_durations[-1] to zero/negative,
    # crashing moviepy's with_speed_scaled — proportional scaling can't do
    # that as long as every raw input is positive.
    result = _reconcile_scene_durations([5, 5, 0.01], song_duration=8.0)
    assert all(d > 0 for d in result)
    assert sum(result) == pytest.approx(8.0)


def test_reconcile_clamps_hallucinated_zero_or_negative_raw_duration():
    # A scene with a hallucinated 0 or negative duration_ratio/timestamp gap
    # must not stay zero/negative after reconciliation.
    result = _reconcile_scene_durations([10, 0, -5], song_duration=60.0)
    assert all(d > 0 for d in result)
    assert sum(result) == pytest.approx(60.0)


def test_reconcile_does_not_dump_all_drift_onto_last_scene():
    # Simulates Gemini returning more scenes than requested and the tail
    # getting truncated: the kept last scene's own reported span is tiny,
    # but a large chunk of the song is still unaccounted for. The old
    # "dump the drift onto the last scene" logic would have driven the
    # last scene to 0.3 + (100 - 40.3) = 60s, a wildly disproportionate,
    # visibly frozen/slow-motion stretch. Proportional scaling instead
    # keeps every scene's share of the total the same as its raw input.
    # (last value kept above MIN_RAW_SCENE_SECONDS so the floor-clamp doesn't
    # also affect the ratio being checked here)
    raw = [20, 20, 1.0]
    result = _reconcile_scene_durations(raw, song_duration=100.0)
    assert result[-1] < 60.0 - 1.0  # nowhere near the old dump-onto-last outcome
    assert result[-1] / result[0] == pytest.approx(raw[-1] / raw[0])
    assert sum(result) == pytest.approx(100.0)
