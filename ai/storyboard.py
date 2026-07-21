"""
get_storyboard – title-only storyboard fallback used when there's no API key,
or when audio_analysis.analyze_song_audio fails (uniform scene lengths,
no real listening to the song).
"""

from .genai_client import get_client, parse_json_block

from core.error_utils import safe_error


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


def get_storyboard(song_name: str, api_key: str, num_scenes: int = 6) -> list:
    """
    Ask Gemini to produce a storyboard for the given children's song.

    Returns a list of dicts with keys:
        title (str in Hebrew), image_prompt (str in English), duration_ratio (float)
    """
    if not api_key:
        return _default_storyboard(song_name, num_scenes)

    try:
        client = get_client(api_key)
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
        scenes = parse_json_block(text, "[", "]")
        if isinstance(scenes, list) and len(scenes) > 0:
            return scenes[:num_scenes]

    except Exception as exc:
        print(f"[storyboard] Storyboard error: {safe_error(exc)}")

    return _default_storyboard(song_name, num_scenes)
