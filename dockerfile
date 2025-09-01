# Dockerfile 최종 수정본

# 1. 베이스 이미지 선택
FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04

# 2. 자동 빌드를 위한 환경 변수 설정
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul

# 3. 시스템 의존성 및 ROS 설치
RUN apt-get update && apt-get install -y \
    # --- 기본 시스템 도구 및 pip ---
    build-essential \
    git \
    curl \
    wget \
    locales \
    python3-pip \
    python3-venv \
    graphviz \
    libgraphviz-dev \
    # --- NVIDIA Container Toolkit ---
    # nvidia-container-toolkit \
    # --- ROS Humble 설치에 필요한 도구 ---
    software-properties-common \
    && rm -rf /var/lib/apt/lists/* \
    # --- Locale (언어/지역 설정) 구성 ---
    && locale-gen en_US.UTF-8 \
    && update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
    # --- ROS Humble 설치 ---
    && add-apt-repository universe \
    && curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | tee /etc/apt/sources.list.d/ros2.list > /dev/null \
    && apt-get update \
    && apt-get install -y ros-humble-desktop ros-dev-tools \
    && rm -rf /var/lib/apt/lists/*

# 4. 파이썬 가상 환경 생성 및 설정
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 5. 환경 변수 설정
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV PYTHONPATH="/app${PYTHONPATH:+:${PYTHONPATH}}"

# 6. 작업 디렉토리 설정
WORKDIR /app

# 7. 파이썬 라이브러리 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 8. 프로젝트 소스 코드 복사
# 배포가 필요하면 다시 주석 해제
# COPY . .

# 9. ROS 환경 자동 설정
RUN echo "source /opt/ros/humble/setup.bash" >> /root/.bashrc

# 10. 컨테이너 기본 실행 명령어
CMD ["tail", "-f", "/dev/null"]