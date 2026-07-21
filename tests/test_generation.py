from core.generation import _scene_count_for_duration


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
