"""
analyze_song_audio – upload the real audio to Gemini (File API) and have it
listen to the song, returning lyrics/BPM/mood + a storyboard timed to the
song's actual section boundaries + line-by-line timed lyrics for karaoke
subtitles.

Raises RuntimeError on total failure so the caller can fall back to
storyboard.get_storyboard() (title-only, uniform-duration storyboard).
"""

import re
import time
import json

from .genai_client import get_client

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
    client = get_client(api_key)
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
