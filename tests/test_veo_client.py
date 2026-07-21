from ai.veo_client import _closest_allowed_duration


def test_rounds_to_nearest_allowed_duration():
    assert _closest_allowed_duration(5.5) == 6
    assert _closest_allowed_duration(7.5) == 8


def test_exact_matches_stay_unchanged():
    assert _closest_allowed_duration(4) == 4
    assert _closest_allowed_duration(6) == 6
    assert _closest_allowed_duration(8) == 8


def test_clamps_out_of_range_values():
    assert _closest_allowed_duration(1) == 4
    assert _closest_allowed_duration(100) == 8
