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
import socket
import subprocess
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_CAMERA_HOST = "192.168.0.9"
DEFAULT_CAMERA_PORT = 9986
# Max seconds to wait for the MJPEG server (serve_actioncam.sh) to come
# back into a listening state between tasks. Each client disconnect
# causes the server's 'ffmpeg -listen 1' to exit and the shell loop to
# respawn it after a `sleep 1` + v4l2 re-init — usually 2–4s.
DEFAULT_SERVER_WAIT_SECONDS = 15
# Default 0: with the serve_actioncam.sh layout (ffmpeg -listen 1 in a
# while-loop), a flush session ends up *disconnecting* the server which
# then restarts, and the main recorder that follows races against the
# port being closed — empty videos/ was the symptom. Set >0 only if the
# camera serving stack is later changed to one that keeps the port open
# across clients (nginx-rtmp, mediamtx, ffmpeg without -listen, etc.).
DEFAULT_FLUSH_SECONDS = 0


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
        server_wait_seconds: int = DEFAULT_SERVER_WAIT_SECONDS,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.file_stem = file_stem
        self.host = host
        self.port = port
        self.flush_seconds = max(0, int(flush_seconds))
        self.server_wait_seconds = max(0, int(server_wait_seconds))
        self.stream_url = f"http://{host}:{port}"
        self.output_path: Optional[Path] = None
        self._proc: Optional[subprocess.Popen] = None
        self._stderr_fh = None
        self._stderr_log_path: Optional[Path] = None

    def _wait_for_server(self) -> bool:
        """Block until ``host:port`` accepts TCP connections or timeout.

        The laptop3 MJPEG server cycles ffmpeg per client (``-listen 1`` +
        while-loop), so between two tasks there is a gap of a few seconds
        where the port is closed. Starting the recorder's ffmpeg during
        that gap produces "Connection refused" and an empty mp4 — this
        pre-check avoids that race.
        """
        if self.server_wait_seconds <= 0:
            return True
        deadline = time.monotonic() + self.server_wait_seconds
        delay = 0.25
        attempts = 0
        while time.monotonic() < deadline:
            attempts += 1
            try:
                with socket.create_connection((self.host, self.port), timeout=1.0):
                    if attempts > 1:
                        logger.info(
                            "[ActionCamRecorder] Server %s:%d accepted after %d attempt(s).",
                            self.host, self.port, attempts,
                        )
                    return True
            except (OSError, socket.timeout):
                pass
            time.sleep(delay)
            delay = min(1.0, delay * 1.5)
        logger.error(
            "[ActionCamRecorder] Timed out waiting %ds for %s:%d to listen.",
            self.server_wait_seconds, self.host, self.port,
        )
        return False

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

        # The serve_actioncam.sh server restarts ffmpeg between clients,
        # so we must wait for :port to come back up before launching our
        # own ffmpeg — otherwise it dies instantly with "Connection refused".
        if not self._wait_for_server():
            self._proc = None
            return self

        self._flush_stale_buffer()

        # NOTE: do NOT pass -nostdin here. The __exit__ path writes 'q' to
        # ffmpeg's stdin to trigger a graceful shutdown (so the mp4 moov
        # atom gets finalized); -nostdin makes ffmpeg ignore stdin, which
        # forces us down the SIGKILL fallback and corrupts the file.
        # -reconnect_* covers the case where the server drops mid-stream.
        cmd = [
            "ffmpeg",
            "-loglevel", "warning",
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
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
        # Keep stderr in a sibling log file so recorder failures (e.g. the
        # server hasn't re-bound :9986 yet) leave a trace — previously the
        # recorder could die silently because stderr was /dev/null.
        self._stderr_log_path = self.output_dir / f"{self.file_stem}.ffmpeg.log"
        self._stderr_fh = open(self._stderr_log_path, "wb")
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=self._stderr_fh,
        )

        # Fail fast if the main recorder died before opening the output
        # (connection refused, wrong URL, etc.). Without this the worker
        # keeps running thinking recording is on.
        time.sleep(1.0)
        if self._proc.poll() is not None:
            rc = self._proc.returncode
            try:
                tail = self._stderr_log_path.read_text(errors="replace")[-500:]
            except Exception:
                tail = "(stderr unreadable)"
            logger.error(
                "[ActionCamRecorder] ffmpeg exited immediately (rc=%s). "
                "Last stderr: %s",
                rc,
                tail,
            )
            self._proc = None
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
            try:
                if self._stderr_fh is not None:
                    self._stderr_fh.close()
            except Exception:
                pass
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
