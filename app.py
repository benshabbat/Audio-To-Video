import os
import uuid
import time
import threading
from flask import Flask, render_template, request, send_file, jsonify
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from moviepy.editor import AudioFileClip, VideoFileClip

load_dotenv()

from gemini_client import analyze_song_audio, get_storyboard, generate_scene_image
from veo_client import generate_scene_video
from animation import create_placeholder_image
from video_generator import (
    generate_video,
    make_kenburns_clip,
    fit_clip_duration,
    assemble_scene_clips,
)
from subtitles import add_karaoke_subtitles

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"mp3", "wav", "ogg", "flac", "m4a", "aac"}
REFERENCE_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
REFERENCE_IMAGE_MIME = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp",
}
VEO_SCENE_TIMEOUT = 300  # seconds to wait for a single Veo clip before falling back

# Default scene colours (used for placeholder images when Imagen fails)
_SCENE_COLORS = [
    (255, 107, 107), (255, 217, 61), (107, 203, 119),
    (77, 150, 255), (199, 125, 255), (255, 160, 80),
]

# In-memory job store  {job_id: {status, message, error, output_path}}
jobs: dict = {}


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _run_generation(
    job_id: str,
    audio_path: str,
    song_name: str,
    api_key: str,
    reference_image_bytes: bytes = None,
    reference_image_mime: str = "image/png",
    enable_subtitles: bool = True,
) -> None:
    def _status(status: str, message: str = "") -> None:
        jobs[job_id].update({"status": status, "message": message})

    temp_veo_paths: list = []
    temp_intermediate_paths: list = []

    try:
        output_path = os.path.join(OUTPUT_FOLDER, f"{job_id}.mp4")

        if api_key:
            audio_probe = AudioFileClip(audio_path)
            song_duration = audio_probe.duration
            audio_probe.close()

            # ── Step 1: Listen to the real audio and build a storyboard ────
            _status("audio", "מאזין לשיר ומנתח אותו (Gemini File API)...")
            storyboard = None
            scene_durations = None
            lyric_lines: list = []
            try:
                analysis = analyze_song_audio(audio_path, song_name, api_key)
                candidate_scenes = analysis["scenes"]
                candidate_durations = [
                    s.get("end", 0) - s.get("start", 0) for s in candidate_scenes
                ]
                if len(candidate_scenes) >= 2 and all(d > 0.2 for d in candidate_durations):
                    storyboard = candidate_scenes
                    scene_durations = candidate_durations
                    scene_durations[-1] += song_duration - sum(scene_durations)
                    lyric_lines = analysis.get("lyric_lines", [])
                else:
                    raise RuntimeError("Audio analysis returned invalid scene timings")
            except Exception as audio_err:
                print(f"[app] Audio analysis failed, using title-only storyboard: {audio_err}")

            if storyboard is None:
                _status("storyboard", "יוצר סטורי בורד...")
                storyboard = get_storyboard(song_name, api_key)
                total_ratio = sum(s.get("duration_ratio", 1.0) for s in storyboard)
                scene_durations = [
                    (s.get("duration_ratio", 1.0) / total_ratio) * song_duration
                    for s in storyboard
                ]
                scene_durations[-1] += song_duration - sum(scene_durations)

            # ── Step 2: Generate a real video clip per scene with Veo 3.1 ──
            scene_clips = []
            for i, (scene, scene_dur) in enumerate(zip(storyboard, scene_durations)):
                _status(
                    "clips",
                    f"מייצר סצנת וידאו {i + 1} מתוך {len(storyboard)} (Veo 3.1)...",
                )
                clip = None
                try:
                    veo_path = generate_scene_video(
                        scene["image_prompt"],
                        api_key,
                        reference_image_bytes=reference_image_bytes,
                        reference_image_mime=reference_image_mime,
                        duration_seconds=scene_dur,
                        timeout=VEO_SCENE_TIMEOUT,
                    )
                    temp_veo_paths.append(veo_path)
                    raw_clip = VideoFileClip(veo_path).without_audio().resize(newsize=(1280, 720))
                    clip = fit_clip_duration(raw_clip, scene_dur)
                except Exception as veo_err:
                    print(f"[app] Scene {i + 1} Veo generation failed, using still image: {veo_err}")

                if clip is None:
                    try:
                        img = generate_scene_image(scene["image_prompt"], api_key)
                    except Exception as img_err:
                        print(f"[app] Scene {i + 1} image fallback failed: {img_err}")
                        img = create_placeholder_image(
                            scene.get("title", str(i + 1)),
                            _SCENE_COLORS[i % len(_SCENE_COLORS)],
                        )
                    clip = make_kenburns_clip(img, scene_dur, size=(1280, 720), zoom_in=(i % 2 == 0))

                scene_clips.append(clip)
                time.sleep(0.4)  # light rate-limit guard

            # ── Step 3: Assemble final video ────────────────────────────────
            _status("video", "מרכיב סרטון סופי...")

            if lyric_lines and enable_subtitles:
                assembled_path = os.path.join(OUTPUT_FOLDER, f"{job_id}_assembled.mp4")
                temp_intermediate_paths.append(assembled_path)
                assemble_scene_clips(audio_path, assembled_path, scene_clips)

                _status("subtitles", "מטמיע כתוביות קריוקי...")
                subtitles_burned = False
                try:
                    subtitles_burned = add_karaoke_subtitles(assembled_path, lyric_lines, output_path)
                except Exception as sub_err:
                    print(f"[app] Subtitle burn failed, using video without subtitles: {sub_err}")

                if not subtitles_burned:
                    os.replace(assembled_path, output_path)
                    temp_intermediate_paths.remove(assembled_path)
            else:
                assemble_scene_clips(audio_path, output_path, scene_clips)
        else:
            # ── Procedural fallback (no API key) ──────────────────────────
            _status("video", "יוצר אנימציה...")
            generate_video(audio_path, song_name, output_path)

        jobs[job_id].update({"status": "done", "output_path": output_path})

    except Exception as exc:
        jobs[job_id].update({"status": "error", "error": str(exc)})

    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass
        for path in temp_veo_paths + temp_intermediate_paths:
            try:
                os.remove(path)
            except OSError:
                pass


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
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
    safe_name = secure_filename(file.filename)
    audio_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_{safe_name}")
    file.save(audio_path)

    jobs[job_id] = {"status": "starting", "message": "", "error": None, "output_path": None}

    thread = threading.Thread(
        target=_run_generation,
        args=(job_id, audio_path, song_name, api_key, reference_image_bytes, reference_image_mime, enable_subtitles),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id: str):
    if not all(c.isalnum() or c == "-" for c in job_id):
        return jsonify({"error": "Invalid job ID"}), 400

    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({
        "status": job["status"],
        "message": job.get("message", ""),
        "error": job.get("error"),
        "ready": job["status"] == "done",
    })


@app.route("/download/<job_id>")
def download(job_id: str):
    if not all(c.isalnum() or c == "-" for c in job_id):
        return jsonify({"error": "Invalid job ID"}), 400

    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "הסרטון עוד לא מוכן"}), 404

    output_path = job.get("output_path", "")
    if not output_path or not os.path.isfile(output_path):
        return jsonify({"error": "הקובץ לא נמצא"}), 404

    return send_file(output_path, as_attachment=True, download_name="video.mp4")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
