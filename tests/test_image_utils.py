import numpy as np

from media.image_utils import hex_to_rgb, blend_colors, apply_ken_burns


def test_hex_to_rgb_six_digit():
    assert hex_to_rgb("#ff8000") == (255, 128, 0)


def test_hex_to_rgb_three_digit_shorthand():
    assert hex_to_rgb("#0f0") == (0, 255, 0)


def test_hex_to_rgb_without_hash_prefix():
    assert hex_to_rgb("000000") == (0, 0, 0)


def test_blend_colors_at_endpoints():
    assert blend_colors((0, 0, 0), (100, 200, 30), 0.0) == (0, 0, 0)
    assert blend_colors((0, 0, 0), (100, 200, 30), 1.0) == (100, 200, 30)


def test_blend_colors_midpoint():
    assert blend_colors((0, 0, 0), (100, 100, 100), 0.5) == (50, 50, 50)


def test_blend_colors_clamps_t_outside_0_1():
    assert blend_colors((0, 0, 0), (100, 100, 100), -5) == (0, 0, 0)
    assert blend_colors((0, 0, 0), (100, 100, 100), 5) == (100, 100, 100)


def test_apply_ken_burns_preserves_frame_shape():
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    result = apply_ken_burns(frame, t=1.0, duration=5.0, zoom_in=True)
    assert result.shape == frame.shape


def test_apply_ken_burns_zoom_out_also_preserves_shape():
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    result = apply_ken_burns(frame, t=2.5, duration=5.0, zoom_in=False)
    assert result.shape == frame.shape
