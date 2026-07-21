import os
import time

from moviepy import AudioFileClip, VideoFileClip

from ai.audio_analysis import analyze_song_audio
from ai.storyboard import get_storyboard
from ai.image_generation import generate_scene_image
from ai.veo_client import generate_scene_video
from media.image_utils import create_placeholder_image
from media.video_generator import (
    generate_video,
    make_kenburns_clip,
    fit_clip_duration,
    assemble_scene_clips,
)
from media.subtitles import add_karaoke_subtitles
from .error_utils import safe_error
from .jobs import jobs, OUTPUT_FOLDER, TEMP_VEO_FOLDER

VEO_SCENE_TIMEOUT = 300  # seconds to wait for a single Veo clip before falling back

# Audio-understanding cost scales with the audio's duration, not its byte
# size — MAX_CONTENT_LENGTH alone doesn't stop a long, low-bitrate file from
# triggering a very expensive Gemini File API analysis call.
MAX_SONG_DURATION_SECONDS = int(os.getenv("MAX_SONG_DURATION_SECONDS", "600"))

# Default scene colours (used for placeholder images when Imagen fails)
_SCENE_COLORS = [
    (255, 107, 107), (255, 217, 61), (107, 203, 119),
    (77, 150, 255), (199, 125, 255), (255, 160, 80),
]

# Rough progress percentage per named status (used when a step has no
# finer-grained sub-progress of its own, e.g. the Veo clip loop below)
_STATUS_PROGRESS = {
    "starting": 0, "audio": 5, "storyboard": 10, "clips": 15,
    "video": 85, "subtitles": 92, "done": 100, "error": 0,
}

DEFAULT_NUM_SCENES = 6

# Veo's shortest supported clip is 4s (ai/veo_client._ALLOWED_DURATIONS).
# Asking for more/shorter scenes than the song can give ~4s each just means
# every Veo clip gets time-stretched (sped up) to squeeze into its shorter
# slot — paying for a full ~4-8s Veo generation per scene while using only a
# fraction of it. Scaling scene count down for short audio avoids that.
MIN_SCENE_SECONDS = 4.0


def _scene_count_for_duration(duration: float) -> int:
    max_scenes_that_fit = int(duration // MIN_SCENE_SECONDS)
    return max(2, min(DEFAULT_NUM_SCENES, max_scenes_that_fit))


# Floor for a single scene's own raw duration, before proportional
# reconciliation below — guards against a hallucinated zero/negative Gemini
# timestamp or duration_ratio for one scene.
MIN_RAW_SCENE_SECONDS = 0.5


def _reconcile_scene_durations(raw_durations: list, song_duration: float) -> list:
    """
    Clamp each scene to a small positive floor, then scale all of them
    proportionally so they sum exactly to song_duration.

    The storyboard's own timings/ratios never line up exactly with the real,
    ffmpeg-measured song_duration. Scaling proportionally — instead of
    dumping the entire drift onto the last scene — avoids driving any single
    scene's duration to zero or negative (which crashes moviepy's
    with_speed_scaled: a 0 final_duration leaves its speed factor as None,
    a negative one produces a clip with negative duration) and avoids
    stretching one scene to an extreme, visibly frozen/slow-motion length
    when e.g. Gemini returns more scenes than requested and the tail gets
    truncated.
    """
    clamped = [max(MIN_RAW_SCENE_SECONDS, d) for d in raw_durations]
    scale = song_duration / sum(clamped)
    return [d * scale for d in clamped]


def run_generation(
    job_id: str,
    audio_path: str,
    song_name: str,
    api_key: str,
    reference_image_bytes: bytes = None,
    reference_image_mime: str = "image/png",
    enable_subtitles: bool = True,
    custom_storyboard: list = None,
) -> None:
    def _status(status: str, message: str = "", progress: int = None) -> None:
        if progress is None:
            progress = _STATUS_PROGRESS.get(status, jobs[job_id].get("progress", 0))
        jobs[job_id].update({"status": status, "message": message, "progress": progress})

    temp_veo_paths: list = []
    temp_intermediate_paths: list = []
    # Raw VideoFileClip handles for downloaded Veo clips — must be closed
    # before their temp files can be deleted (os.remove on an open file
    # raises OSError on Windows, otherwise silently leaking the file).
    veo_file_clips: list = []

    try:
        output_path = os.path.join(OUTPUT_FOLDER, f"{job_id}.mp4")

        audio_probe = AudioFileClip(audio_path)
        song_duration = audio_probe.duration
        audio_probe.close()

        if song_duration > MAX_SONG_DURATION_SECONDS:
            raise RuntimeError(
                f"קובץ השמע ארוך מדי ({int(song_duration)} שניות, "
                f"מקסימום {MAX_SONG_DURATION_SECONDS})"
            )

        if api_key:
            storyboard = None
            scene_durations = None
            lyric_lines: list = []

            if custom_storyboard is not None:
                # ── User-supplied storyboard: skip Gemini's own scene/prompt
                # generation entirely. There's no real audio-timed lyric data
                # for a storyboard we didn't derive from analyze_song_audio,
                # so karaoke subtitles are unavailable for this path.
                _status("storyboard", "משתמש בסטוריבורד מותאם אישית...")
                storyboard = custom_storyboard
                raw_ratios = [s.get("duration_ratio", 1.0) for s in storyboard]
                scene_durations = _reconcile_scene_durations(raw_ratios, song_duration)
            else:
                num_scenes = _scene_count_for_duration(song_duration)

                # ── Step 1: Listen to the real audio and build a storyboard ──
                _status("audio", "מאזין לשיר ומנתח אותו (Gemini File API)...")
                try:
                    analysis = analyze_song_audio(audio_path, song_name, api_key, num_scenes=num_scenes)
                    candidate_scenes = analysis["scenes"]
                    candidate_durations = [
                        s.get("end", 0) - s.get("start", 0) for s in candidate_scenes
                    ]
                    if len(candidate_scenes) >= 2 and all(d > 0.2 for d in candidate_durations):
                        storyboard = candidate_scenes
                        scene_durations = _reconcile_scene_durations(candidate_durations, song_duration)
                        lyric_lines = analysis.get("lyric_lines", [])
                    else:
                        raise RuntimeError("Audio analysis returned invalid scene timings")
                except Exception as audio_err:
                    print(f"[generation] Audio analysis failed, using title-only storyboard: {safe_error(audio_err)}")

                if storyboard is None:
                    _status("storyboard", "יוצר סטורי בורד...")
                    storyboard = get_storyboard(song_name, api_key, num_scenes=num_scenes)
                    raw_ratios = [s.get("duration_ratio", 1.0) for s in storyboard]
                    scene_durations = _reconcile_scene_durations(raw_ratios, song_duration)

            # ── Step 2: Generate a real video clip per scene with Veo 3.1 ──
            scene_clips = []
            clips_progress_start, clips_progress_end = 15, 80
            for i, (scene, scene_dur) in enumerate(zip(storyboard, scene_durations)):
                clip_progress = clips_progress_start + int(
                    (i / len(storyboard)) * (clips_progress_end - clips_progress_start)
                )
                _status(
                    "clips",
                    f"מייצר סצנת וידאו {i + 1} מתוך {len(storyboard)} (Veo 3.1)...",
                    progress=clip_progress,
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
                        output_dir=TEMP_VEO_FOLDER,
                    )
                    temp_veo_paths.append(veo_path)
                    raw_clip = VideoFileClip(veo_path).without_audio().resized(new_size=(1280, 720))
                    veo_file_clips.append(raw_clip)
                    clip = fit_clip_duration(raw_clip, scene_dur)
                except Exception as veo_err:
                    print(f"[generation] Scene {i + 1} Veo generation failed, using still image: {safe_error(veo_err)}")

                if clip is None:
                    try:
                        img = generate_scene_image(scene["image_prompt"], api_key)
                    except Exception as img_err:
                        print(f"[generation] Scene {i + 1} image fallback failed: {safe_error(img_err)}")
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
                    print(f"[generation] Subtitle burn failed, using video without subtitles: {safe_error(sub_err)}")

                if not subtitles_burned:
                    os.replace(assembled_path, output_path)
                    temp_intermediate_paths.remove(assembled_path)
            else:
                assemble_scene_clips(audio_path, output_path, scene_clips)
        else:
            # ── Procedural fallback (no API key) ──────────────────────────
            _status("video", "יוצר אנימציה...")
            generate_video(audio_path, song_name, output_path)

        jobs[job_id].update({"status": "done", "output_path": output_path, "progress": 100})

    except Exception as exc:
        jobs[job_id].update({"status": "error", "error": safe_error(exc), "progress": 0})

    finally:
        for clip in veo_file_clips:
            try:
                clip.close()
            except Exception:
                pass
        try:
            os.remove(audio_path)
        except OSError:
            pass
        for path in temp_veo_paths + temp_intermediate_paths:
            try:
                os.remove(path)
            except OSError:
                pass
