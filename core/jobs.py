import os
import time
import threading

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"
TEMP_VEO_FOLDER = "temp_veo"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(TEMP_VEO_FOLDER, exist_ok=True)

FILE_RETENTION_SECONDS = 3 * 60 * 60  # delete finished jobs' files after 3h
CLEANUP_INTERVAL_SECONDS = 30 * 60

# Veo 3.1 calls are slow and metered — cap how many generation jobs can run
# at the same time so a burst of uploads can't fan out into unbounded,
# expensive concurrent Veo/Gemini requests.
#
# This cap (and the `jobs` store below) is process-local in-memory state, so
# it only holds if this app runs as a single process. Deploying behind
# multiple worker processes (e.g. `gunicorn -w N`) gives each worker its own
# copy, silently raising the real limit to MAX_CONCURRENT_JOBS * N — run with
# a single worker, or move this to shared external state first.
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "2"))

# In-memory job store  {job_id: {status, message, error, output_path, progress, created_at}}
jobs: dict = {}

# Guards structural changes to `jobs` (insert/delete) so the concurrency-cap
# check-then-insert in /generate is atomic and concurrent iteration (e.g. from
# cleanup_old_jobs) can't crash on a dict-changed-size-during-iteration race.
jobs_lock = threading.Lock()


def active_job_count_locked() -> int:
    """Count active jobs. Caller must hold jobs_lock."""
    return sum(1 for job in jobs.values() if job.get("status") not in ("done", "error"))


def cleanup_old_jobs() -> None:
    """Delete output/upload files (and their job entries) older than FILE_RETENTION_SECONDS."""
    cutoff = time.time() - FILE_RETENTION_SECONDS

    for folder in (UPLOAD_FOLDER, OUTPUT_FOLDER, TEMP_VEO_FOLDER):
        try:
            entries = os.listdir(folder)
        except OSError:
            continue
        for name in entries:
            path = os.path.join(folder, name)
            try:
                if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                    os.remove(path)
            except OSError:
                pass

    with jobs_lock:
        stale_job_ids = [
            job_id for job_id, job in jobs.items()
            if job.get("created_at", time.time()) < cutoff
        ]
        for job_id in stale_job_ids:
            jobs.pop(job_id, None)


def cleanup_loop() -> None:
    while True:
        time.sleep(CLEANUP_INTERVAL_SECONDS)
        cleanup_old_jobs()
