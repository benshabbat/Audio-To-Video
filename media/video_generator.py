import numpy as np
from PIL import Image
from moviepy import VideoClip, AudioFileClip, concatenate_videoclips
from .animation import ChildrenAnimator
from .image_utils import apply_ken_burns

# Moves the moov atom to the front of the file so players (e.g. YouTube,
# mobile browsers) can start playback before the whole file has downloaded.
_FASTSTART_PARAMS = ["-movflags", "+faststart"]


def generate_video(
    audio_path: str,
    song_name: str,
    output_path: str,
    theme: dict = None,
) -> None:
    """
    Create an animated MP4 video synced to the given audio file, using the
    procedural ChildrenAnimator fallback (no AI-generated scenes).
    """
    audio = AudioFileClip(audio_path)
    duration = audio.duration

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
    video = video.with_audio(audio)

    video.write_videofile(
        output_path,
        fps=15,
        codec="libx264",
        audio_codec="aac",
        preset="fast",
        threads=4,
        logger=None,
        ffmpeg_params=_FASTSTART_PARAMS,
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
        return clip.with_duration(target_duration)
    return clip.with_speed_scaled(final_duration=target_duration)


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
        video = video.subclipped(0, audio.duration)
    elif video.duration < audio.duration - 0.05:
        pad = audio.duration - video.duration
        freeze = clips[-1].to_ImageClip(t=max(0, clips[-1].duration - 0.04)).with_duration(pad)
        video = concatenate_videoclips([video, freeze], method="compose")

    video = video.with_audio(audio)
    video.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="fast",
        threads=4,
        logger=None,
        ffmpeg_params=_FASTSTART_PARAMS,
    )

    audio.close()
    video.close()
