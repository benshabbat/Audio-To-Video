import math
import random
import numpy as np
from PIL import Image, ImageDraw

from .image_utils import get_font, get_note_font, hex_to_rgb, blend_colors, create_gradient_frame


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

        # Only the semi-transparent pill needs alpha compositing, so do the
        # RGBA convert/composite on just that region instead of the full
        # 1280x720 frame — this runs once per frame, so the saving multiplies
        # by frame count (a ~700x150 pill region is roughly 9x fewer pixels
        # to convert/composite than the full frame).
        box_x1, box_y1 = tx - pad, ty - pad
        box_x2, box_y2 = tx + self.title_w + pad, ty + self.title_h + pad
        # +1: PIL's rounded_rectangle coordinates are inclusive (it fills
        # through box_x2/box_y2), while Image.crop's right/bottom bounds are
        # exclusive — without the +1 the last inclusive column/row of the
        # pill would fall just outside the cropped region and be dropped.
        crop_x1, crop_y1 = max(0, box_x1), max(0, box_y1)
        crop_x2, crop_y2 = min(self.width, box_x2 + 1), min(self.height, box_y2 + 1)

        region = img.crop((crop_x1, crop_y1, crop_x2, crop_y2)).convert("RGBA")
        overlay = Image.new("RGBA", region.size, (0, 0, 0, 0))
        ovd = ImageDraw.Draw(overlay)
        ovd.rounded_rectangle(
            [box_x1 - crop_x1, box_y1 - crop_y1, box_x2 - crop_x1, box_y2 - crop_y1],
            radius=24,
            fill=(0, 0, 30, 170),
        )
        composited = Image.alpha_composite(region, overlay).convert("RGB")
        img.paste(composited, (crop_x1, crop_y1))

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
