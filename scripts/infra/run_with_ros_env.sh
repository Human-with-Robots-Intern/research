#!/bin/bash
# This script sets up only the ROS environment and then passes execution
# to run_project.sh for further setup and command execution.

set -e # 에러 발생 시 즉시 중단

# --- 1. 기본 ROS 환경 설정 ---
if [ -f "/opt/ros/humble/setup.bash" ]; then
    source "/opt/ros/humble/setup.bash"
else
    echo "Error: ROS setup file not found at /opt/ros/humble/setup.bash" >&2
    exit 1
fi

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
PROJECT_ROOT=$( realpath "$SCRIPT_DIR/../.." )

# --- 2. 워크스페이스 빌드 및 설정 함수 ---
build_and_source_ws() {
    local ws_name=$1
    local ws_dir="$PROJECT_ROOT/ros/$ws_name"
    local setup_file="$ws_dir/install/setup.bash"

    if [ -d "$ws_dir/src" ]; then
        echo ">>> Building workspace: $ws_name"
        # 빌드 수행 (실패 시 스크립트 중단)
        (cd "$ws_dir" && colcon build --symlink-install --cmake-args -DCMAKE_EXPORT_COMPILE_COMMANDS=ON)
        
        if [ -f "$setup_file" ]; then
            echo ">>> Sourcing workspace: $ws_name"
            source "$setup_file"
        else
             echo "Warning: Setup file not found for $ws_name after build." >&2
        fi
    else
        echo "Warning: Workspace directory not found at $ws_dir" >&2
    fi
}

# --- 3. 워크스페이스 순차 빌드 ---
# 의존성 순서가 있다면 순서를 조정하세요 (예: 메시지 패키지가 있는 ws 먼저)
build_and_source_ws "moveit_proxy_ws"
build_and_source_ws "ttp_ws"

# Chain execution to the common project environment setup script
exec "$SCRIPT_DIR/run_project.sh" "$@"
