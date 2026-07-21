from web import create_app
from web.limiter import limiter, GENERATE_RATE_LIMIT


def test_generate_is_rate_limited_per_client():
    # Only meaningful against the default "N per hour" config — if someone
    # overrides GENERATE_RATE_LIMIT via env for their own deployment, this
    # test's fixed request count no longer matches and should be skipped.
    assert GENERATE_RATE_LIMIT == "5 per hour", (
        "test assumes the default GENERATE_RATE_LIMIT; update the request "
        "count above if the default changes"
    )

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    limiter.reset()

    # No "audio" file attached, so each request 400s immediately inside the
    # view — but it still passes through (and counts against) the rate
    # limiter, which runs before the view body.
    statuses = [client.post("/generate", data={}).status_code for _ in range(6)]

    assert statuses[:5] == [400] * 5
    assert statuses[5] == 429
