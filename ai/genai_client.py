# Bounds each individual HTTP call so a stalled connection can't hang a job
# (and its concurrency slot) forever.
_HTTP_TIMEOUT_MS = 120_000


def get_client(api_key: str):
    from google import genai
    from google.genai import types

    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=_HTTP_TIMEOUT_MS))
