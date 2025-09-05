# Dockerfile 최종 수정본

# ==================================================================================================
# Stage 1: 베이스 이미지 및 기본 환경 설정
# ==================================================================================================
FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04 AS base

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
    apt-get install -y ros-humble-desktop ros-dev-tools && \
    rm -rf /var/lib/apt/lists/* && \
    # COPY 명령어의 대상 디렉토리가 존재하도록 보장
    mkdir -p /etc/ros /usr/share/ament_index

# ==================================================================================================
# Stage 3: Python 가상 환경 및 라이브러리 설치
# ==================================================================================================
FROM base AS python_builder

# --- Python 가상 환경 생성 ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3-pip python3-venv graphviz libgraphviz-dev python3-dev && \
    rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# --- 파이썬 라이브러리 설치 ---
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ==================================================================================================
# Stage 4: 최종 이미지 생성
# ==================================================================================================
FROM base AS final

# --- 이전 스테이지에서 빌드된 결과물 복사 ---
COPY --from=ros_builder /opt/ros/humble /opt/ros/humble
COPY --from=ros_builder /usr/lib/python3/dist-packages/ /usr/lib/python3/dist-packages/
COPY --from=ros_builder /usr/share/ament_index/ /usr/share/ament_index/
COPY --from=ros_builder /etc/ros/ /etc/ros/

COPY --from=python_builder /opt/venv /opt/venv

# --- Vulkan/GL 런타임 및 Unity 의존 라이브러리 설치 ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libvulkan1 vulkan-tools \
    libglvnd0 libgl1 libglx0 libegl1 \
    libglib2.0-0 libx11-6 libxext6 libxrandr2 libxi6 libxrender1 libxfixes3 libxcursor1 \
    libnss3 libasound2 ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# --- Vulkan 로더 최신화 및 NVIDIA EGL ICD 설정 ---
RUN set -eux; \
    curl -fsSL https://packages.lunarg.com/lunarg-signing-key-pub.asc | gpg --dearmor -o /usr/share/keyrings/lunarg-archive-keyring.gpg; \
    echo "deb [signed-by=/usr/share/keyrings/lunarg-archive-keyring.gpg] https://packages.lunarg.com/vulkan jammy main" > /etc/apt/sources.list.d/lunarg-vulkan.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends libvulkan1 vulkan-tools; \
    rm -rf /var/lib/apt/lists/*; \
    mkdir -p /etc/vulkan/icd.d; \
    printf '{\n    "file_format_version": "1.0.1",\n    "ICD": {\n        "library_path": "libEGL_nvidia.so.0",\n        "api_version": "1.4.303"\n    }\n}\n' > /etc/vulkan/icd.d/nvidia_egl_icd.json

# --- 환경 변수 설정 ---
ENV PATH="/opt/venv/bin:$PATH"
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV PYTHONPATH="/app${PYTHONPATH:+:${PYTHONPATH}}"

# --- 작업 디렉토리 설정 ---
WORKDIR /app

# --- nvidia_icd.json 복사 ---
COPY nvidia_icd.json /etc/vulkan/icd.d

# --- 프로젝트 소스 코드 복사 (필요시 주석 해제) ---
# COPY . .

# --- ROS 환경 자동 설정 및 .bashrc 정리 ---
RUN echo "source /opt/ros/humble/setup.bash" >> /root/.bashrc && \
    echo "source /opt/venv/bin/activate" >> /root/.bashrc

# --- 컨테이너 기본 실행 명령어 ---
CMD ["tail", "-f", "/dev/null"]


# ==================================================================================================
# Stage 5: 개발용 이미지 생성 (Development Image)
# ==================================================================================================
FROM final AS development

# --- 개발에 필요한 빌드 도구들 다시 설치 ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    wget \
    gnupg \
    python3-pip \
    python3-venv \
    graphviz \
    libgraphviz-dev \
    fonts-liberation && \
    rm -rf /var/lib/apt/lists/*