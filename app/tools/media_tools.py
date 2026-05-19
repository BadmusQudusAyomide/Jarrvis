"""Media download tools powered by yt-dlp.

Downloads are written to a temp directory and deleted by the caller after sending.
No permanent storage is used — safe for Render and other ephemeral hosting.
"""
import logging
import shutil
import tempfile
from pathlib import Path
import yt_dlp
from app.tools.base import BaseTool, ToolSchema, ToolParameter

logger = logging.getLogger(__name__)

TELEGRAM_MAX_BYTES = 50 * 1024 * 1024  # 50 MB — Telegram Bot API hard limit


def _find_newest_file(directory: Path) -> Path | None:
    """Return the most recently modified file inside directory."""
    files = [p for p in directory.iterdir() if p.is_file()]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


class DownloadMediaTool(BaseTool):
    """Download public media from TikTok, Instagram, Facebook, YouTube, Twitter/X, and 1000+ sites."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="download_media",
            description=(
                "Download video or audio from a public social media URL. "
                "Returns a temporary file path — the caller must send the file and then delete it."
            ),
            parameters=[
                ToolParameter(
                    name="url",
                    type="string",
                    description="Public media URL (TikTok, Instagram, Facebook, YouTube, etc.)",
                    required=True,
                ),
                ToolParameter(
                    name="audio_only",
                    type="boolean",
                    description="If true, extract audio as mp3 (requires ffmpeg on the server).",
                    required=False,
                ),
                ToolParameter(
                    name="quality",
                    type="string",
                    description="Video quality: best, medium, or worst. Ignored when audio_only=true.",
                    required=False,
                ),
            ],
            return_type="string",
        )

    def execute(self, url: str, audio_only: bool = False, quality: str = "best", **kwargs) -> str:
        tmp_dir = None
        try:
            if not url or not isinstance(url, str):
                return "Error: 'url' is required"

            quality = (quality or "best").strip().lower()
            if quality not in {"best", "medium", "worst"}:
                quality = "best"

            # Temp dir — automatically isolated per download, deleted by caller after sending
            tmp_dir = Path(tempfile.mkdtemp(prefix="jarvis_dl_"))

            ydl_opts: dict = {
                "outtmpl": str(tmp_dir / "%(title).80s.%(ext)s"),
                "quiet": True,
                "noprogress": True,
                "restrictfilenames": True,  # safe filenames on Windows and Linux
                "noplaylist": True,         # single video only, not whole playlist
            }

            has_ffmpeg = bool(shutil.which("ffmpeg"))

            if audio_only:
                ydl_opts["format"] = "bestaudio/best"
                if has_ffmpeg:
                    ydl_opts["postprocessors"] = [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                    }]
                else:
                    logger.warning("ffmpeg not found — audio will not be converted to mp3")
            else:
                if has_ffmpeg:
                    format_map = {
                        "best":   "bestvideo+bestaudio/best",
                        "medium": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
                        "worst":  "worstvideo+worstaudio/worst",
                    }
                else:
                    # Without ffmpeg, merging streams isn't possible — use single-file formats
                    format_map = {
                        "best":   "best",
                        "medium": "best[height<=480]/best",
                        "worst":  "worst",
                    }
                ydl_opts["format"] = format_map[quality]

            logger.info(f"Downloading from {url} (audio_only={audio_only}, quality={quality}, ffmpeg={has_ffmpeg})")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = (info.get("title") or "media") if info else "media"

            file_path = _find_newest_file(tmp_dir)
            if not file_path:
                return f"Error: download appeared to succeed but no file was found in {tmp_dir}"

            size_bytes = file_path.stat().st_size
            size_mb = size_bytes / (1024 * 1024)
            size_label = f"{size_mb:.1f} MB"

            if size_bytes > TELEGRAM_MAX_BYTES:
                # Clean up — we can't send it anyway
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return (
                    f"Error: '{title}' is {size_label} which exceeds Telegram's 50 MB limit. "
                    f"Try /download <url> quality=medium  or  /download <url> audio_only=true"
                )

            # Return the temp path — bot.py is responsible for deleting after sending
            return f"FILE:{file_path}|TITLE:{title}|SIZE:{size_label}|TMPDIR:{tmp_dir}"

        except yt_dlp.utils.DownloadError as e:
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            err = str(e)
            if "private" in err.lower() or "login" in err.lower() or "age" in err.lower():
                return "Error: This content is private or age-restricted. Only public media can be downloaded."
            return f"Error downloading media: {err}"
        except Exception as e:
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            logger.error(f"Download failed: {e}", exc_info=True)
            return f"Error downloading media: {str(e)}"
