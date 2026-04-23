"""Action-cam MJPEG pull recorder for per-task real-world video capture.

Runs inside the ttp container on the remote PC. Pulls an MJPEG stream
served by laptop3 (``scripts/infra/serve_actioncam.sh`` streaming
/dev/video8 on port 9986) and saves it as an mp4 per task.

Context-manager semantics mean task start = stream open, task end =
stream close, so the remote run_all worker doesn't need any separate
control-plane RPC for recording start/stop.
"""
from __future__ import annotations

import logging
import signal
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_CAMERA_HOST = "192.168.0.9"
DEFAULT_CAMERA_PORT = 9986
DEFAULT_FLUSH_SECONDS = 5


class ActionCamRecorder:
    """Record the laptop3 action-cam MJPEG stream to mp4 for one task.

    Args:
        output_dir: directory the mp4 is written to (created if missing).
        file_stem: base filename (no extension); final path is
            ``output_dir/{file_stem}.mp4``.
        host, port: MJPEG server address (laptop3 running serve_actioncam.sh).
        flush_seconds: seconds to pre-consume from the stream before
            starting the real recording. The ffmpeg server uses ``-listen 1``
            and restarts via a while-loop after each client disconnect, so
            the first frames of a fresh connection can be warm-up/stale
            (encoder re-init, UVC device buffer). Setting this to 0 skips
            the flush stage.
    """

    def __init__(
        self,
        output_dir: Path,
        file_stem: str,
        host: str = DEFAULT_CAMERA_HOST,
        port: int = DEFAULT_CAMERA_PORT,
        flush_seconds: int = DEFAULT_FLUSH_SECONDS,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.file_stem = file_stem
        self.host = host
        self.port = port
        self.flush_seconds = max(0, int(flush_seconds))
        self.stream_url = f"http://{host}:{port}"
        self.output_path: Optional[Path] = None
        self._proc: Optional[subprocess.Popen] = None

    def _flush_stale_buffer(self) -> None:
        if self.flush_seconds <= 0:
            return
        logger.info(
            "[ActionCamRecorder] Flushing stale MJPEG buffer for %ds...",
            self.flush_seconds,
        )
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-loglevel", "error",
                    "-i", self.stream_url,
                    "-t", str(self.flush_seconds),
                    "-f", "null", "-",
                ],
                timeout=self.flush_seconds + 10,
                check=False,
            )
        except subprocess.TimeoutExpired:
            logger.warning("[ActionCamRecorder] Flush stage timeout (ignored).")
        except Exception as e:
            logger.warning("[ActionCamRecorder] Flush stage error (ignored): %s", e)

    def __enter__(self) -> "ActionCamRecorder":
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.output_path = self.output_dir / f"{self.file_stem}.mp4"

        self._flush_stale_buffer()

        # NOTE: do NOT pass -nostdin here. The __exit__ path writes 'q' to
        # ffmpeg's stdin to trigger a graceful shutdown (so the mp4 moov
        # atom gets finalized); -nostdin makes ffmpeg ignore stdin, which
        # forces us down the SIGKILL fallback and corrupts the file.
        cmd = [
            "ffmpeg",
            "-loglevel", "warning",
            "-use_wallclock_as_timestamps", "1",
            "-fflags", "+genpts",
            "-i", self.stream_url,
            "-c:v", "copy",
            "-movflags", "+faststart",
            "-y",
            str(self.output_path),
        ]
        logger.info(
            "[ActionCamRecorder] Start: %s -> %s", self.stream_url, self.output_path
        )
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            # Preferred path: send 'q' to stdin so ffmpeg writes the trailer
            # (mp4 moov atom) before exiting. SIGKILL leaves an unplayable
            # truncated file; SIGINT/SIGTERM do let ffmpeg finalize, so keep
            # them as fallbacks.
            graceful = False
            try:
                if proc.stdin is not None:
                    proc.stdin.write(b"q")
                    proc.stdin.flush()
                    proc.stdin.close()
                proc.wait(timeout=5)
                graceful = True
            except subprocess.TimeoutExpired:
                pass
            except Exception:
                pass

            if not graceful:
                proc.send_signal(signal.SIGINT)
                try:
                    proc.wait(timeout=5)
                    graceful = True
                except subprocess.TimeoutExpired:
                    pass

            if not graceful:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                    graceful = True
                except subprocess.TimeoutExpired:
                    pass

            if not graceful:
                logger.warning(
                    "[ActionCamRecorder] ffmpeg ignored q/SIGINT/SIGTERM; "
                    "SIGKILLing (output mp4 may be truncated)."
                )
                proc.kill()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            self._proc = None
            if self.output_path and self.output_path.exists():
                size_mb = self.output_path.stat().st_size / (1024 * 1024)
                logger.info(
                    "[ActionCamRecorder] Saved: %s (%.1f MB)",
                    self.output_path,
                    size_mb,
                )
            else:
                logger.warning(
                    "[ActionCamRecorder] Output file missing or empty: %s",
                    self.output_path,
                )
