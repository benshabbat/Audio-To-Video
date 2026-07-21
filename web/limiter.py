import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Caps how many /generate requests a single client IP can submit, independent
# of MAX_CONCURRENT_JOBS — without this, one client could keep resubmitting
# the instant a job slot frees up and monopolize the (shared, billed) Veo/
# Gemini quota indefinitely.
GENERATE_RATE_LIMIT = os.getenv("GENERATE_RATE_LIMIT", "5 per hour")

# In-memory storage: same process-local limitation as the `jobs` store in
# core/jobs.py — each worker process gets its own counters. Fine for a single
# process; move to a shared store (e.g. Redis) before running multiple workers.
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
