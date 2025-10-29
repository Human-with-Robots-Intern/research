# Dockerfile 최종 수정본

# ==================================================================================================
# Stage 1: 베이스 이미지 및 기본 환경 설정
# ==================================================================================================
FROM nvidia/cuda:12.5.1-cudnn-devel-ubuntu22.04 AS base

# --- APT Source를 한국 미러(kakao)로 변경 ---
RUN sed -i 's#http://archive.ubuntu.com/ubuntu/#http://mirror.kakao.com/ubuntu/#' /etc/apt/sources.list && \
    sed -i 's#http://security.ubuntu.com/ubuntu/#http://mirror.kakao.com/ubuntu/#' /etc/apt/sources.list

# --- 환경 변수 설정 ---
# 자동 빌드를 위한 설정 및 시간대 설정
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul

# --- 기본 시스템 도구 및 Locale 설정 ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    wget \
    gnupg \
    locales \
    software-properties-common \
    fonts-liberation \
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
# Stage 2: ROS Humble 설치
# ==================================================================================================
FROM base AS ros_builder

# --- ROS Humble 저장소 설정 및 설치 ---
RUN add-apt-repository universe && \
    curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | tee /etc/apt/sources.list.d/ros2.list > /dev/null && \
    apt-get update && \
    apt-get install -y ros-humble-desktop ros-dev-tools ros-humble-rmw-cyclonedds-cpp && \
    rm -rf /var/lib/apt/lists/* && \
    # COPY 명령어의 대상 디렉토리가 존재하도록 보장
    mkdir -p /etc/ros /usr/share/ament_index

# ==================================================================================================
# Stage 3: Python 라이브러리 설치 (TTP)
# ==================================================================================================
FROM base AS python_builder_ttp

# --- Python 및 관련 도구 설치 ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3-pip graphviz libgraphviz-dev python3-dev && \
    rm -rf /var/lib/apt/lists/*

# --- 파이썬 라이브러리 설치 ---
WORKDIR /app
COPY requirements-ttp.txt .
RUN pip install --no-cache-dir -r requirements-ttp.txt

# ==================================================================================================
# Stage 4: Python 라이브러리 설치 (ROS)
# ==================================================================================================
FROM base AS python_builder_ros

# --- Python 및 관련 도구 설치 ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3-pip graphviz libgraphviz-dev python3-dev && \
    rm -rf /var/lib/apt/lists/*

# --- 파이썬 라이브러리 설치 ---
WORKDIR /app
COPY requirements-ros.txt .
RUN pip install --no-cache-dir -r requirements-ros.txt && \
    pip install --no-cache-dir colcon-common-extensions


# ==================================================================================================
# Stage 5: 공통 런타임 환경 (common_runtime)
# ==================================================================================================
FROM base AS common_runtime

# --- 호스트 사용자와 동일한 ID를 가진 사용자 생성 ---
ARG UID
ARG GID
ARG USERNAME
RUN groupadd -g $GID -o ${USERNAME} && \
    useradd -u $UID -g $GID -o -m -s /bin/bash ${USERNAME}

# --- Vulkan/GL 런타임 및 Unity 의존 라이브러리 설치 (LunarG 최신 버전 사용) ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libglvnd0 libgl1 libglx0 libegl1 \
    libglib2.0-0 libx11-6 libxext6 libxrandr2 libxi6 libxrender1 libxfixes3 libxcursor1 \
    libnss3 libasound2 ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# --- Vulkan 로더 최신화 및 NVIDIA EGL ICD 설정 ---
RUN set -eux; \
    curl -fsSL https://packages.lunarg.com/lunarg-signing-key-pub.asc | gpg --dearmor -o /usr/share/keyrings/lunarg-archive-keyring.gpg; \
    echo "deb [signed-by=/usr/share/keyrings/lunarg-archive-keyring.gpg] https://packages.lunarg.com/vulkan jammy main" > /etc/apt/sources.list.d/lunarg-vulkan.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends libvulkan1 vulkan-tools vulkan-validationlayers; \
    rm -rf /var/lib/apt/lists/*; \
    mkdir -p /etc/vulkan/icd.d; \
    printf '{\n    "file_format_version": "1.0.1",\n    "ICD": {\n        "library_path": "libEGL_nvidia.so.0",\n        "api_version": "1.4.303"\n    }\n}\n' > /etc/vulkan/icd.d/nvidia_egl_icd.json; \
    printf '{\n    "file_format_version": "1.0.0",\n    "ICD": {\n        "library_path": "libvulkan_nvidia.so",\n        "api_version": "1.3.0"\n    }\n}\n' > /etc/vulkan/icd.d/nvidia_layers.json

# --- 환경 변수 설정 ---
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV PYTHONPATH="/app${PYTHONPATH:+:${PYTHONPATH}}"

# --- 작업 디렉토리 설정 및 권한 부여 ---
WORKDIR /app
RUN chown -R ${USERNAME}:${USERNAME} /app

# --- 컨테이너 기본 실행 명령어 ---
CMD ["tail", "-f", "/dev/null"]

# ==================================================================================================
# Stage 6: TTP 베이스 이미지 (ttp_base)
# ==================================================================================================
FROM common_runtime AS ttp_base

# --- Python 라이브러리 복사 ---
COPY --from=python_builder_ttp /usr/local/lib/python3.10/dist-packages/ /usr/local/lib/python3.10/dist-packages/
COPY --from=python_builder_ttp /usr/local/bin/ /usr/local/bin/

# ==================================================================================================
# Stage 7: ROS 베이스 이미지 (ros_base)
# ==================================================================================================
FROM common_runtime AS ros_base

# --- ROS용 Python 라이브러리 복사 ---
COPY --from=python_builder_ros /usr/local/lib/python3.10/dist-packages/ /usr/local/lib/python3.10/dist-packages/
COPY --from=python_builder_ros /usr/local/bin/ /usr/local/bin/

# --- ROS 관련 파일 복사 ---
COPY --from=ros_builder /opt/ros/humble /opt/ros/humble
COPY --from=ros_builder /usr/lib/python3/dist-packages/ /usr/lib/python3/dist-packages/
COPY --from=ros_builder /usr/share/ament_index/ /usr/share/ament_index/
COPY --from=ros_builder /etc/ros/ /etc/ros/

# --- ROS 환경 자동 설정 ---
RUN echo "source /opt/ros/humble/setup.bash" >> /home/$USERNAME/.bashrc

# ==================================================================================================
# Stage 8: TTP 개발용 이미지 (ttp_development)
# ==================================================================================================
FROM ttp_base AS ttp_development

# --- 개발에 필요한 빌드 도구들 설치 ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    wget \
    gnupg \
    python3-pip \
    graphviz \
    libgraphviz-dev \
    fonts-liberation && \
    rm -rf /var/lib/apt/lists/*

USER $USERNAME

# ==================================================================================================
# Stage 9: ROS 개발용 이미지 (ros_development)
# ==================================================================================================
FROM ros_base AS ros_development

# --- 개발에 필요한 빌드 도구들 설치 ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    wget \
    gnupg \
    cmake \
    python3-pip \
    python3-dev \
    graphviz \
    libgraphviz-dev \
    fonts-liberation \
    libtinyxml2-9 \
    libconsole-bridge1.0 \
    libpython3.10 \
    libspdlog1 && \
    rm -rf /var/lib/apt/lists/*

USER $USERNAME