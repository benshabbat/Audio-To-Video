"""
Veo 3.1 client: generates one real-motion video clip per storyboard scene.

Uses the `google-genai` package (google.genai). The optional reference image
is passed as a character "ingredient" to keep the same character consistent
across scenes; if the installed SDK version doesn't support that field yet,
it falls back to using the image as first-frame conditioning.

generate_scene_video raises RuntimeError on any failure/timeout so the caller
can fall back to a still-image (Ken Burns) clip for that scene.
"""

import os
import time
import uuid
import tempfile

from core.error_utils import safe_error
from .genai_client import get_client

_ALLOWED_DURATIONS = (4, 6, 8)  # seconds supported by the veo-3.1 model family

# Lite tier is ~1/3 the cost of the full model with no feature loss for this
# app's usage (reference-image conditioning works on both). Override via env
# if higher fidelity is ever worth the extra cost.
_VEO_MODEL = os.getenv("VEO_MODEL", "veo-3.1-lite-generate-preview")


def _closest_allowed_duration(seconds: float) -> int:
    return min(_ALLOWED_DURATIONS, key=lambda d: abs(d - seconds))


def generate_scene_video(
    prompt: str,
    api_key: str,
    reference_image_bytes: bytes = None,
    reference_image_mime: str = "image/png",
    duration_seconds: float = 8,
    aspect_ratio: str = "16:9",
    poll_interval: int = 10,
    timeout: int = 300,
    output_dir: str = None,
) -> str:
    """
    Generate a single scene as a real video clip with Veo 3.1.

    Returns the path to a downloaded temp .mp4 file. Raises RuntimeError if
    generation fails or times out.
    """
    from google.genai import types

    client = get_client(api_key)
    veo_duration = _closest_allowed_duration(duration_seconds)

    config_kwargs = {
        "aspect_ratio": aspect_ratio,
        "duration_seconds": veo_duration,
        "number_of_videos": 1,
    }

    image = None
    if reference_image_bytes:
        image = types.Image(image_bytes=reference_image_bytes, mime_type=reference_image_mime)

    operation = None

    # ── Attempt 1: character reference image ("ingredients to video") ────────
    if image is not None:
        try:
            operation = client.models.generate_videos(
                model=_VEO_MODEL,
                prompt=prompt,
                config=types.GenerateVideosConfig(reference_images=[image], **config_kwargs),
            )
        except TypeError:
            operation = None  # installed SDK doesn't know this field yet

    # ── Attempt 2: image as first-frame conditioning (or no image at all) ────
    if operation is None:
        try:
            operation = client.models.generate_videos(
                model=_VEO_MODEL,
                prompt=prompt,
                image=image,
                config=types.GenerateVideosConfig(**config_kwargs),
            )
        except Exception as exc:
            raise RuntimeError(f"Veo request failed: {safe_error(exc)}") from exc

    # ── Poll until the long-running operation completes ──────────────────────
    waited = 0
    while not operation.done:
        if waited >= timeout:
            raise RuntimeError(f"Veo generation timed out after {timeout}s")
        time.sleep(poll_interval)
        waited += poll_interval
        try:
            operation = client.operations.get(operation)
        except Exception as exc:
            raise RuntimeError(f"Veo polling failed: {safe_error(exc)}") from exc

    if getattr(operation, "error", None):
        raise RuntimeError(f"Veo generation error: {safe_error(operation.error)}")

    result = getattr(operation, "response", None) or getattr(operation, "result", None)
    videos = getattr(result, "generated_videos", None) if result else None
    if not videos:
        raise RuntimeError("Veo returned no video")

    video = videos[0].video
    out_path = os.path.join(output_dir or tempfile.gettempdir(), f"veo_{uuid.uuid4().hex}.mp4")

    try:
        client.files.download(file=video)
    except Exception:
        pass  # some SDK versions download automatically inside .save()

    video.save(out_path)

    if not os.path.isfile(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError("Veo video download produced an empty file")

    return out_path
