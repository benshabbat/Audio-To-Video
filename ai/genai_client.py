import re
import json

# Bounds each individual HTTP call so a stalled connection can't hang a job
# (and its concurrency slot) forever.
_HTTP_TIMEOUT_MS = 120_000


def get_client(api_key: str):
    from google import genai
    from google.genai import types

    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=_HTTP_TIMEOUT_MS))


def parse_json_block(text: str, open_char: str, close_char: str):
    """
    Find the first `open_char ... close_char` span in text (e.g. "{"/"}" or
    "["/"]") and parse it as JSON. Returns None if no span is found or it
    isn't valid JSON.
    """
    match = re.search(re.escape(open_char) + r".*" + re.escape(close_char), text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None
