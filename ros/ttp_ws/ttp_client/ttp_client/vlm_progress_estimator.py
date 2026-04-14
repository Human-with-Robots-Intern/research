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


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates keyed by monitoring target.
#
# Each entry contains:
#   - description: human-readable label (for logging)
#   - instruction: the main prompt text sent to the VLM
#   - few_shots: text-only few-shot examples (no images)
#
# To modify prompts, edit the dictionaries below.
# ---------------------------------------------------------------------------

MONITORING_PROMPTS: Dict[str, Dict[str, Any]] = {
    "sausage": {
        "description": "소시지 굽기 진행도",
        "instruction": (
            "This image shows sausage(s) being cooked on a pan/stove. "
            "Estimate the cooking progress as an integer between 0 and 130 (in steps of 10). "
            "0 means cooking has not started at all. "
            "50 means about half-cooked. "
            "100 means perfectly done. "
            "Values above 100 (110, 120, 130) mean overcooked/burnt. "
            "Return ONLY a JSON object with a single key 'progress' whose value is the integer."
        ),
        "few_shots": [
            {
                "role": "user",
                "text": "The sausage is pink and raw, the pan is just starting to heat up.",
            },
            {"role": "assistant", "text": '{"progress": 10}'},
            {
                "role": "user",
                "text": "The surface is starting to turn slightly brown.",
            },
            {"role": "assistant", "text": '{"progress": 40}'},
            {
                "role": "user",
                "text": "The sausage is evenly browned all over with nice grill marks.",
            },
            {"role": "assistant", "text": '{"progress": 100}'},
            {
                "role": "user",
                "text": "The sausage has many blackened/charred spots.",
            },
            {"role": "assistant", "text": '{"progress": 120}'},
        ],
    },
    "tomato": {
        "description": "토마토 요리 진행도",
        "instruction": (
            "This image shows tomato(es) being cooked on a pan/stove. "
            "Estimate the cooking progress as an integer between 0 and 130 (in steps of 10). "
            "0 means cooking has not started at all. "
            "50 means about half-cooked (softening, releasing juices). "
            "100 means perfectly done (fully softened, slightly caramelized). "
            "Values above 100 (110, 120, 130) mean overcooked/burnt. "
            "Return ONLY a JSON object with a single key 'progress' whose value is the integer."
        ),
        "few_shots": [
            {
                "role": "user",
                "text": "The tomato slices are fresh and firm on the pan, just placed.",
            },
            {"role": "assistant", "text": '{"progress": 10}'},
            {
                "role": "user",
                "text": "The tomatoes are starting to soften and release some juice.",
            },
            {"role": "assistant", "text": '{"progress": 40}'},
            {
                "role": "user",
                "text": "The tomatoes are fully softened and slightly caramelized.",
            },
            {"role": "assistant", "text": '{"progress": 100}'},
            {
                "role": "user",
                "text": "The tomatoes are dried out and heavily charred.",
            },
            {"role": "assistant", "text": '{"progress": 120}'},
        ],
    },
    "tea": {
        "description": "차 우리기 진행도",
        "instruction": (
            "This image shows tea being brewed in a teapot or cup. "
            "Estimate the brewing progress as an integer between 0 and 130 (in steps of 10). "
            "0 means brewing has not started (clear water). "
            "50 means halfway brewed (light color). "
            "100 means perfectly brewed (ideal color and strength). "
            "Values above 100 (110, 120, 130) mean over-brewed/too strong. "
            "Return ONLY a JSON object with a single key 'progress' whose value is the integer."
        ),
        "few_shots": [
            {
                "role": "user",
                "text": "The water is nearly clear with the tea bag just placed in.",
            },
            {"role": "assistant", "text": '{"progress": 10}'},
            {
                "role": "user",
                "text": "The water has a light golden/amber tint.",
            },
            {"role": "assistant", "text": '{"progress": 40}'},
            {
                "role": "user",
                "text": "The tea has a rich, deep color — looks perfectly brewed.",
            },
            {"role": "assistant", "text": '{"progress": 100}'},
            {
                "role": "user",
                "text": "The tea is very dark and opaque, over-steeped.",
            },
            {"role": "assistant", "text": '{"progress": 120}'},
        ],
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
        "few_shots": [],
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
    messages = []

    # Few-shot examples (text only)
    for shot in prompt_template.get("few_shots", []):
        messages.append({"role": shot["role"], "content": shot["text"]})

    # Actual query with image
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
        model_name: str = "gpt-4.1-mini",
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
        """Capture a single color frame from the RealSense camera."""
        if self._camera is None:
            logger.warning("No camera available — skipping frame capture.")
            return None

        success, frame = self._camera.read()
        if not success or frame is None:
            logger.error("Failed to capture frame from RealSense camera.")
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
