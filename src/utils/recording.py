import subprocess
import signal
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

class DualCameraRecorder:
    def __init__(self, output_dir: Path, file_stem: str, host: str = "192.168.0.9"):
        """
        Context Manager for recording dual camera streams using ffmpeg.
        
        Args:
            output_dir (Path): Directory to save video files.
            file_stem (str): Filename prefix (without extension).
            host (str): Camera host IP address.
        """
        self.output_dir = output_dir
        self.file_stem = file_stem
        self.host = host
        self.processes: List[subprocess.Popen] = []
        
        # Define sources (port, suffix identifier)
        # Assumes HTTP MJPEG streams based on user description.
        # If using RTSP, change input_url in start_recording.
        self.sources = [
            {"port": 9996, "suffix": "cam1"},
            {"port": 9997, "suffix": "cam2"},
        ]

    def __enter__(self):
        self.start_recording()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_recording()

    def start_recording(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        for source in self.sources:
            port = source["port"]
            suffix = source["suffix"]
            output_file = self.output_dir / f"{self.file_stem}_{suffix}.mp4"
            
            # Construct Input URL
            # Note: "-f mjpeg" is often needed for http streams from robot cameras/webcams
            # input_url = f"http://{self.host}:{port}/vnc.html"
            # VNC 웹페이지가 아닌 실제 스트림 URL이 필요합니다.
            input_url = f"http://{self.host}:{port}"

            logger.info(f"Connecting to stream: {input_url}")
            
            # ffmpeg command
            # -y: Overwrite output file
            # -f mjpeg: Force format for input (remove if not mjpeg)
            # -i url: Input source
            # -c:v libx264: Re-encode to H.264 for compatibility
            # -preset ultrafast: Use minimal CPU
            # -pix_fmt yuv420p: Ensure compatibility with players
            cmd = [
                "ffmpeg",
                "-y",
                "-f", "mjpeg", 
                "-i", input_url,
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-pix_fmt", "yuv420p",
                str(output_file)
            ]
            
            # Suppress ffmpeg logs
            cmd.extend(["-loglevel", "error"])

            try:
                # Run in background
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE
                )
                self.processes.append(proc)
                logger.info(f"Started recording {suffix} to {output_file}")
            except FileNotFoundError:
                logger.error("ffmpeg not found. Please install ffmpeg.")
            except Exception as e:
                logger.error(f"Failed to start recording for {suffix}: {e}")

    def stop_recording(self):
        if not self.processes:
            return
            
        logger.info("Stopping recordings...")
        for proc in self.processes:
            if proc.poll() is None:
                # Send SIGINT (CTRL+C) to allow ffmpeg to finalize the file
                proc.send_signal(signal.SIGINT)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning("ffmpeg did not exit gracefully, killing...")
                    proc.kill()
        self.processes = []

