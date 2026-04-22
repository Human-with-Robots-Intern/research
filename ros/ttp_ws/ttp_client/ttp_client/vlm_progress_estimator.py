"""VLM-based cooking progress estimator for monitoring actions.

Captures a frame from the RealSense camera and queries an OpenAI VLM
to estimate the cooking/preparation progress as an integer in [0, 130]
(step 10).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import numpy as np

# Directory where VLM call logs (input image + prompt + response) are saved
VLM_LOG_DIR = Path("/app/assets/results/vlm_logs")

# Directory containing image few-shot examples:
#   <FEW_SHOT_DIR>/<subdir>/progress_<NNN>.jpg
# where <subdir> matches the prompt key (sausage, tomato, tea) and <NNN> is the
# progress value (010, 020, ..., 130).
FEW_SHOT_DIR = Path("/app/ros/ttp_ws/data_ur/few_shots")


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates keyed by monitoring target.
#
# Each entry contains:
#   - description: human-readable label (for logging)
#   - instruction: the main prompt text sent to the VLM
#   - few_shot_subdir: subdirectory name under FEW_SHOT_DIR containing
#     progress_<NNN>.jpg reference images (or None for no few-shots)
#
# To modify prompts, edit the dictionaries below.
# ---------------------------------------------------------------------------

MONITORING_PROMPTS: Dict[str, Dict[str, Any]] = {
    "sausage": {
        "description": "소시지 굽기 진행도",
        "instruction": (
            "This image shows sausage(s) being pan-fried on a pan/stove. "
            "IMPORTANT setup note: an LED strip is placed DIRECTLY UNDER the sausage object itself, "
            "so the sausage glows from below and its apparent surface color is dominated by the LED color "
            "transmitted/diffused through the sausage body. Judge progress by the overall color the sausage emits. "
            "Estimate the cooking progress as an integer between 0 and 130 (in steps of 10), "
            "based mainly on the perceived surface color of the sausage. "
            "0 = raw, bright pink glow, pan not yet hot. "
            "50 = about half-cooked, glow fading from pink toward light brown. "
            "100 = perfectly done, even reddish-brown glow all over. "
            "110-130 = overcooked/burnt, dark brown to near-black charred tones. "
            "Return ONLY a JSON object with a single key 'progress' whose value is the integer."
        ),
        "few_shot_subdir": "sausage",
    },
    "tomato": {
        "description": "토마토 소스 졸이기 진행도",
        "instruction": (
            "This image shows tomatoes being simmered/reduced into a sauce in a pan or pot. "
            "The task is to boil down fresh tomatoes until they become a thick tomato sauce. "
            "Estimate the cooking progress as an integer between 0 and 130 (in steps of 10), "
            "based on the color, thickness, and water content of the sauce. "
            "0 = just placed: bright/light red fresh tomato chunks, very watery, pan/pot just heating up. "
            "50 = about half-reduced: deeper red, still somewhat liquid, tomatoes breaking down. "
            "100 = perfectly done: rich deep red, thick and glossy sauce, most water evaporated. "
            "110-130 = over-reduced/burnt: dark reddish-brown, dried out, scorched at the bottom. "
            "Return ONLY a JSON object with a single key 'progress' whose value is the integer."
        ),
        "few_shot_subdir": "tomato",
    },
    "tea": {
        "description": "차 우리기 진행도",
        "instruction": (
            "This image shows tea (green tea) being brewed in a teapot or cup. "
            "Estimate the brewing progress as an integer between 0 and 130 (in steps of 10), "
            "based on the color of the liquid. "
            "0 = not started: nearly clear/whitish water, tea leaves/bag just placed. "
            "50 = halfway: light green tint developing. "
            "100 = perfectly brewed: rich green color, ideal strength. "
            "110-130 = over-brewed: very dark green, overly strong/bitter-looking. "
            "Return ONLY a JSON object with a single key 'progress' whose value is the integer."
        ),
        "few_shot_subdir": "tea",
    },
    "default": {
        "description": "일반 요리 진행도",
        "instruction": (
            "This image shows a cooking/preparation process. "
            "Estimate the progress as an integer between 0 and 130 (in steps of 10). "
            "0 means not started. 50 means halfway. 100 means done. "
            "Values above 100 mean overcooked/over-processed. "
            "Return ONLY a JSON object with a single key 'progress' whose value is the integer."
        ),
        "few_shot_subdir": None,
    },
}


def _encode_frame_as_data_url(frame: np.ndarray, quality: int = 85) -> str:
    """Encode a BGR numpy frame to a JPEG base64 data URL."""
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
    success, buf = cv2.imencode(".jpg", frame, encode_params)
    if not success:
        raise RuntimeError("Failed to encode frame as JPEG.")
    b64 = base64.b64encode(buf.tobytes()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


# Cache of (subdir -> [(progress, data_url), ...]) to avoid re-reading files.
_FEW_SHOT_CACHE: Dict[str, list] = {}


def _load_image_few_shots(subdir: Optional[str]) -> list:
    """Load progress_<NNN>.jpg reference images from FEW_SHOT_DIR/<subdir>.

    Returns a list of (progress_int, data_url_str) sorted by progress.
    Results are cached per subdir.
    """
    if not subdir:
        return []
    if subdir in _FEW_SHOT_CACHE:
        return _FEW_SHOT_CACHE[subdir]

    folder = FEW_SHOT_DIR / subdir
    if not folder.is_dir():
        logger.warning("Few-shot dir not found: %s", folder)
        _FEW_SHOT_CACHE[subdir] = []
        return []

    shots = []
    for path in sorted(folder.glob("progress_*.jpg")):
        try:
            progress = int(path.stem.replace("progress_", ""))
        except ValueError:
            continue
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        shots.append((progress, f"data:image/jpeg;base64,{b64}"))
    logger.info("Loaded %d image few-shots from %s", len(shots), folder)
    _FEW_SHOT_CACHE[subdir] = shots
    return shots


# Maps object_id (from object_init_states.json "position" field) to a
# monitoring category.  Add new entries here when new monitored objects
# are defined.
OBJECT_ID_TO_CATEGORY: Dict[int, str] = {
    33: "stove",   # stove — actual food determined from instruction
    # teapot: id TBD, e.g.  44: "teapot",
}


def _resolve_prompt_key(
    object_id: Optional[int], instruction: Optional[str]
) -> str:
    """Determine the prompt key from the monitoring object_id and instruction.

    Rules:
      - teapot (object_id mapped to "teapot") → always "tea"
      - stove  (object_id 33) → parse instruction for "sausage" or "tomato"
      - fallback → "default"
    """
    category = OBJECT_ID_TO_CATEGORY.get(object_id) if object_id is not None else None

    if category == "teapot":
        return "tea"

    if category == "stove" and instruction is not None:
        inst_lower = instruction.lower()
        for keyword in ("sausage", "tomato"):
            if keyword in inst_lower:
                return keyword

    return "default"


def _select_prompt(
    instruction: Optional[str], object_id: Optional[int] = None
) -> Dict[str, Any]:
    """Select the appropriate prompt template from object_id and instruction."""
    key = _resolve_prompt_key(object_id, instruction)
    return MONITORING_PROMPTS.get(key, MONITORING_PROMPTS["default"])


def _build_messages(
    prompt_template: Dict[str, Any],
    image_data_url: str,
) -> list:
    """Build the OpenAI chat messages from a prompt template and image."""
    messages: list = []

    # Image few-shot examples: each is a (user-image, assistant-json) pair.
    few_shots = _load_image_few_shots(prompt_template.get("few_shot_subdir"))
    for progress, shot_data_url in few_shots:
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Example reference image."},
                    {
                        "type": "image_url",
                        "image_url": {"url": shot_data_url, "detail": "low"},
                    },
                ],
            }
        )
        messages.append(
            {"role": "assistant", "content": json.dumps({"progress": progress})}
        )

    # Actual query with the live camera frame + full instruction.
    messages.append(
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt_template["instruction"]},
                {
                    "type": "image_url",
                    "image_url": {"url": image_data_url, "detail": "low"},
                },
            ],
        }
    )
    return messages


def _parse_progress(raw_text: str) -> int:
    """Parse the VLM response text into an integer progress value.

    Handles both pure JSON and text-wrapped JSON.  Falls back to scanning
    for a bare integer if JSON parsing fails.
    """
    # Try JSON first
    try:
        data = json.loads(raw_text)
        value = int(data["progress"])
    except (json.JSONDecodeError, KeyError, TypeError):
        # Fallback: find any integer in the text
        import re

        match = re.search(r"\b(\d{1,3})\b", raw_text)
        if match:
            value = int(match.group(1))
        else:
            raise ValueError(f"Could not parse progress from VLM response: {raw_text}")

    # Clamp to valid range and round to nearest 10
    value = max(0, min(130, value))
    value = round(value / 10) * 10
    return value


class VLMProgressEstimator:
    """Captures a RealSense frame and queries a VLM for progress estimation.

    Args:
        camera: An already-initialised ``realsense_camera`` instance.
            If ``None``, image capture is skipped (useful for testing).
        model_name: OpenAI model to use for the VLM query.
        api_key: OpenAI API key. Defaults to ``OPENAI_API_KEY`` env var.
    """

    def __init__(
        self,
        camera: Any = None,
        *,
        model_name: str = "gpt-4.1",
        api_key: Optional[str] = None,
    ) -> None:
        self._camera = camera
        self._model_name = model_name
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._client: Any = None  # lazy init

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self._api_key)
        return self._client

    def capture_frame(self) -> Optional[np.ndarray]:
        """Capture a single color frame from the camera."""
        if self._camera is None:
            logger.warning("No camera available — skipping frame capture.")
            return None

        success, frame = self._camera.read()
        if not success or frame is None:
            logger.error("Failed to capture frame from camera.")
            return None
        return frame

    def estimate_progress(
        self,
        instruction: Optional[str] = None,
        object_id: Optional[int] = None,
        frame: Optional[np.ndarray] = None,
    ) -> Optional[int]:
        """Estimate cooking/preparation progress.

        Args:
            instruction: The full natural-language instruction given at
                program start (e.g. "Cook Sausage and Do Laundry").
                Used together with ``object_id`` to select the prompt.
            object_id: The object_id from action_parts[2].  Determines
                the monitoring category (e.g. 33 → stove → check
                instruction for sausage/tomato; teapot id → tea).
            frame: BGR image as a numpy array. If ``None``, a frame will
                be captured from the camera.

        Returns:
            An integer in [0, 130] (step 10), or ``None`` if estimation fails.
        """
        if frame is None:
            frame = self.capture_frame()
        if frame is None:
            logger.error("No frame available for VLM progress estimation.")
            return None

        prompt_template = _select_prompt(instruction, object_id)
        image_data_url = _encode_frame_as_data_url(frame)
        messages = _build_messages(prompt_template, image_data_url)

        logger.info(
            "Querying VLM for progress (object_id=%s, instruction=%s, model=%s)",
            object_id,
            instruction,
            self._model_name,
        )

        # Save input image for review
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        log_dir = VLM_LOG_DIR / timestamp
        log_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(log_dir / "input_frame.jpg"), frame)

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self._model_name,
                messages=messages,
                max_tokens=50,
                temperature=0.0,
            )
            raw_text = response.choices[0].message.content.strip()
            logger.info("VLM raw response: %s", raw_text)
            progress = _parse_progress(raw_text)
            logger.info("Parsed progress: %d", progress)

            # Save VLM input/output log for review
            log_data = {
                "timestamp": timestamp,
                "instruction": instruction,
                "object_id": object_id,
                "prompt_key": _resolve_prompt_key(object_id, instruction),
                "prompt_text": prompt_template["instruction"],
                "model": self._model_name,
                "vlm_raw_response": raw_text,
                "parsed_progress": progress,
            }
            with open(log_dir / "vlm_log.json", "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)

            return progress
        except Exception:
            logger.exception("VLM progress estimation failed.")
            # Still save partial log on failure
            log_data = {
                "timestamp": timestamp,
                "instruction": instruction,
                "object_id": object_id,
                "prompt_key": _resolve_prompt_key(object_id, instruction),
                "error": "VLM call failed — see ROS container logs",
            }
            try:
                with open(log_dir / "vlm_log.json", "w", encoding="utf-8") as f:
                    json.dump(log_data, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
            return None
