"""
Gemini API client:
  1. analyze_song_audio  – upload the real audio to Gemini (File API) and have
     it listen to the song, returning lyrics/BPM/mood + a storyboard timed to
     the song's actual section boundaries
  2. get_storyboard  – title-only storyboard fallback (uniform scene lengths)
  3. generate_scene_image – generate a single scene image via Imagen 4 (or Gemini fallback)

Uses the `google-genai` package (google.genai).
Raises RuntimeError from analyze_song_audio / generate_scene_image on total
failure so the caller can fall back (to get_storyboard / a placeholder image).
"""

import io
import re
import time
import json
import base64

from PIL import Image

from error_utils import safe_error

_AUDIO_MIME = {
    "mp3": "audio/mpeg", "wav": "audio/wav", "ogg": "audio/ogg",
    "flac": "audio/flac", "m4a": "audio/mp4", "aac": "audio/aac",
}


def _file_state_name(f) -> str:
    state = getattr(f, "state", None)
    return str(getattr(state, "name", state) or "")


def _upload_audio_file(client, audio_path: str, timeout: int = 60):
    """Upload the audio file via the Gemini File API and wait until it's ready to use."""
    ext = audio_path.rsplit(".", 1)[-1].lower() if "." in audio_path else ""
    mime_type = _AUDIO_MIME.get(ext, "audio/mpeg")

    uploaded = client.files.upload(file=audio_path, config={"mime_type": mime_type})

    waited = 0
    while _file_state_name(uploaded) == "PROCESSING":
        if waited >= timeout:
            raise RuntimeError("Gemini file processing timed out")
        time.sleep(3)
        waited += 3
        uploaded = client.files.get(name=uploaded.name)

    if _file_state_name(uploaded) == "FAILED":
        raise RuntimeError("Gemini failed to process the uploaded audio file")

    return uploaded


def analyze_song_audio(audio_path: str, song_name: str, api_key: str, num_scenes: int = 6) -> dict:
    """
    Upload the song's actual audio to Gemini and have it listen to the song
    directly (native audio understanding), extracting lyrics/BPM/mood, a
    scene-by-scene storyboard timed to the song's real structure, and
    line-by-line timed lyrics for karaoke-style subtitles.

    Returns:
        {
          "lyrics": str, "bpm": int | None, "mood": str,
          "scenes": [{"title": Hebrew str, "image_prompt": English str,
                      "start": float seconds, "end": float seconds}, ...],
          "lyric_lines": [{"text": str, "start": float seconds, "end": float seconds}, ...]
        }
    "lyric_lines" is an empty list for instrumental songs.

    Raises RuntimeError on any failure — caller should fall back to
    get_storyboard() (title-only, uniform-duration storyboard).
    """
    from google import genai

    client = genai.Client(api_key=api_key)
    uploaded = _upload_audio_file(client, audio_path)

    try:
        prompt = f"""Listen carefully to this children's song audio (title: "{song_name}").

Return ONLY a valid JSON object (no other text):
{{
  "lyrics": "full lyrics if the song is sung, or an empty string if instrumental",
  "bpm": estimated tempo as an integer,
  "mood": "brief English mood/style description",
  "scenes": [
    {{
      "title": "brief Hebrew scene title (1-3 words)",
      "image_prompt": "detailed English prompt for a video generation model describing what happens in this part of the song, children's book illustration style, colorful, cute cartoon style, bright colors, high quality",
      "start": seconds as a float,
      "end": seconds as a float
    }}
  ],
  "lyric_lines": [
    {{
      "text": "one sung line, in the language it's actually sung in",
      "start": seconds as a float when this line begins,
      "end": seconds as a float when this line ends
    }}
  ]
}}

Rules:
- Base the scenes on the song's real structure (intro/verse/chorus/etc.) and lyrics content — not guesswork.
- Exactly {num_scenes} scenes, contiguous, covering the entire song with no gaps or overlaps (first scene starts at 0, last scene ends at the song's total duration).
- image_prompt must be in English only.
- lyric_lines must cover every sung line in the song in chronological order with accurate timing; return an empty array if the song is instrumental."""

        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=[uploaded, prompt],
        )
        text = response.text.strip()
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if not json_match:
            raise RuntimeError("Gemini did not return JSON for audio analysis")

        data = json.loads(json_match.group())
        scenes = data.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            raise RuntimeError("Gemini audio analysis returned no scenes")

        lyric_lines = data.get("lyric_lines")
        if not isinstance(lyric_lines, list):
            lyric_lines = []

        return {
            "lyrics": data.get("lyrics", ""),
            "bpm": data.get("bpm"),
            "mood": data.get("mood", ""),
            "scenes": scenes[:num_scenes],
            "lyric_lines": lyric_lines,
        }
    finally:
        try:
            client.files.delete(name=uploaded.name)
        except Exception:
            pass


# ── Default storyboard (used when no API key or on error) ────────────────────

def _default_storyboard(song_name: str, num_scenes: int) -> list:
    scenes = [
        {
            "title": "פתיחה",
            "image_prompt": (
                f"Colorful opening scene for a children's song called '{song_name}', "
                "happy animated characters, bright background, "
                "children's book illustration style, vibrant colors, high quality"
            ),
            "duration_ratio": 1.0,
        },
        {
            "title": "הרפתקה",
            "image_prompt": (
                "Cute cartoon animals on a fun adventure in a magical forest, "
                "colorful flowers and butterflies, children's illustration, bright and cheerful"
            ),
            "duration_ratio": 1.2,
        },
        {
            "title": "שיר וריקוד",
            "image_prompt": (
                "Adorable animated animals dancing and singing together under a rainbow, "
                "joyful, children's book illustration style, vivid colors"
            ),
            "duration_ratio": 1.5,
        },
        {
            "title": "טבע",
            "image_prompt": (
                "Beautiful colorful landscape with a smiling sun, fluffy clouds, "
                "colorful birds, children's cartoon style, cheerful and bright"
            ),
            "duration_ratio": 1.0,
        },
        {
            "title": "חברים",
            "image_prompt": (
                "Group of happy cartoon children and animals playing together, "
                "colorful playground, children's illustration, friendship theme"
            ),
            "duration_ratio": 1.2,
        },
        {
            "title": "סיום",
            "image_prompt": (
                "Magical celebration with colorful confetti and stars, "
                "happy characters, children's illustration, warm joyful ending"
            ),
            "duration_ratio": 1.0,
        },
    ]
    return scenes[:num_scenes]


# ── Public API ────────────────────────────────────────────────────────────────

def get_storyboard(song_name: str, api_key: str, num_scenes: int = 6) -> list:
    """
    Ask Gemini to produce a storyboard for the given children's song.

    Returns a list of dicts with keys:
        title (str in Hebrew), image_prompt (str in English), duration_ratio (float)
    """
    if not api_key:
        return _default_storyboard(song_name, num_scenes)

    try:
        from google import genai  # google-genai package

        client = genai.Client(api_key=api_key)
        prompt = f"""Create a {num_scenes}-scene visual storyboard for a children's song called "{song_name}".

Return ONLY a valid JSON array (no other text):
[
  {{
    "title": "brief Hebrew scene title (1-3 words)",
    "image_prompt": "detailed English prompt for Imagen, children's book illustration style",
    "duration_ratio": 1.0
  }}
]

Rules:
- image_prompt: English only, detailed, include "children's book illustration, colorful, cute cartoon style, bright colors, high quality"
- duration_ratio: use 1.5 for chorus / important scenes, 1.0 for others
- Exactly {num_scenes} scenes, no duplicate titles"""

        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=prompt,
        )
        text = response.text.strip()
        json_match = re.search(r"\[.*\]", text, re.DOTALL)
        if json_match:
            scenes = json.loads(json_match.group())
            if isinstance(scenes, list) and len(scenes) > 0:
                return scenes[:num_scenes]

    except Exception as exc:
        print(f"[gemini] Storyboard error: {safe_error(exc)}")

    return _default_storyboard(song_name, num_scenes)


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
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

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
        print(f"[gemini] Imagen 4 failed: {safe_error(e1)}")

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
        print(f"[gemini] Gemini image model failed: {safe_error(e2)}")

    raise RuntimeError("Image generation failed (Imagen 3 + Gemini both unavailable)")

