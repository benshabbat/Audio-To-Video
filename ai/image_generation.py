"""
generate_scene_image – generate a single scene image via Imagen 4, falling
back to the Gemini image-output model if Imagen is unavailable.
"""

import io
import base64

from PIL import Image

from .genai_client import get_client

from core.error_utils import safe_error


def generate_scene_image(
    image_prompt: str,
    api_key: str,
    size: tuple = (1280, 720),
) -> Image.Image:
    """
    Generate a 16:9 scene image using Imagen 4.
    Falls back to the Gemini image-output model if Imagen is unavailable.

    Raises RuntimeError if both methods fail — caller should catch and use a placeholder.
    """
    from google.genai import types

    client = get_client(api_key)

    # ── Method 1: Imagen 4 ────────────────────────────────────────────────────
    try:
        response = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=image_prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="16:9",
                output_mime_type="image/png",
            ),
        )
        raw = response.generated_images[0].image.image_bytes
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        return img.resize(size, Image.LANCZOS)

    except Exception as e1:
        print(f"[image_generation] Imagen 4 failed: {safe_error(e1)}")

    # ── Method 2: Gemini image-output model ───────────────────────────────────
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=image_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["image"],
            ),
        )
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    raw = part.inline_data.data
                    if isinstance(raw, str):
                        raw = base64.b64decode(raw)
                    img = Image.open(io.BytesIO(raw)).convert("RGB")
                    return img.resize(size, Image.LANCZOS)

    except Exception as e2:
        print(f"[image_generation] Gemini image model failed: {safe_error(e2)}")

    raise RuntimeError("Image generation failed (Imagen 4 + Gemini both unavailable)")
