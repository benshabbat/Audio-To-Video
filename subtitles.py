"""
Karaoke-style subtitle burn-in for the final video.

build_srt() turns Gemini's timed lyric_lines into a standard .srt file.
burn_subtitles() hardcodes them onto a video with FFmpeg (via imageio-ffmpeg,
so no system-wide ffmpeg install is required), styled for children:
bright yellow text with a thick black outline for readability.
"""

import os
import shutil
import tempfile
import subprocess

# force_style tuned for a bold, highly readable "kids karaoke" caption
_FORCE_STYLE = (
    "Fontname=Arial,Fontsize=22,Bold=1,"
    "PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,"
    "BorderStyle=1,Outline=2.5,Shadow=1,MarginV=30,Alignment=2"
)


def _srt_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    total_ms = int(round(seconds * 1000))
    hours, rem_ms = divmod(total_ms, 3_600_000)
    minutes, rem_ms = divmod(rem_ms, 60_000)
    secs, ms = divmod(rem_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def build_srt(lyric_lines: list, srt_path: str) -> bool:
    """
    Write lyric_lines ([{"text", "start", "end"}]) to srt_path as an SRT file.
    Returns False (and writes nothing) if there are no usable lines.
    """
    entries = [
        line for line in lyric_lines
        if (line.get("text") or "").strip() and line.get("end", 0) > line.get("start", 0)
    ]
    if not entries:
        return False

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, line in enumerate(entries, start=1):
            f.write(f"{i}\n")
            f.write(f"{_srt_timestamp(line['start'])} --> {_srt_timestamp(line['end'])}\n")
            f.write(f"{line['text'].strip()}\n\n")

    return True


def burn_subtitles(video_path: str, srt_path: str, output_path: str) -> None:
    """
    Hardcode the given .srt onto video_path, writing output_path.
    Raises RuntimeError if ffmpeg fails.

    Runs with cwd set to the subtitle file's own directory and references it
    by bare filename, so the ffmpeg `subtitles` filter (which parses its
    argument with its own colon/backslash escaping rules) never has to deal
    with a Windows drive letter or non-ASCII path components.
    """
    import imageio_ffmpeg

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    work_dir = os.path.dirname(os.path.abspath(srt_path))
    srt_name = os.path.basename(srt_path)
    video_abs = os.path.abspath(video_path)
    output_abs = os.path.abspath(output_path)

    cmd = [
        ffmpeg_exe, "-y",
        "-i", video_abs,
        "-vf", f"subtitles={srt_name}:force_style='{_FORCE_STYLE}'",
        "-c:a", "copy",
        output_abs,
    ]

    result = subprocess.run(
        cmd, cwd=work_dir,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode != 0 or not os.path.isfile(output_abs):
        raise RuntimeError(f"ffmpeg subtitle burn failed: {result.stdout[-1500:]}")


def add_karaoke_subtitles(video_path: str, lyric_lines: list, output_path: str) -> bool:
    """
    Convenience wrapper: builds an SRT from lyric_lines and burns it onto
    video_path, writing output_path. Returns True if subtitles were burned
    in, False if there were no usable lyric lines (caller should then just
    use video_path as the final output).
    """
    tmp_dir = tempfile.mkdtemp(prefix="karaoke_")
    srt_path = os.path.join(tmp_dir, "lyrics.srt")
    try:
        if not build_srt(lyric_lines, srt_path):
            return False
        burn_subtitles(video_path, srt_path, output_path)
        return True
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
