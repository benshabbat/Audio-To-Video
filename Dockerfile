FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p uploads outputs temp_veo

ENV PYTHONUNBUFFERED=1
EXPOSE 5000

# --workers 1 is required, not a tuning choice: jobs/rate-limit state
# (core/jobs.py, web/limiter.py) is in-memory and process-local. Running
# with more workers gives each one its own copy, silently multiplying
# MAX_CONCURRENT_JOBS / GENERATE_RATE_LIMIT instead of sharing the cap.
# --threads lets one process still handle concurrent HTTP requests, since
# each /generate call just starts a background thread and returns.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "--timeout", "120", "app:app"]
