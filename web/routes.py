import os
import time
import uuid
import threading
from flask import Blueprint, render_template, request, send_file, jsonify
from werkzeug.utils import secure_filename

from core.jobs import (
    jobs,
    jobs_lock,
    UPLOAD_FOLDER,
    MAX_CONCURRENT_JOBS,
    active_job_count_locked,
)
from core.generation import run_generation
from .limiter import limiter, GENERATE_RATE_LIMIT

main_bp = Blueprint("main", __name__)

ALLOWED_EXTENSIONS = {"mp3", "wav", "ogg", "flac", "m4a", "aac"}
REFERENCE_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
REFERENCE_IMAGE_MIME = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp",
}


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _valid_job_id(job_id: str) -> bool:
    return all(c.isalnum() or c == "-" for c in job_id)


@main_bp.route("/")
def index():
    return render_template("index.html")


@main_bp.route("/generate", methods=["POST"])
@limiter.limit(GENERATE_RATE_LIMIT)
def generate():
    if "audio" not in request.files:
        return jsonify({"error": "לא הועלה קובץ שמע"}), 400

    file = request.files["audio"]
    if not file.filename or not _allowed(file.filename):
        return jsonify({"error": "פורמט לא נתמך (mp3, wav, ogg, flac, m4a, aac)"}), 400

    song_name = (request.form.get("song_name") or "").strip() or "שיר יפה"
    api_key = (request.form.get("api_key") or "").strip() or os.getenv("GEMINI_API_KEY", "")
    enable_subtitles = (request.form.get("enable_subtitles") or "true").strip().lower() != "false"

    reference_image_bytes = None
    reference_image_mime = "image/png"
    ref_file = request.files.get("reference_image")
    if ref_file and ref_file.filename:
        ext = ref_file.filename.rsplit(".", 1)[-1].lower() if "." in ref_file.filename else ""
        if ext not in REFERENCE_IMAGE_EXTENSIONS:
            return jsonify({"error": "תמונת ייחוס בפורמט לא נתמך (png, jpg, webp)"}), 400
        reference_image_bytes = ref_file.read()
        reference_image_mime = REFERENCE_IMAGE_MIME[ext]

    job_id = str(uuid.uuid4())
    with jobs_lock:
        if active_job_count_locked() >= MAX_CONCURRENT_JOBS:
            return jsonify({
                "error": f"המערכת עמוסה כרגע (עד {MAX_CONCURRENT_JOBS} סרטונים במקביל) — נסה שוב בעוד כמה דקות"
            }), 429
        jobs[job_id] = {
            "status": "starting", "message": "", "error": None, "output_path": None,
            "progress": 0, "created_at": time.time(),
        }

    safe_name = secure_filename(file.filename)
    audio_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_{safe_name}")
    file.save(audio_path)

    thread = threading.Thread(
        target=run_generation,
        args=(job_id, audio_path, song_name, api_key, reference_image_bytes, reference_image_mime, enable_subtitles),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id})


@main_bp.route("/status/<job_id>")
def status(job_id: str):
    if not _valid_job_id(job_id):
        return jsonify({"error": "Invalid job ID"}), 400

    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({
        "status": job["status"],
        "message": job.get("message", ""),
        "error": job.get("error"),
        "progress": job.get("progress", 0),
        "ready": job["status"] == "done",
    })


@main_bp.route("/download/<job_id>")
def download(job_id: str):
    if not _valid_job_id(job_id):
        return jsonify({"error": "Invalid job ID"}), 400

    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "הסרטון עוד לא מוכן"}), 404

    output_path = job.get("output_path", "")
    if not output_path or not os.path.isfile(output_path):
        return jsonify({"error": "הקובץ לא נמצא"}), 404

    return send_file(output_path, as_attachment=True, download_name="video.mp4")
