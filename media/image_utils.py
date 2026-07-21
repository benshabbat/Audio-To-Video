import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ── Font cache ────────────────────────────────────────────────────────────────
_font_cache: dict = {}

_TITLE_FONT_PATHS = [
    "C:/Windows/Fonts/comicbd.ttf",
    "C:/Windows/Fonts/comic.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
]
_NOTE_FONT_PATHS = [
    "C:/Windows/Fonts/seguisym.ttf",   # Best Unicode music-symbol support
    "C:/Windows/Fonts/seguiemj.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def _load_font(paths: list, size: int) -> ImageFont.FreeTypeFont:
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    if key not in _font_cache:
        paths = _TITLE_FONT_PATHS if bold else _TITLE_FONT_PATHS[1:]
        _font_cache[key] = _load_font(paths, size)
    return _font_cache[key]


def get_note_font(size: int) -> ImageFont.FreeTypeFont:
    key = ("note", size)
    if key not in _font_cache:
        _font_cache[key] = _load_font(_NOTE_FONT_PATHS, size)
    return _font_cache[key]


# ── Color helpers ─────────────────────────────────────────────────────────────

def hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def blend_colors(c1: tuple, c2: tuple, t: float) -> tuple:
    t = max(0.0, min(1.0, t))
    return tuple(int(a * (1 - t) + b * t) for a, b in zip(c1, c2))


def create_gradient_frame(
    width: int,
    height: int,
    top: tuple,
    bottom: tuple,
) -> np.ndarray:
    """Return a (height, width, 3) uint8 numpy array with a vertical gradient."""
    t = np.linspace(0.0, 1.0, height, dtype=np.float32)
    r = (top[0] * (1 - t) + bottom[0] * t).astype(np.uint8)
    g = (top[1] * (1 - t) + bottom[1] * t).astype(np.uint8)
    b = (top[2] * (1 - t) + bottom[2] * t).astype(np.uint8)
    col = np.stack([r, g, b], axis=-1)
    # np.repeat already returns a freshly-allocated, contiguous array (not a
    # view), so an extra .copy() here would just be a second full-frame
    # memcpy (~2.7MB at 1280x720) on every single frame for no benefit.
    return np.repeat(col[:, np.newaxis, :], width, axis=1)


# ── Storyboard animation helpers ──────────────────────────────────────────────

def apply_ken_burns(
    image_np: np.ndarray,
    t: float,
    duration: float,
    zoom_in: bool = True,
) -> np.ndarray:
    """
    Apply a slow Ken Burns (zoom + pan) effect to a single frame.
    zoom_in=True  → start wide, slowly zoom in
    zoom_in=False → start zoomed in, slowly pull out
    """
    H, W = image_np.shape[:2]
    t_norm = t / max(duration, 0.001)  # 0 → 1

    scale = (1.0 + 0.12 * t_norm) if zoom_in else (1.12 - 0.12 * t_norm)

    crop_w = int(W / scale)
    crop_h = int(H / scale)

    # Gentle horizontal drift (3% of width)
    drift = 0.03 * t_norm * (1 if zoom_in else -1)
    cx = int(W * (0.5 + drift))
    cy = H // 2

    x1 = max(0, cx - crop_w // 2)
    y1 = max(0, cy - crop_h // 2)
    x2 = min(W, x1 + crop_w)
    y2 = min(H, y1 + crop_h)

    # Clamp both edges
    if x2 - x1 < crop_w:
        x1 = max(0, x2 - crop_w)
    if y2 - y1 < crop_h:
        y1 = max(0, y2 - crop_h)

    cropped = image_np[y1:y2, x1:x2]
    if cropped.shape[0] < 2 or cropped.shape[1] < 2:
        return image_np

    return np.array(Image.fromarray(cropped).resize((W, H), Image.BILINEAR))


def create_placeholder_image(
    title: str,
    color: tuple = (100, 150, 255),
    size: tuple = (1280, 720),
) -> Image.Image:
    """
    Generate a colourful placeholder when Imagen cannot produce an image.
    Shows the scene title centred over a gradient background with decorative rings.
    """
    W, H = size
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)

    # Gradient background
    dark = tuple(int(c * 0.4) for c in color)
    for y in range(H):
        t = y / H
        row = tuple(int(color[i] * (1 - t) + dark[i] * t) for i in range(3))
        draw.line([(0, y), (W, y)], fill=row)

    # Decorative concentric rings
    lighter = tuple(min(255, c + 70) for c in color)
    for i in range(1, 6):
        r = W * i // 10
        draw.ellipse(
            [W // 2 - r, H // 2 - r, W // 2 + r, H // 2 + r],
            outline=lighter,
            width=2,
        )

    # Decorative orbit dots
    for i in range(8):
        angle = i * math.pi / 4
        dx = int(math.cos(angle) * W * 0.3)
        dy = int(math.sin(angle) * H * 0.28)
        dot_c = tuple(min(255, c + 100) for c in color)
        ds = 14
        draw.ellipse(
            [W // 2 + dx - ds, H // 2 + dy - ds, W // 2 + dx + ds, H // 2 + dy + ds],
            fill=dot_c,
        )

    # Title text
    font = get_font(72, bold=True)
    bbox = draw.textbbox((0, 0), title, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx, ty = (W - tw) // 2, (H - th) // 2
    draw.text((tx + 4, ty + 4), title, fill=(0, 0, 0), font=font)
    draw.text((tx, ty), title, fill=(255, 255, 255), font=font)

    return img
