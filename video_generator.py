import numpy as np
from PIL import Image
from moviepy.editor import VideoClip, AudioFileClip, concatenate_videoclips
import moviepy.video.fx.all as vfx
from animation import ChildrenAnimator, StoryboardAnimator, apply_ken_burns


def generate_video(
    audio_path: str,
    song_name: str,
    output_path: str,
    storyboard: list = None,
    scene_images: list = None,
    theme: dict = None,
) -> None:
    """
    Create an animated MP4 video synced to the given audio file.

    If storyboard + scene_images are provided, uses StoryboardAnimator
    (AI-generated images with Ken Burns + crossfade).
    Otherwise falls back to the procedural ChildrenAnimator.
    """
    audio = AudioFileClip(audio_path)
    duration = audio.duration

    if storyboard and scene_images:
        # ── Storyboard mode ────────────────────────────────────────────────
        total_ratio = sum(s.get("duration_ratio", 1.0) for s in storyboard)
        scene_durations = [
            (s.get("duration_ratio", 1.0) / total_ratio) * duration
            for s in storyboard
        ]
        # Correct any floating-point drift so durations sum exactly to audio length
        diff = duration - sum(scene_durations)
        scene_durations[-1] += diff

        animator = StoryboardAnimator(
            images=scene_images,
            scene_durations=scene_durations,
            title=song_name,
            size=(1280, 720),
        )
    else:
        # ── Procedural fallback ────────────────────────────────────────────
        colors: list = []
        if theme:
            for key in ("bg_color1", "bg_color2"):
                val = theme.get(key)
                if val:
                    colors.append(val)
            colors.extend(theme.get("colors", []))

        animator = ChildrenAnimator(
            title=song_name,
            duration=duration,
            colors=colors,
            size=(1280, 720),
        )

    video = VideoClip(animator.make_frame, duration=duration)
    video = video.set_audio(audio)

    video.write_videofile(
        output_path,
        fps=15,
        codec="libx264",
        audio_codec="aac",
        preset="fast",
        threads=4,
        logger=None,
    )

    audio.close()
    video.close()


def make_kenburns_clip(
    image: Image.Image,
    duration: float,
    size: tuple = (1280, 720),
    zoom_in: bool = True,
) -> VideoClip:
    """Wrap a single still image into a silent Ken Burns (pan + zoom) clip."""
    arr = np.array(image.resize(size, Image.LANCZOS))
    return VideoClip(lambda t: apply_ken_burns(arr, t, duration, zoom_in), duration=duration)


def fit_clip_duration(clip: VideoClip, target_duration: float) -> VideoClip:
    """Time-stretch a clip so its length matches target_duration exactly."""
    if abs(clip.duration - target_duration) < 0.05:
        return clip.set_duration(target_duration)
    return clip.fx(vfx.speedx, final_duration=target_duration)


def assemble_scene_clips(audio_path: str, output_path: str, clips: list) -> None:
    """
    Concatenate per-scene silent clips (Veo clips and/or Ken Burns fallbacks),
    overlay the original song audio, and write the final MP4. Clip durations
    are expected to already sum close to the audio length; any drift is
    reconciled by trimming or freezing the last frame.
    """
    audio = AudioFileClip(audio_path)
    video = concatenate_videoclips(clips, method="compose")

    if video.duration > audio.duration:
        video = video.subclip(0, audio.duration)
    elif video.duration < audio.duration - 0.05:
        pad = audio.duration - video.duration
        freeze = clips[-1].to_ImageClip(t=max(0, clips[-1].duration - 0.04)).set_duration(pad)
        video = concatenate_videoclips([video, freeze], method="compose")

    video = video.set_audio(audio)
    video.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="fast",
        threads=4,
        logger=None,
    )

    audio.close()
    video.close()
