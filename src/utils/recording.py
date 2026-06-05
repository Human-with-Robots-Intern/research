"""Action-cam pull recorder for per-task real-world video capture.

Runs inside the ttp container on the remote PC. Pulls an H.264 / MPEG-TS
stream served by laptop3 (``scripts/infra/serve_actioncam.sh`` encoding
/dev/video8 on port 9986) and remuxes it into an mp4 per task with
``-c:v copy`` (no re-encoding on the ttp side).

Context-manager semantics mean task start = stream open, task end =
stream close, so the remote run_all worker doesn't need any separate
control-plane RPC for recording start/stop.
"""
from __future__ import annotations

import logging
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_CAMERA_HOST = "192.168.0.9"
DEFAULT_CAMERA_PORT = 9986
# Total seconds budgeted for Popen-retry attempts. Each failed attempt
# spends ~1.5s (ffmpeg startup + fail) + 2s backoff (~3.5s/round), and
# a serve_actioncam.sh restart cycle is ~2–4s, so 30s gives roughly 7–8
# rounds — plenty of slack for worst-case v4l2 re-init.
DEFAULT_SERVER_WAIT_SECONDS = 30
# Default 0: with the serve_actioncam.sh layout (ffmpeg -listen 1 in a
# while-loop), a flush session ends up *disconnecting* the server which
# then restarts, and the main recorder that follows races against the
# port being closed — empty videos/ was the symptom. Set >0 only if the
# camera serving stack is later changed to one that keeps the port open
# across clients (nginx-rtmp, mediamtx, ffmpeg without -listen, etc.).
DEFAULT_FLUSH_SECONDS = 0


class ActionCamRecorder:
    """Remux the laptop3 action-cam H.264/MPEG-TS stream to mp4 for one task.

    Args:
        output_dir: directory the mp4 is written to (created if missing).
        file_stem: base filename (no extension); final path is
            ``output_dir/{file_stem}.mp4``.
        host, port: camera stream address (laptop3 running serve_actioncam.sh).
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
        self._stderr_log_path = self.output_dir / f"{self.file_stem}.ffmpeg.log"

        # Do NOT pre-check with a raw TCP connect: the server uses
        # 'ffmpeg -listen 1' which accepts exactly one client and dies on
        # disconnect, so a probe connect would itself consume the slot
        # and force the server back into its sleep-1-and-respawn cycle —
        # the next real attempt then races the restart.
        #
        # Strategy: actually spawn the recorder ffmpeg, give it ~1.5s to
        # either establish a working stream or die with "Connection
        # refused". If it dies, back off while the server respawns and
        # try again. server_wait_seconds caps the total retry budget.
        self._flush_stale_buffer()

        base_cmd = [
            "ffmpeg",
            "-loglevel", "warning",
            # -reconnect_* handles mid-stream drops; initial-connect
            # retries are driven by our Python loop below because
            # ffmpeg's reconnect flags don't reliably cover "refused
            # before the first byte".
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            # Enlarge probe so h264-over-mpegts input can be detected
            # reliably before we try to open the mp4 output. With the
            # defaults (5 MB / 5 s) a freshly-accepted '-listen 1'
            # server occasionally doesn't feed enough bytes in time and
            # ffmpeg gives up with "Could not write header for output
            # file #0 (incorrect codec parameters ?)".
            "-probesize", "10M",
            "-analyzeduration", "10000000",
            "-use_wallclock_as_timestamps", "1",
            "-fflags", "+genpts",
            "-i", self.stream_url,
            "-c:v", "copy",
            # Fragmented mp4: write a valid empty moov up front and emit
            # a new moof per keyframe. With +faststart we had moov-less
            # files whenever ffmpeg didn't reach its post-processing
            # stage (ffprobe: "moov atom not found"). With fragments the
            # file stays playable even if ffmpeg is SIGKILLed — at worst
            # we lose the tail up to the last keyframe.
            "-movflags", "+frag_keyframe+empty_moov+default_base_moof",
            "-y",
            str(self.output_path),
        ]

        deadline = time.monotonic() + max(self.server_wait_seconds, 2)
        attempt = 0
        retry_delay = 2.0
        while True:
            attempt += 1
            # Truncate on first attempt, append on retries so we keep a
            # record of each failure in the same .ffmpeg.log.
            mode = "wb" if attempt == 1 else "ab"
            self._stderr_fh = open(self._stderr_log_path, mode)
            logger.info(
                "[ActionCamRecorder] Start (attempt %d): %s -> %s",
                attempt, self.stream_url, self.output_path,
            )
            proc = subprocess.Popen(
                base_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=self._stderr_fh,
            )
            try:
                # 3s: MPEG-TS input probe with the enlarged probesize
                # needs a second or two of stream data to detect the
                # h264 extradata; 1.5s was truncating probe before it
                # could succeed and the wrapper misread it as a dead
                # process.
                rc = proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                # Still running after 3s → stream is flowing. Success.
                self._proc = proc
                if attempt > 1:
                    logger.info(
                        "[ActionCamRecorder] Recording established on attempt %d.",
                        attempt,
                    )
                return self

            # ffmpeg died during startup — typically "Connection refused"
            # while serve_actioncam.sh is respawning. Close the stderr
            # handle, log a tail, and back off.
            try:
                self._stderr_fh.close()
            except Exception:
                pass
            try:
                tail = self._stderr_log_path.read_text(errors="replace")[-400:]
            except Exception:
                tail = "(stderr unreadable)"
            logger.warning(
                "[ActionCamRecorder] ffmpeg exited rc=%s on attempt %d. "
                "Tail: %s", rc, attempt, tail.strip().splitlines()[-1:],
            )

            if time.monotonic() + retry_delay >= deadline:
                logger.error(
                    "[ActionCamRecorder] Giving up after %d attempts "
                    "(total budget %ds). Task will run without recording.",
                    attempt, self.server_wait_seconds,
                )
                self._proc = None
                return self
            time.sleep(retry_delay)

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
