# AI2-THOR Headless (Cloud Rendering) Docker 환경 설정 가이드

> **환경**: Ubuntu 22.04, NVIDIA GPU, Docker + nvidia-container-toolkit

---

## 문제 상황

AI2-THOR를 Docker 컨테이너 내에서 headless(cloud rendering)로 실행하면 X Display 연결 실패:

```
UserWarning: could not connect to X Display: 6, Can't connect to display ":6": [Errno 111] Connection refused
...
Exception: Platform Linux64 failed validation with the following errors:
Invalid display: :99. Failed to connect
Linux64 requires a X11 server to be running with GLX.
```

---

## 원인

AI2-THOR의 cloud rendering(headless)은 X11/GLX가 아닌 **EGL**을 사용해야 한다. 하지만 Docker 컨테이너 내에서 NVIDIA Vulkan ICD가 자동으로 인식되지 않아, AI2-THOR가 X11 fallback으로 가다가 실패한다.

---

## 해결 과정

### Step 1: Vulkan/GL 런타임 설치

Dockerfile에 Vulkan 및 GL 관련 라이브러리를 설치한다.

```dockerfile
# --- Vulkan/GL 런타임 및 Unity 의존 라이브러리 설치 (LunarG 최신 버전 사용) ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libglvnd0 libgl1 libglx0 libegl1 \
    libglib2.0-0 libx11-6 libxext6 libxrandr2 libxi6 libxrender1 libxfixes3 libxcursor1 libvulkan-dev \
    libnss3 libasound2 ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# --- Vulkan 로더 최신화 (Ubuntu 22.04 = jammy) ---
RUN set -eux; \
    curl -fsSL https://packages.lunarg.com/lunarg-signing-key-pub.asc | gpg --dearmor -o /usr/share/keyrings/lunarg-archive-keyring.gpg; \
    echo "deb [signed-by=/usr/share/keyrings/lunarg-archive-keyring.gpg] https://packages.lunarg.com/vulkan jammy main" > /etc/apt/sources.list.d/lunarg-vulkan.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends libvulkan1 vulkan-tools vulkan-validationlayers; \
    rm -rf /var/lib/apt/lists/*
```

> **주의**: LunarG 저장소의 코드네임(`jammy`)이 Ubuntu 버전과 일치하는지 확인할 것.

### Step 2: 이것만으로는 안 된다

설치 후 `vulkaninfo`를 실행하면 여전히 드라이버를 찾지 못한다:

```
ERROR: [Loader Message] Code 0 : vkCreateInstance: Found no drivers!
Cannot create Vulkan instance.
ERROR at ./vulkaninfo/./vulkaninfo.h:573:vkCreateInstance failed with ERROR_INCOMPATIBLE_DRIVER
```

### Step 3: VK_ICD_FILENAMES 환경변수 설정

Docker Compose에서 NVIDIA EGL ICD 파일 경로를 명시한다:

```yaml
services:
  ttp:
    # ...(기타 설정들)
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=all
      - VK_ICD_FILENAMES=/usr/share/glvnd/egl_vendor.d/10_nvidia.json
```

### Step 4: 이것만으로도 안 된다

```
WARNING: [Loader Message] Code 0 : loader_parse_icd_manifest: ICD JSON
/usr/share/glvnd/egl_vendor.d/10_nvidia.json does not have an 'api_version' field.
Skipping ICD JSON.
```

Vulkan 로더가 해당 JSON 파일에서 `api_version` 필드를 찾지 못해 ICD를 건너뛴다.

### Step 5: api_version 필드 추가 (최종 해결)

`/usr/share/glvnd/egl_vendor.d/10_nvidia.json` 파일에 `"api_version": "1.3"` 필드를 추가해야 한다.

Dockerfile에 다음을 추가:

```dockerfile
# --- Vulkan ICD에 api_version 필드 추가 ---
RUN if [ -f /usr/share/glvnd/egl_vendor.d/10_nvidia.json ]; then \
    python3 -c "import json; \
    f='/usr/share/glvnd/egl_vendor.d/10_nvidia.json'; \
    d=json.load(open(f)); \
    d.setdefault('ICD', d.get('ICD', {}))['api_version'] = '1.3'; \
    json.dump(d, open(f,'w'), indent=4)"; \
    fi
```

또는 수동으로 파일 내용을 확인/수정:

```bash
cat /usr/share/glvnd/egl_vendor.d/10_nvidia.json
# "api_version" : "1.3" 이 있는지 확인
```

---

## 참고

- [StackOverflow: Vulkan unable to detect NVIDIA GPU in Docker](https://stackoverflow.com/questions/74965945/vulkan-is-unable-to-detect-nvidia-gpu-from-within-a-docker-container-when-using)
- AI2-THOR cloud rendering 문서: `CloudRendering` platform을 사용하면 X11 없이 EGL 기반으로 렌더링 가능
