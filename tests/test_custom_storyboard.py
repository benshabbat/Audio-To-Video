import pytest

from web.routes import _parse_custom_storyboard, MAX_CUSTOM_SCENES, MAX_CUSTOM_PROMPT_LENGTH


def test_parses_valid_minimal_storyboard():
    result = _parse_custom_storyboard('[{"image_prompt": "a cute cartoon dog"}]')
    assert result == [{"title": "סצנה 1", "image_prompt": "a cute cartoon dog", "duration_ratio": 1.0}]


def test_parses_valid_full_storyboard():
    raw = '[{"title": "פתיחה", "image_prompt": "opening scene", "duration_ratio": 1.5}]'
    result = _parse_custom_storyboard(raw)
    assert result == [{"title": "פתיחה", "image_prompt": "opening scene", "duration_ratio": 1.5}]


def test_rejects_invalid_json():
    with pytest.raises(ValueError):
        _parse_custom_storyboard("not json at all")


def test_rejects_non_list_json():
    with pytest.raises(ValueError):
        _parse_custom_storyboard('{"title": "not a list"}')


def test_rejects_empty_list():
    with pytest.raises(ValueError):
        _parse_custom_storyboard("[]")


def test_rejects_too_many_scenes():
    scenes = [{"image_prompt": "x"} for _ in range(MAX_CUSTOM_SCENES + 1)]
    import json
    with pytest.raises(ValueError):
        _parse_custom_storyboard(json.dumps(scenes))


def test_rejects_scene_missing_image_prompt():
    with pytest.raises(ValueError):
        _parse_custom_storyboard('[{"title": "no prompt here"}]')


def test_rejects_non_dict_scene_entry():
    with pytest.raises(ValueError):
        _parse_custom_storyboard('["just a string, not an object"]')


def test_rejects_overly_long_image_prompt():
    import json
    long_prompt = "x" * (MAX_CUSTOM_PROMPT_LENGTH + 1)
    with pytest.raises(ValueError):
        _parse_custom_storyboard(json.dumps([{"image_prompt": long_prompt}]))


def test_clamps_invalid_duration_ratio_to_default():
    result = _parse_custom_storyboard('[{"image_prompt": "x", "duration_ratio": -5}]')
    assert result[0]["duration_ratio"] == 1.0

    result = _parse_custom_storyboard('[{"image_prompt": "x", "duration_ratio": 0}]')
    assert result[0]["duration_ratio"] == 1.0

    result = _parse_custom_storyboard('[{"image_prompt": "x", "duration_ratio": "not a number"}]')
    assert result[0]["duration_ratio"] == 1.0
