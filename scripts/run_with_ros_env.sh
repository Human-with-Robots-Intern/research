#!/bin/bash
# This script sets up the required ROS and project environment and then executes the given command.

# Source the main ROS setup file
if [ -f "/opt/ros/humble/setup.bash" ]; then
    source "/opt/ros/humble/setup.bash"
else
    echo "Error: ROS setup file not found at /opt/ros/humble/setup.bash" >&2
    exit 1
fi

# Source the workspace setup file
# Get the directory of the current script to find the workspace root relative to it.
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
WORKSPACE_SETUP_FILE="$SCRIPT_DIR/../src/ros/ttp_ws/install/setup.bash"

if [ -f "$WORKSPACE_SETUP_FILE" ]; then
    source "$WORKSPACE_SETUP_FILE"
else
    echo "Warning: Workspace setup file not found at $WORKSPACE_SETUP_FILE. Continuing without it." >&2
fi

# Add the project root to PYTHONPATH to handle imports like `from src...` and `from ithor...`
PROJECT_ROOT=$( realpath "$SCRIPT_DIR/.." )
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# Execute the command passed to this script
exec "$@" 