

# ==================================================================================================
# Stage 1: 베이스 이미지 및 기본 환경 설정 (공통 의존성 통합)
# ==================================================================================================
FROM nvidia/cuda:12.5.1-cudnn-devel-ubuntu22.04 AS base

# --- APT Source를 한국 미러(kakao)로 변경 ---
RUN sed -i 's#http://archive.ubuntu.com/ubuntu/#http://mirror.kakao.com/ubuntu/#' /etc/apt/sources.list && \
    sed -i 's#http://security.ubuntu.com/ubuntu/#http://mirror.kakao.com/ubuntu/#' /etc/apt/sources.list

# --- 환경 변수 설정 ---
ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Seoul

# --- 기본 시스템 도구, Python 공통 도구 및 VNC/GUI 설정 ---
# git, curl, build-essential 등은 모든 하위 스테이지에서 공통적으로 사용되므로 여기서 한 번만 설치합니다.
RUN apt update && \
    apt install -y --no-install-recommends \
    # [시스템 기본 도구]
    build-essential \
    git \
    curl \
    wget \
    gnupg \
    locales \
    software-properties-common \
    fonts-liberation \
    # [Python/Graphviz 공통 의존성]
    python3-pip \
    python3-dev \
    graphviz \
    libgraphviz-dev \
    # [GUI/VNC 관련]
    xvfb \
    x11vnc \
    xfce4 \
    xfce4-goodies \
    novnc \
    websockify \
    && \
    # Locale 설정
    locale-gen en_US.UTF-8 && \
    update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 && \
    # apt 캐시 정리
    rm -rf /var/lib/apt/lists/*

# ==================================================================================================
# Stage 2: ROS Humble 설치 (Builder)
# ==================================================================================================
FROM base AS ros_builder

# --- ROS Humble 저장소 설정 및 설치 ---
RUN add-apt-repository universe && \
    curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | tee /etc/apt/sources.list.d/ros2.list > /dev/null && \
    apt update && \
    apt install -y ros-humble-desktop ros-dev-tools ros-humble-rmw-cyclonedds-cpp && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /etc/ros /usr/share/ament_index

# ==================================================================================================
# Stage 3: Python 라이브러리 설치 (TTP)
# ==================================================================================================
FROM base AS python_builder_ttp

# (python3-pip, dev 등은 base에 이미 있음)

# --- PyTorch 인덱스 URL을 ARG로 받음 ---
ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

WORKDIR /app
COPY requirements-ttp.txt .
RUN pip install torch torchvision --index-url $PYTORCH_INDEX_URL && \
    pip install --no-cache-dir -r requirements-ttp.txt
    

# ==================================================================================================
# Stage 4: Python 라이브러리 설치 (ROS)
# ==================================================================================================
FROM base AS python_builder_ros

WORKDIR /app
COPY requirements-ros.txt .
RUN pip install --no-cache-dir -r requirements-ros.txt && \
    pip install --no-cache-dir colcon-common-extensions

# ==================================================================================================
# Stage 5: 공통 런타임 환경 (common_runtime)
# ==================================================================================================
FROM base AS common_runtime

# --- 사용자 설정 ---
ARG UID
ARG GID
ARG USERNAME

ENV UID=${UID} \
    GID=${GID} \
    USERNAME=${USERNAME}

RUN test -n "${UID}" -a -n "${GID}" -a -n "${USERNAME}" && \
    groupadd -g ${GID} ${USERNAME} && \
    useradd -m -u ${UID} -g ${GID} -s /bin/bash ${USERNAME}

# --- Vulkan/GL 및 Unity 의존성 ---
RUN apt update && \
    apt install -y --no-install-recommends \
    libglvnd0 libgl1 libglx0 libegl1 \
    libglib2.0-0 libx11-6 libxext6 libxrandr2 libxi6 libxrender1 libxfixes3 libxcursor1 libvulkan-dev \
    libnss3 libasound2 ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# --- LunarG Vulkan ---
RUN set -eux; \
    curl -fsSL https://packages.lunarg.com/lunarg-signing-key-pub.asc | gpg --dearmor -o /usr/share/keyrings/lunarg-archive-keyring.gpg; \
    echo "deb [signed-by=/usr/share/keyrings/lunarg-archive-keyring.gpg] https://packages.lunarg.com/vulkan jammy main" > /etc/apt/sources.list.d/lunarg-vulkan.list; \
    apt update; \
    apt install -y --no-install-recommends libvulkan1 vulkan-tools vulkan-validationlayers; \
    rm -rf /var/lib/apt/lists/*

# --- 환경 설정 ---
ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    PYTHONPATH="/app${PYTHONPATH:+:${PYTHONPATH}}"

# --- 터미널 편의 기능: novncdisplay 명령어 등록 (모든 사용자 적용) ---
RUN echo '\n\
novncdisplay() {\n\
    local ID=$1\n\
    if [ -z "$ID" ]; then\n\
        echo "Usage: novncdisplay <ID> (e.g. 98)"\n\
        return 1\n\
    fi\n\
    local VNC_PORT=$((5900 + ID))\n\
    local WEB_PORT=$((9900 + ID))\n\
    export DISPLAY=:$ID\n\
    export LIBGL_ALWAYS_SOFTWARE=1\n\
    export QT_QPA_PLATFORM=xcb\n\
    echo "Starting Xvfb on :$ID ..."\n\
    Xvfb :$ID -screen 0 3840x2160x24 -nolisten tcp >/app/logs/xvfb$ID.log 2>&1 &\n\
    sleep 1\n\
    echo "Starting x11vnc on port $VNC_PORT ..."\n\
    x11vnc -display :$ID -forever -shared -rfbport $VNC_PORT -nopw >/app/logs/vnc$ID.log 2>&1 &\n\
    echo "Starting websockify on port $WEB_PORT ..."\n\
    websockify --web=/usr/share/novnc $WEB_PORT localhost:$VNC_PORT >/app/logs/novnc$ID.log 2>&1 &\n\
    echo "Done. Display :$ID is ready at http://localhost:$WEB_PORT/vnc.html"\n\
}' >> /etc/bash.bashrc

WORKDIR /app
RUN chown -R ${USERNAME}:${USERNAME} /app
CMD ["tail", "-f", "/dev/null"]

# ==================================================================================================
# Stage 6: TTP 베이스 이미지 (ttp_base)
# ==================================================================================================
FROM common_runtime AS ttp_base

COPY --from=python_builder_ttp /usr/local/lib/python3.10/dist-packages/ /usr/local/lib/python3.10/dist-packages/
COPY --from=python_builder_ttp /usr/local/bin/ /usr/local/bin/

# ==================================================================================================
# Stage 7: ROS 베이스 이미지 (ros_base)
# ==================================================================================================
FROM common_runtime AS ros_base

COPY --from=python_builder_ros /usr/local/lib/python3.10/dist-packages/ /usr/local/lib/python3.10/dist-packages/
COPY --from=python_builder_ros /usr/local/bin/ /usr/local/bin/

COPY --from=ros_builder /opt/ros/humble /opt/ros/humble
COPY --from=ros_builder /usr/lib/python3/dist-packages/ /usr/lib/python3/dist-packages/
COPY --from=ros_builder /usr/share/ament_index/ /usr/share/ament_index/
COPY --from=ros_builder /etc/ros/ /etc/ros/

RUN echo "/opt/ros/humble/lib" > /etc/ld.so.conf.d/ros2.conf && ldconfig

# ==================================================================================================
# Stage 8: TTP 개발용 이미지 (ttp_development)
# ==================================================================================================
FROM ttp_base AS ttp_development

# (base에 이미 설치된 패키지 제외하고 필요한 것만 남김 -> 사실상 base에 다 있어서 제거 가능하지만, 혹시 몰라 명시적 확인)
# TTP 개발 환경은 base의 도구들로 충분하므로, 추가적인 apt install은 생략 가능하나,
# NVIDIA/OpenGL 설정은 필수입니다.

# --- NVIDIA OpenGL/EGL 설정 ---
COPY --from=nvidia/opengl:1.0-glvnd-runtime-ubuntu22.04 \
     /usr/lib/x86_64-linux-gnu \
     /usr/lib/x86_64-linux-gnu

# NVIDIA EGL Vendor 설정 파일 생성 (api_version 1.3 포함)
# NVIDIA Runtime이 /usr/share/glvnd를 덮어쓰므로 /opt에 생성
# "api_version" : "1.3 을 적어줘야 현재 버전에서 작동하는데 덮어쓰면 권한문제가 심각함. 임의로 생성.
RUN mkdir -p /opt/egl_vendor.d && \
    echo '{\n\
    "file_format_version" : "1.0.0",\n\
    "ICD" : {\n\
        "library_path" : "libEGL_nvidia.so.0",\n\
        "api_version" : "1.3"\n\
    }\n\
}' > /opt/egl_vendor.d/10_nvidia.json

RUN echo '/usr/lib/x86_64-linux-gnu' >> /etc/ld.so.conf.d/glvnd.conf && \
    ldconfig && \
    echo '/usr/lib/x86_64-linux-gnu/libGL.so.1' >> /etc/ld.so.preload && \
    echo '/usr/lib/x86_64-linux-gnu/libEGL.so.1' >> /etc/ld.so.preload

USER $USERNAME
CMD ["tail", "-f", "/dev/null"]

# ==================================================================================================
# Stage 9: ROS 개발용 이미지 (ros_development)
# ==================================================================================================
FROM ros_base AS ros_development

# --- 개발 및 ROS 전용 추가 도구 설치 ---
# (base에 있는 git, curl, build-essential 등은 제거하고 ROS 및 Dev 특화 패키지만 설치)
RUN apt update && \
    apt install -y --no-install-recommends \
    # [개발 도구]
    nano \
    cmake \
    iputils-ping \
    iproute2 \
    ethtool \
    # [라이브러리]
    libpoco-dev \
    libeigen3-dev \
    libtinyxml2-9 \
    libconsole-bridge1.0 \
    libspdlog1 \
    libyaml-cpp0.7 \
    libassimp5 \
    # [GUI/Qt 관련]
    python3-pyqt5 \
    python3-pyqt5.qtsvg \
    libqt5svg5 \
    libxkbcommon-x11-0 && \
    rm -rf /var/lib/apt/lists/*

# --- ROS APT 저장소 등록 및 추가 패키지 설치 ---
# ros_base는 파일을 복사해왔지만, apt 패키지 매니저는 이를 모르므로
# 추가 설치(ros-humble-ur 등)를 위해 저장소 등록이 다시 필요합니다.
RUN set -eux; \
    add-apt-repository -y universe; \
    curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg; \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" > /etc/apt/sources.list.d/ros2.list; \
    apt update; \
    # 필요한 ROS 추가 패키지 설치
    apt install -y --no-install-recommends \
    ros-humble-ur \
    ros-humble-desktop \
    ros-humble-nav2-msgs \
    libmodbus-dev \
    ros-humble-realsense2-camera \
    ros-humble-librealsense2* ; \
    rm -rf /var/lib/apt/lists/*

USER $USERNAME

# --- 터미널 실행 시 자동으로 ROS 환경 설정 로드 ---
RUN echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc && \
    echo "if [ -f /app/ros/ttp_ws/install/setup.bash ]; then source /app/ros/ttp_ws/install/setup.bash; fi" >> ~/.bashrc && \
    echo "if [ -f /app/ros/moveit_proxy_ws/install/setup.bash ]; then source /app/ros/moveit_proxy_ws/install/setup.bash; fi" >> ~/.bashrc
