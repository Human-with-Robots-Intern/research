#!/bin/bash
# This script sets up only the ROS environment and then passes execution
# to run_project.sh for further setup and command execution.

# Source the main ROS setup file
if [ -f "/opt/ros/humble/setup.bash" ]; then
    source "/opt/ros/humble/setup.bash"
else
    echo "Error: ROS setup file not found at /opt/ros/humble/setup.bash" >&2
    exit 1
fi

# Source the workspace setup file
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
WORKSPACE_SETUP_FILE="$SCRIPT_DIR/../src/ros/ttp_ws/install/setup.bash"

if [ -f "$WORKSPACE_SETUP_FILE" ]; then
    source "$WORKSPACE_SETUP_FILE"
else
    echo "Warning: Workspace setup file not found at $WORKSPACE_SETUP_FILE. Continuing without it." >&2
fi

# Chain execution to the common project environment setup script
exec "$SCRIPT_DIR/run_project.sh" "$@" 