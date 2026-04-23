#!/usr/bin/env bash
# Streams the XPRO 415 action cam (/dev/video8 on laptop3) as an MJPEG HTTP
# endpoint. Consumed by src/utils/recording.py (ActionCamRecorder) running
# inside the ttp container on the remote PC for per-task real-world video.
#
# Prerequisite: action cam must already be UVC-bound to CAM_DEVICE. If not,
# follow the "XPRO 415 UVC recovery recipe" in auto-memory
# (hardware_actioncam_xpro415_uvc_recipe.md): unbind mass storage interface
# + inject VID/PID into uvcvideo new_id.
#
# Usage:
#   bash scripts/infra/serve_actioncam.sh
#   # Ctrl-C to stop.
#
# Env overrides:
#   CAM_DEVICE (default /dev/video8)
#   CAM_PORT   (default 9986)
#   CAM_SIZE   (default 1280x720)

set -u
CAM_DEVICE="${CAM_DEVICE:-/dev/video8}"
CAM_PORT="${CAM_PORT:-9986}"
CAM_SIZE="${CAM_SIZE:-1280x720}"

echo "[serve_actioncam] device=$CAM_DEVICE size=$CAM_SIZE port=$CAM_PORT"
echo "[serve_actioncam] stream URL: http://0.0.0.0:${CAM_PORT}"

# ffmpeg with -listen 1 exits once the client disconnects; the while loop
# restarts it so the next task can re-connect. This is why ActionCamRecorder
# includes an optional buffer-flush stage — the first frames right after
# server restart can be stale/warm-up frames.
while true; do
    ffmpeg -f v4l2 -video_size "$CAM_SIZE" -i "$CAM_DEVICE" \
        -vf "transpose=2,format=yuvj420p" \
        -c:v mjpeg -q:v 5 -f mpjpeg -listen 1 "http://0.0.0.0:${CAM_PORT}" || true
    echo "[serve_actioncam] ffmpeg exited (code=$?). Restarting in 1s..."
    sleep 1
done
