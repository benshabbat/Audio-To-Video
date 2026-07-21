import os
import json
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

# Caps how many scenes a user-supplied custom storyboard can request — each
# scene triggers a real, billed Veo/Imagen call, so this can't be unbounded.
MAX_CUSTOM_SCENES = 10
MAX_CUSTOM_PROMPT_LENGTH = 2000


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _valid_job_id(job_id: str) -> bool:
    return all(c.isalnum() or c == "-" for c in job_id)


def _parse_custom_storyboard(raw: str) -> list:
    """
    Parse and validate a user-supplied storyboard JSON string into the same
    shape core/generation.py expects from Gemini's own storyboard: a list of
    {"title", "image_prompt", "duration_ratio"} dicts. Raises ValueError with
    a Hebrew message (shown directly to the caller) on any invalid input.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("הסטוריבורד המותאם אינו JSON תקין")

    if not isinstance(data, list) or not data:
        raise ValueError("הסטוריבורד המותאם חייב להיות רשימה לא ריקה של סצנות")

    if len(data) > MAX_CUSTOM_SCENES:
        raise ValueError(f"מקסימום {MAX_CUSTOM_SCENES} סצנות בסטוריבורד מותאם אישית")

    scenes = []
    for i, scene in enumerate(data):
        if not isinstance(scene, dict):
            raise ValueError(f"סצנה {i + 1} אינה אובייקט תקין")

        image_prompt = str(scene.get("image_prompt") or "").strip()
        if not image_prompt:
            raise ValueError(f"לסצנה {i + 1} חסר image_prompt")
        if len(image_prompt) > MAX_CUSTOM_PROMPT_LENGTH:
            raise ValueError(f"ה-image_prompt של סצנה {i + 1} ארוך מדי")

        duration_ratio = scene.get("duration_ratio", 1.0)
        if not isinstance(duration_ratio, (int, float)) or duration_ratio <= 0:
            duration_ratio = 1.0

        title = str(scene.get("title") or f"סצנה {i + 1}").strip()[:100]
        scenes.append({
            "title": title,
            "image_prompt": image_prompt,
            "duration_ratio": float(duration_ratio),
        })

    return scenes


@main_bp.route("/")
def index():
    return render_template("index.html", max_custom_scenes=MAX_CUSTOM_SCENES)


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

    custom_storyboard = None
    raw_storyboard = (request.form.get("custom_storyboard") or "").strip()
    if raw_storyboard:
        try:
            custom_storyboard = _parse_custom_storyboard(raw_storyboard)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

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
        args=(
            job_id, audio_path, song_name, api_key,
            reference_image_bytes, reference_image_mime, enable_subtitles, custom_storyboard,
        ),
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
