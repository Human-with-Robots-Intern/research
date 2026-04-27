#!/bin/bash
# Watch for task completion flag and play beep sound
# Usage: bash scripts/infra/task_complete_beep.sh

FLAG="/home/laptop3/kyungtae_ws/research/.task_complete"
echo "Watching for task completion..."

while true; do
    if [ -f "$FLAG" ]; then
        echo "[$(date)] Task complete! Beeping..."
        # Try multiple beep methods
        paplay /usr/share/sounds/freedesktop/stereo/complete.oga 2>/dev/null \
            || aplay /usr/share/sounds/alsa/Front_Center.wav 2>/dev/null \
            || printf '\a'
        rm -f "$FLAG"
    fi
    sleep 1
done
