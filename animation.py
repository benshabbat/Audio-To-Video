import math
import random
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
    return np.repeat(col[:, np.newaxis, :], width, axis=1).copy()


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


# ── StoryboardAnimator ────────────────────────────────────────────────────────

class StoryboardAnimator:
    """
    Animates between AI-generated scene images using:
    - Ken Burns effect (slow zoom + pan) per scene
    - Crossfade transitions between scenes
    - Subtle star + musical-note particle overlay
    - Song title bar (first 5 s, fades out)
    """

    TRANSITION_DURATION = 0.9  # seconds for crossfade

    def __init__(
        self,
        images: list,
        scene_durations: list,
        title: str,
        size: tuple = (1280, 720),
    ):
        self.width, self.height = size
        self.title = title
        self.n_scenes = len(images)
        self.durations = scene_durations

        # Cumulative scene start times
        self.scene_starts = [0.0]
        for d in scene_durations[:-1]:
            self.scene_starts.append(self.scene_starts[-1] + d)

        # Pre-process images to numpy arrays at target resolution
        self.images_np: list = []
        for img in images:
            arr = np.array(img.resize(size, Image.LANCZOS))
            self.images_np.append(arr)

        # Alternate Ken Burns direction per scene
        self.zoom_in = [i % 2 == 0 for i in range(self.n_scenes)]

        # Subtle particle system
        rng = random.Random(42)
        self.stars = [
            {
                "x": rng.random(),
                "y": rng.random(),
                "size": rng.randint(2, 8),
                "speed": rng.uniform(1.5, 4.0),
                "phase": rng.uniform(0, 2 * math.pi),
                "color": rng.choice(
                    [(255, 255, 200), (255, 255, 255), (220, 255, 220)]
                ),
            }
            for _ in range(28)
        ]
        self.notes = [
            {
                "x": rng.random(),
                "y": rng.random(),
                "speed": rng.uniform(0.04, 0.10),
                "symbol": rng.choice(["♪", "♫", "♬", "♩"]),
                "phase": rng.uniform(0, 2 * math.pi),
            }
            for _ in range(6)
        ]

        # Pre-load fonts
        title_size = 80 if len(title) <= 15 else 64 if len(title) <= 25 else 52
        self.title_font = get_font(title_size, bold=True)
        self.note_font = get_note_font(30)

        dummy = Image.new("RGB", (10, 10))
        bbox = ImageDraw.Draw(dummy).textbbox((0, 0), title, font=self.title_font)
        self.title_w = bbox[2] - bbox[0]
        self.title_h = bbox[3] - bbox[1]

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _scene_at(self, t: float) -> tuple:
        """Return (scene_idx, t_within_scene)."""
        for i in range(self.n_scenes - 1, -1, -1):
            if t >= self.scene_starts[i]:
                return i, t - self.scene_starts[i]
        return 0, 0.0

    # ── Main frame generator ──────────────────────────────────────────────────

    def make_frame(self, t: float) -> np.ndarray:
        scene_idx, scene_t = self._scene_at(t)
        scene_dur = self.durations[scene_idx]

        # ── Ken Burns on current scene ────────────────────────────────────────
        base = apply_ken_burns(
            self.images_np[scene_idx], scene_t, scene_dur, self.zoom_in[scene_idx]
        )

        # ── Crossfade to next scene ────────────────────────────────────────────
        if scene_idx < self.n_scenes - 1:
            time_to_end = scene_dur - scene_t
            # Effective transition: don't exceed half of either adjacent scene
            eff_trans = min(
                self.TRANSITION_DURATION,
                scene_dur * 0.45,
                self.durations[scene_idx + 1] * 0.45,
            )
            if time_to_end < eff_trans:
                alpha = (eff_trans - time_to_end) / eff_trans
                nxt = apply_ken_burns(
                    self.images_np[scene_idx + 1],
                    0.0,
                    self.durations[scene_idx + 1],
                    self.zoom_in[scene_idx + 1],
                )
                base = (base * (1 - alpha) + nxt * alpha).astype(np.uint8)

        # ── Title bar overlay (first 5 s, fade out over last 2 s) ─────────────
        img = Image.fromarray(base).convert("RGBA")

        if t < 5.0:
            fade = 1.0 - max(0.0, (t - 3.0) / 2.0)
            bar_h = self.title_h + 44
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            ovd = ImageDraw.Draw(overlay)
            ovd.rectangle([0, 0, self.width, bar_h], fill=(0, 0, 0, int(165 * fade)))
            img = Image.alpha_composite(img, overlay)

            draw = ImageDraw.Draw(img)
            tx = (self.width - self.title_w) // 2
            ty = 22
            fc = int(255 * fade)
            draw.text((tx + 3, ty + 3), self.title, fill=(20, 20, 20, fc), font=self.title_font)
            draw.text((tx, ty), self.title, fill=(255, 255, 240, fc), font=self.title_font)

        # ── Particle overlay ──────────────────────────────────────────────────
        particles = Image.new("RGBA", img.size, (0, 0, 0, 0))
        pdraw = ImageDraw.Draw(particles)

        for s in self.stars:
            twinkle = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(t * s["speed"] + s["phase"]))
            size = max(1, int(s["size"] * twinkle))
            sx = int(s["x"] * self.width)
            sy = int(s["y"] * self.height)
            r, g, b = s["color"]
            pdraw.ellipse(
                [sx - size, sy - size, sx + size, sy + size],
                fill=(r, g, b, int(180 * twinkle)),
            )

        for note in self.notes:
            y_f = (note["y"] - t * note["speed"]) % 1.0
            ny = int(y_f * self.height)
            nx = int(note["x"] * self.width + math.sin(t * 0.7 + note["phase"]) * 22)
            pdraw.text((nx, ny), note["symbol"], fill=(255, 255, 200, 140), font=self.note_font)

        img = Image.alpha_composite(img, particles)
        return np.array(img.convert("RGB"))


# ── ChildrenAnimator (procedural fallback) ────────────────────────────────────

class ChildrenAnimator:
    """Generates per-frame numpy arrays for a colourful children's-song video."""

    def __init__(
        self,
        title: str,
        duration: float,
        colors: list,
        size: tuple = (1280, 720),
    ):
        self.title = title
        self.duration = duration
        self.width, self.height = size

        # Parse colors
        self.colors: list = []
        for c in colors:
            try:
                self.colors.append(hex_to_rgb(c) if isinstance(c, str) else tuple(c))
            except Exception:
                pass
        if not self.colors:
            self.colors = [
                (255, 107, 107),
                (255, 217, 61),
                (107, 203, 119),
                (77, 150, 255),
                (199, 125, 255),
            ]

        rng = random.Random(42)

        STAR_COLORS = [
            (255, 255, 150), (255, 200, 100),
            (255, 255, 255), (200, 255, 200), (150, 200, 255),
        ]
        self.stars = [
            {
                "x": rng.random(),
                "y": rng.random(),
                "size": rng.randint(3, 14),
                "speed": rng.uniform(1.0, 4.5),
                "phase": rng.uniform(0, 2 * math.pi),
                "color": rng.choice(STAR_COLORS),
            }
            for _ in range(60)
        ]

        self.bubbles = [
            {
                "x": rng.random(),
                "y": rng.random(),
                "size": rng.randint(8, 35),
                "speed": rng.uniform(0.02, 0.08),
                "wobble": rng.uniform(0.3, 1.5),
                "phase": rng.uniform(0, 2 * math.pi),
                "color": rng.choice(self.colors + [(255, 255, 255)]),
            }
            for _ in range(20)
        ]

        self.notes = [
            {
                "x": rng.random(),
                "y": rng.random(),
                "speed": rng.uniform(0.04, 0.12),
                "symbol": rng.choice(["♪", "♫", "♩", "♬"]),
                "color": rng.choice(
                    [(255, 255, 200), (255, 255, 255), (200, 255, 255)]
                ),
                "phase": rng.uniform(0, 2 * math.pi),
                "size": rng.randint(28, 52),
            }
            for _ in range(12)
        ]

        # Pre-load fonts
        title_size = (
            96 if len(title) <= 10
            else 80 if len(title) <= 18
            else 64 if len(title) <= 28
            else 52
        )
        self.title_font = get_font(title_size, bold=True)

        dummy = Image.new("RGB", (10, 10))
        bbox = ImageDraw.Draw(dummy).textbbox((0, 0), self.title, font=self.title_font)
        self.title_w = bbox[2] - bbox[0]
        self.title_h = bbox[3] - bbox[1]
        self.title_x = (self.width - self.title_w) // 2
        self.title_y = self.height // 2 - self.title_h // 2 - 20

    def _cycle_color(self, t: float, speed: float = 1.0) -> tuple:
        phase = (t * speed) % len(self.colors)
        c1 = self.colors[int(phase) % len(self.colors)]
        c2 = self.colors[(int(phase) + 1) % len(self.colors)]
        return blend_colors(c1, c2, phase - int(phase))

    def _bg_colors(self, t: float) -> tuple:
        mid = self._cycle_color(t, speed=1 / 8)
        top = tuple(min(255, int(c * 0.85 + 40)) for c in mid)
        bot = tuple(int(c * 0.45) for c in mid)
        return top, bot

    def make_frame(self, t: float) -> np.ndarray:
        top, bot = self._bg_colors(t)
        frame = create_gradient_frame(self.width, self.height, top, bot)
        img = Image.fromarray(frame, "RGB")
        draw = ImageDraw.Draw(img)

        # Stars
        for s in self.stars:
            twinkle = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(t * s["speed"] + s["phase"]))
            size = max(1, int(s["size"] * twinkle))
            sx, sy = int(s["x"] * self.width), int(s["y"] * self.height)
            draw.ellipse([sx - size, sy - size, sx + size, sy + size], fill=s["color"])
            if size > 6:
                r, g, b = s["color"]
                draw.line([sx - size * 2, sy, sx + size * 2, sy], fill=(r, g, b), width=1)
                draw.line([sx, sy - size * 2, sx, sy + size * 2], fill=(r, g, b), width=1)

        # Bubbles
        for bub in self.bubbles:
            y_f = (bub["y"] - t * bub["speed"]) % 1.0
            by = int(y_f * self.height)
            bx = int(
                bub["x"] * self.width
                + math.sin(t * bub["wobble"] + bub["phase"]) * 25
            )
            bs = bub["size"]
            r, g, b = bub["color"]
            fill_c = (min(255, r + 80), min(255, g + 80), min(255, b + 80))
            draw.ellipse(
                [bx - bs, by - bs, bx + bs, by + bs],
                fill=fill_c, outline=(r, g, b), width=2,
            )

        # Musical notes
        for note in self.notes:
            y_f = (note["y"] - t * note["speed"]) % 1.0
            ny = int(y_f * self.height)
            nx = int(note["x"] * self.width + math.sin(t * 0.7 + note["phase"]) * 25)
            nfont = get_note_font(note["size"])
            draw.text((nx, ny), note["symbol"], fill=note["color"], font=nfont)

        # Equalizer bars
        num_bars = 48
        bar_spacing = (self.width - 40) // num_bars
        bar_w = max(2, bar_spacing - 3)
        base_y = self.height - 15
        for i in range(num_bars):
            phase = i * 0.35 + t * 5
            bar_h = int(10 + 65 * abs(math.sin(phase)) * abs(math.cos(phase * 0.7)))
            bx = 20 + i * bar_spacing
            bar_color = self._cycle_color(t * 0.1 + i / num_bars, speed=len(self.colors))
            draw.rectangle([bx, base_y - bar_h, bx + bar_w, base_y], fill=bar_color)

        # Title (semi-transparent pill + text)
        wave_y = int(math.sin(t * 1.8) * 12)
        tx, ty = self.title_x, self.title_y + wave_y
        pad = 22

        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ovd = ImageDraw.Draw(overlay)
        ovd.rounded_rectangle(
            [tx - pad, ty - pad, tx + self.title_w + pad, ty + self.title_h + pad],
            radius=24,
            fill=(0, 0, 30, 170),
        )
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

        draw.text((tx + 4, ty + 4), self.title, fill=(10, 10, 30), font=self.title_font)
        title_color = tuple(
            min(255, int(c * 0.6 + 120)) for c in self._cycle_color(t * 0.3)
        )
        title_color = tuple(min(255, c + 80) for c in title_color)
        draw.text((tx, ty), self.title, fill=title_color, font=self.title_font)

        # Orbiting dots
        cx = self.width // 2
        cy = ty + self.title_h // 2
        orx = self.title_w // 2 + 45
        ory = self.title_h // 2 + 22
        for i in range(5):
            angle = t * 1.5 + i * (2 * math.pi / 5)
            dx, dy = int(math.cos(angle) * orx), int(math.sin(angle) * ory)
            dot_c = self.colors[i % len(self.colors)]
            dsize = 8
            draw.ellipse(
                [cx + dx - dsize, cy + dy - dsize, cx + dx + dsize, cy + dy + dsize],
                fill=dot_c,
            )

        return np.array(img)


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


def _load_font(paths: list[str], size: int) -> ImageFont.FreeTypeFont:
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

def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def blend_colors(
    c1: tuple[int, int, int], c2: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(int(a * (1 - t) + b * t) for a, b in zip(c1, c2))  # type: ignore[return-value]


def create_gradient_frame(
    width: int,
    height: int,
    top: tuple[int, int, int],
    bottom: tuple[int, int, int],
) -> np.ndarray:
    """Return a (height, width, 3) uint8 numpy array with a vertical gradient."""
    t = np.linspace(0.0, 1.0, height, dtype=np.float32)
    r = (top[0] * (1 - t) + bottom[0] * t).astype(np.uint8)
    g = (top[1] * (1 - t) + bottom[1] * t).astype(np.uint8)
    b = (top[2] * (1 - t) + bottom[2] * t).astype(np.uint8)
    col = np.stack([r, g, b], axis=-1)          # (height, 3)
    return np.repeat(col[:, np.newaxis, :], width, axis=1).copy()  # (height, width, 3)


# ── Main animator class ───────────────────────────────────────────────────────

class ChildrenAnimator:
    """Generates per-frame numpy arrays for a colourful children's-song video."""

    def __init__(
        self,
        title: str,
        duration: float,
        colors: list,
        size: tuple[int, int] = (1280, 720),
    ):
        self.title = title
        self.duration = duration
        self.width, self.height = size

        # Parse colors
        self.colors: list[tuple[int, int, int]] = []
        for c in colors:
            try:
                self.colors.append(hex_to_rgb(c) if isinstance(c, str) else tuple(c))
            except Exception:
                pass
        if not self.colors:
            self.colors = [
                (255, 107, 107),
                (255, 217, 61),
                (107, 203, 119),
                (77, 150, 255),
                (199, 125, 255),
            ]

        rng = random.Random(42)

        STAR_COLORS = [
            (255, 255, 150), (255, 200, 100),
            (255, 255, 255), (200, 255, 200), (150, 200, 255),
        ]
        self.stars = [
            {
                "x": rng.random(),
                "y": rng.random(),
                "size": rng.randint(3, 14),
                "speed": rng.uniform(1.0, 4.5),
                "phase": rng.uniform(0, 2 * math.pi),
                "color": rng.choice(STAR_COLORS),
            }
            for _ in range(60)
        ]

        self.bubbles = [
            {
                "x": rng.random(),
                "y": rng.random(),
                "size": rng.randint(8, 35),
                "speed": rng.uniform(0.02, 0.08),
                "wobble": rng.uniform(0.3, 1.5),
                "phase": rng.uniform(0, 2 * math.pi),
                "color": rng.choice(self.colors + [(255, 255, 255)]),
            }
            for _ in range(20)
        ]

        self.notes = [
            {
                "x": rng.random(),
                "y": rng.random(),
                "speed": rng.uniform(0.04, 0.12),
                "symbol": rng.choice(["♪", "♫", "♩", "♬"]),
                "color": rng.choice(
                    [(255, 255, 200), (255, 255, 255), (200, 255, 255)]
                ),
                "phase": rng.uniform(0, 2 * math.pi),
                "size": rng.randint(28, 52),
            }
            for _ in range(12)
        ]

        # Pre-load fonts
        title_size = (
            96 if len(title) <= 10
            else 80 if len(title) <= 18
            else 64 if len(title) <= 28
            else 52
        )
        self.title_font = get_font(title_size, bold=True)

        # Measure title dimensions once
        dummy = Image.new("RGB", (10, 10))
        bbox = ImageDraw.Draw(dummy).textbbox((0, 0), self.title, font=self.title_font)
        self.title_w = bbox[2] - bbox[0]
        self.title_h = bbox[3] - bbox[1]
        self.title_x = (self.width - self.title_w) // 2
        self.title_y = self.height // 2 - self.title_h // 2 - 20

    # ── Private helpers ───────────────────────────────────────────────────────

    def _cycle_color(self, t: float, speed: float = 1.0) -> tuple[int, int, int]:
        phase = (t * speed) % len(self.colors)
        c1 = self.colors[int(phase) % len(self.colors)]
        c2 = self.colors[(int(phase) + 1) % len(self.colors)]
        return blend_colors(c1, c2, phase - int(phase))

    def _bg_colors(self, t: float) -> tuple[tuple, tuple]:
        mid = self._cycle_color(t, speed=1 / 8)
        top = tuple(min(255, int(c * 0.85 + 40)) for c in mid)
        bot = tuple(int(c * 0.45) for c in mid)
        return top, bot  # type: ignore[return-value]

    # ── Public frame generator ────────────────────────────────────────────────

    def make_frame(self, t: float) -> np.ndarray:
        """Called by moviepy for every frame; returns (H, W, 3) uint8 array."""
        top, bot = self._bg_colors(t)
        frame = create_gradient_frame(self.width, self.height, top, bot)
        img = Image.fromarray(frame, "RGB")
        draw = ImageDraw.Draw(img)

        # ── Stars ─────────────────────────────────────────────────────────────
        for s in self.stars:
            twinkle = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(t * s["speed"] + s["phase"]))
            size = max(1, int(s["size"] * twinkle))
            sx, sy = int(s["x"] * self.width), int(s["y"] * self.height)
            draw.ellipse([sx - size, sy - size, sx + size, sy + size], fill=s["color"])
            if size > 6:
                r, g, b = s["color"]
                draw.line([sx - size * 2, sy, sx + size * 2, sy], fill=(r, g, b), width=1)
                draw.line([sx, sy - size * 2, sx, sy + size * 2], fill=(r, g, b), width=1)

        # ── Bubbles ───────────────────────────────────────────────────────────
        for bub in self.bubbles:
            y_f = (bub["y"] - t * bub["speed"]) % 1.0
            by = int(y_f * self.height)
            bx = int(bub["x"] * self.width + math.sin(t * bub["wobble"] + bub["phase"]) * 25)
            bs = bub["size"]
            r, g, b = bub["color"]
            fill_c = (min(255, r + 80), min(255, g + 80), min(255, b + 80))
            draw.ellipse(
                [bx - bs, by - bs, bx + bs, by + bs],
                fill=fill_c, outline=(r, g, b), width=2,
            )

        # ── Musical notes ─────────────────────────────────────────────────────
        for note in self.notes:
            y_f = (note["y"] - t * note["speed"]) % 1.0
            ny = int(y_f * self.height)
            nx = int(note["x"] * self.width + math.sin(t * 0.7 + note["phase"]) * 25)
            nfont = get_note_font(note["size"])
            draw.text((nx, ny), note["symbol"], fill=note["color"], font=nfont)

        # ── Equalizer bars ────────────────────────────────────────────────────
        num_bars = 48
        bar_spacing = (self.width - 40) // num_bars
        bar_w = max(2, bar_spacing - 3)
        base_y = self.height - 15
        for i in range(num_bars):
            phase = i * 0.35 + t * 5
            bar_h = int(10 + 65 * abs(math.sin(phase)) * abs(math.cos(phase * 0.7)))
            bx = 20 + i * bar_spacing
            bar_color = self._cycle_color(t * 0.1 + i / num_bars, speed=len(self.colors))
            draw.rectangle([bx, base_y - bar_h, bx + bar_w, base_y], fill=bar_color)

        # ── Title box + text ──────────────────────────────────────────────────
        wave_y = int(math.sin(t * 1.8) * 12)
        tx, ty = self.title_x, self.title_y + wave_y
        pad = 22

        # Semi-opaque dark pill behind title (drawn by compositing)
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ovd = ImageDraw.Draw(overlay)
        ovd.rounded_rectangle(
            [tx - pad, ty - pad, tx + self.title_w + pad, ty + self.title_h + pad],
            radius=24,
            fill=(0, 0, 30, 170),
        )
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

        # Shadow
        draw.text((tx + 4, ty + 4), self.title, fill=(10, 10, 30), font=self.title_font)
        # Title text
        title_color = tuple(
            min(255, int(c * 0.6 + 120)) for c in self._cycle_color(t * 0.3)
        )
        title_color = tuple(min(255, c + 80) for c in title_color)  # type: ignore[assignment]
        draw.text((tx, ty), self.title, fill=title_color, font=self.title_font)

        # Orbiting dots around title
        cx = self.width // 2
        cy = ty + self.title_h // 2
        orx = self.title_w // 2 + 45
        ory = self.title_h // 2 + 22
        for i in range(5):
            angle = t * 1.5 + i * (2 * math.pi / 5)
            dx, dy = int(math.cos(angle) * orx), int(math.sin(angle) * ory)
            dot_c = self.colors[i % len(self.colors)]
            dsize = 8
            draw.ellipse(
                [cx + dx - dsize, cy + dy - dsize, cx + dx + dsize, cy + dy + dsize],
                fill=dot_c,
            )

        return np.array(img)
