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

# Source/build the workspace setup if needed
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
WORKSPACE_DIR="$SCRIPT_DIR/../ros/ttp_ws"
WORKSPACE_SETUP_FILE="$WORKSPACE_DIR/install/setup.bash"

if [ ! -f "$WORKSPACE_SETUP_FILE" ]; then
    echo "Workspace not built. Running rosdep and colcon build..." >&2
    set -e
    cd "$WORKSPACE_DIR"
    # Install dependencies (ignore missing to avoid hard failure on optional deps)
    rosdep update || true
    rosdep install --from-paths src -r -y || true
    colcon build --symlink-install
    set +e
fi

# Always run an incremental build to pick up any source changes
(
    cd "$WORKSPACE_DIR" && colcon build --symlink-install
) || true

if [ -f "$WORKSPACE_SETUP_FILE" ]; then
    # shellcheck disable=SC1090
    source "$WORKSPACE_SETUP_FILE"
else
    echo "Warning: Workspace setup file still not found at $WORKSPACE_SETUP_FILE." >&2
fi

# Chain execution to the common project environment setup script
exec "$SCRIPT_DIR/run_project.sh" "$@"
