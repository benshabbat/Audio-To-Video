from ai.genai_client import parse_json_block


def test_extracts_object_from_surrounding_noise():
    text = 'Sure, here is the JSON:\n{"a": 1, "b": [2, 3]}\nHope that helps!'
    assert parse_json_block(text, "{", "}") == {"a": 1, "b": [2, 3]}


def test_extracts_array_from_surrounding_noise():
    text = 'Scenes:\n[{"title": "Intro"}, {"title": "End"}]\nDone.'
    assert parse_json_block(text, "[", "]") == [{"title": "Intro"}, {"title": "End"}]


def test_returns_none_when_no_span_found():
    assert parse_json_block("no json here at all", "{", "}") is None


def test_returns_none_on_malformed_json():
    assert parse_json_block("prefix {not: valid, json} suffix", "{", "}") is None
