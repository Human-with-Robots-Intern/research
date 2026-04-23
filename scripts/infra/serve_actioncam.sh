#!/usr/bin/env bash
# Streams the XPRO 415 action cam (/dev/video8 on laptop3) over HTTP as an
# H.264 / MPEG-TS stream. Consumed by src/utils/recording.py
# (ActionCamRecorder) running inside the ttp container on the remote PC
# for per-task real-world video.
#
# Why H.264+MPEG-TS (not the older MJPG+mpjpeg): the camera's native pixel
# format is MJPG 1280x720@30 (~12 Mbps, 1 min ≈ 90 MB) and passing it
# through unchanged saturated the LAN and produced ~100 MB files on the
# ttp side. Encoding to H.264 on laptop3 cuts both by roughly 10x at
# -preset ultrafast -crf 28 (720p fits in ~1 Mbps, files ~10 MB/min),
# and ttp just remuxes with -c:v copy — ttp CPU cost stays near zero.
#
# Prerequisite: action cam must already be UVC-bound to CAM_DEVICE. If not,
# follow the "XPRO 415 UVC recovery recipe" in auto-memory
# (hardware_actioncam_xpro415_uvc_recipe.md): unbind mass storage interface
# + inject VID/PID into uvcvideo new_id + unplug/replug.
#
# Usage:
#   bash scripts/infra/serve_actioncam.sh
#   # Ctrl-C to stop.
#
# Env overrides:
#   CAM_DEVICE (default /dev/video8)
#   CAM_PORT   (default 9986)
#   CAM_SIZE   (default 1280x720)
#   CAM_PRESET (default ultrafast)  — x264 -preset (ultrafast/superfast/veryfast/…)
#   CAM_CRF    (default 28)         — x264 -crf. Lower = better quality, bigger file
#   CAM_GOP    (default 30)         — keyframe interval (every N frames)

set -u
CAM_DEVICE="${CAM_DEVICE:-/dev/video8}"
CAM_PORT="${CAM_PORT:-9986}"
CAM_SIZE="${CAM_SIZE:-1280x720}"
CAM_PRESET="${CAM_PRESET:-ultrafast}"
CAM_CRF="${CAM_CRF:-28}"
CAM_GOP="${CAM_GOP:-30}"

echo "[serve_actioncam] device=$CAM_DEVICE size=$CAM_SIZE port=$CAM_PORT codec=h264 preset=$CAM_PRESET crf=$CAM_CRF gop=$CAM_GOP"
echo "[serve_actioncam] stream URL: http://0.0.0.0:${CAM_PORT} (MPEG-TS / H.264)"

# ffmpeg with -listen 1 exits once the client disconnects; the while loop
# restarts it so the next task can re-connect.
#
# - -input_format mjpeg + -framerate 30 pin the negotiation (camera only
#   advertises MJPG 1280x720@30); without these ffmpeg stalls in v4l2 init
#   and the -listen 1 output muxer never binds.
# - -tune zerolatency disables B-frames and keeps the encoder pipeline
#   short — the client ffmpeg needs to start receiving TS packets
#   promptly after connect, otherwise our 1.5s "alive" check on the
#   recorder side gives up.
# - format=yuv420p (note: NOT yuvj420p) is required by libx264 / mp4.
while true; do
    ffmpeg -f v4l2 -input_format mjpeg -video_size "$CAM_SIZE" -framerate 30 \
        -i "$CAM_DEVICE" \
        -vf "transpose=2,format=yuv420p" \
        -c:v libx264 -preset "$CAM_PRESET" -tune zerolatency \
        -pix_fmt yuv420p -g "$CAM_GOP" -crf "$CAM_CRF" \
        -f mpegts -listen 1 "http://0.0.0.0:${CAM_PORT}" || true
    echo "[serve_actioncam] ffmpeg exited (code=$?). Restarting in 1s..."
    sleep 1
done
