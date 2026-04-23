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
            "This image simulates sausage pan-frying. An LED strip is placed DIRECTLY UNDER "
            "the sausage, and the translucent silicone sausage body glows in a color that "
            "encodes doneness. The sausage body has a natural pink tint even with no LED, "
            "so at very dim anchors the body's native pink can partly show through. "
            "Judge ONLY the glowing sausage — ignore the green pan, trays, AR markers, "
            "background, wires, tape, and everything else in the frame. "
            "The glow sweeps from bright hot-pink → warm pink / coral → dim red-pink, with "
            "BRIGHTNESS monotonically decreasing from anchor 20 to 120 and hue slowly "
            "warming (adding red). NO brown, NO orange, NO yellow, NO pure black appears. "
            "IMPORTANT: anchors 20 / 40 / 60 look quite similar — all bright pink, "
            "differing only in a small amount of brightness and a subtle red-shift. "
            "Anchors 80 / 100 / 120 are clearly dimmer; 120 in particular barely glows. "
            "Use BRIGHTNESS as the primary cue and rely on the 14 reference images above — "
            "they are authoritative. "
            "Output: integer progress in {0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, "
            "110, 120, 130}. "
            "Key anchors (14 reference images above cover all values in 10-step): "
            "0 = LED COMPLETELY OFF — sausage shows only its natural unlit pink, NO glow. "
            "20 = brightest glow; sausage body uniformly lit in vivid pink. "
            "40 = still bright pink, very close to 20 (nearly indistinguishable). "
            "60 = bright pink, slight warm / red lean just starting to appear. "
            "80 = noticeably dimmer than 60; pink-coral tone, glow more localized. "
            "100 = clearly dim; dull coral / pink-red, glow significantly reduced. "
            "120 = barely glowing; very close to anchor 0 but a faint red tint remains. "
            "130 = essentially dead; nearly indistinguishable from 0 (extreme overcook). "
            "Intermediate values (10, 30, 50, 70, 90, 110) interpolate between neighbors — "
            "use the provided reference images for these. "
            "Calibration rules: "
            "(a) If the sausage shows NO glow at all (pure native pink body, no LED "
            "contribution), return 0. Do NOT return 120/130 unless a faint dim glow is "
            "still visible. "
            "(b) BRIGHTEST glow → 20. DIMMEST faint glow → 130. 0 is for NO glow at all. "
            "(c) If you cannot tell two adjacent values apart, pick LOWER. "
            "(d) Do NOT confuse anchor 130 (nearly off) with anchor 20 (very bright). If "
            "the sausage is clearly LIT and VIVID pink, it is 10-60, never 120/130. "
            "Return ONLY a JSON object: "
            "{\"observed_color\": \"<short phrase describing brightness + hue>\", "
            "\"closest_anchor\": <integer in {0, 10, 20, ..., 130}>, "
            "\"progress\": <same integer as closest_anchor>}."
        ),
        "few_shot_subdir": "sausage",
    },
    "tomato": {
        "description": "토마토 소스 졸이기 진행도",
        "instruction": (
            "This image simulates tomato-sauce reduction. An LED is placed DIRECTLY UNDER "
            "a blue pot (covered by a thick white paper diffuser with black grid marks), so "
            "you see a GLOWING SPOT on the diffuser whose color and brightness encode "
            "reduction progress. "
            "Judge ONLY the glowing spot on the white diffuser — ignore the blue pot, "
            "diffuser grid lines, background, red tomato shape, wires, and everything else. "
            "DO NOT infer from 'thickness', 'water content', or 'glossiness'; those cues "
            "are NOT present in this setup. "
            "The glow sweeps along a SINGLE pale-pink → red axis, with hue becoming more "
            "red-saturated and overall brightness decreasing as progress advances. "
            "There is NO brown, NO orange, NO black — only pink/red variants. "
            "Output: integer progress in {0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, "
            "110, 120, 130}. "
            "Key anchors (14 reference images above cover all values in 10-step): "
            "0 = LED COMPLETELY OFF — no glow on the diffuser at all, only the white paper "
            "and the unlit scene. "
            "20 = palest glow, mostly pink-white with the smallest red component; brightest. "
            "40 = similar pale pink to 20, only marginally dimmer. "
            "60 = clearly more saturated pink, less white-washed. "
            "80 = pink-coral, red component emerging; clearly less bright than 60. "
            "100 = clear red / coral-red, red now dominant, noticeably dimmer. "
            "120 = dim deep red, clearly darker and more contained than 100 (over-reduced). "
            "130 = very faint red glow, close to no glow at all (extreme over-reduction). "
            "Intermediate values (10, 30, 50, 70, 90, 110) interpolate between neighbors — "
            "use the provided reference images for these. "
            "Calibration rules: "
            "(a) If there is NO glowing spot on the diffuser at all, return 0. "
            "(b) BRIGHTNESS decreases from 20 → 130; HUE shifts from pale-pink to red. "
            "Use both cues with the references. "
            "(c) 20 and 40 look very similar — if you cannot tell them apart, return 20. "
            "Always pick LOWER when uncertain between adjacent values. "
            "(d) 120/130 are ONLY for glows clearly DIMMER and more contained than the 100 "
            "anchor. 130 is almost indistinguishable from 0 except for a faint red tint. "
            "Return ONLY a JSON object: "
            "{\"observed_color\": \"<short phrase describing brightness + hue>\", "
            "\"closest_anchor\": <integer in {0, 10, 20, ..., 130}>, "
            "\"progress\": <same integer as closest_anchor>}."
        ),
        "few_shot_subdir": "tomato",
    },
    "tea": {
        "description": "차 우리기 진행도",
        "instruction": (
            "This image simulates tea brewing. An LED is placed DIRECTLY UNDER the teacup "
            "(covered by a thick white diffuser/paper), so you see a GLOWING SPOT whose "
            "color AND brightness encode brewing strength. "
            "Judge ONLY the glowing spot — ignore cup, teabag, diffuser edges, background, "
            "wires, arduino boards, and everything else in the frame. "
            "IMPORTANT: in this setup the diffuser is highly reflective, so early anchors "
            "look almost entirely white (bright, near-saturated), and the cyan/teal color "
            "only becomes clearly visible as the LED dims in later anchors. "
            "Use BRIGHTNESS as the primary cue, with hue saturation as a secondary cue. "
            "Output: integer progress in {0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, "
            "110, 120, 130}. "
            "Key anchors (14 reference images above cover all values in 10-step): "
            "0 = LED COMPLETELY OFF — no glow on the diffuser, only the dark pre-brew "
            "state of the cup. "
            "20 = very bright, almost entirely white / white-cyan, barely any color visible. "
            "40 = still very bright white, with a faint cyan tint just starting to appear. "
            "60 = bright glow with a clear but pale cyan tint. "
            "80 = noticeably dimmer than 60; clear pale-cyan color across the whole glow. "
            "100 = distinctly dimmer; rich cyan / teal, color fully developed. "
            "120 = clearly dim; darker cyan / deep teal, glow is noticeably smaller / more "
            "contained (over-brewed). "
            "130 = very dim teal, nearly no glow (extreme over-brew). "
            "Intermediate values (10, 30, 50, 70, 90, 110) interpolate between neighbors — "
            "use the provided reference images for these. "
            "Calibration rules: "
            "(a) If there is NO glowing spot on the diffuser at all, return 0. "
            "(b) Brightness decreases monotonically from 20 → 130. If the glow still looks "
            "as bright / white-washed as the 20 anchor, return 20 — do NOT jump to 100+. "
            "(c) 120/130 are ONLY for glows clearly DIMMER and more contained than the 100 "
            "anchor. "
            "(d) When uncertain between two adjacent values, pick the LOWER one. "
            "Return ONLY a JSON object: "
            "{\"observed_color\": \"<short phrase describing brightness + hue>\", "
            "\"closest_anchor\": <integer in {0, 10, 20, ..., 130}>, "
            "\"progress\": <same integer as closest_anchor>}."
        ),
        "few_shot_subdir": "tea",
    },
    "default": {
        "description": "일반 요리 진행도",
        "instruction": (
            "This image shows a cooking/preparation process. "
            "Estimate the progress as an integer in "
            "{0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130}. "
            "0 = not started. 60 = halfway. 100 = perfectly done. 120+ = overcooked. "
            "When uncertain between two values, pick the LOWER one. "
            "Return ONLY a JSON object: "
            "{\"progress\": <integer in {0, 10, 20, ..., 130}>}."
        ),
        "few_shot_subdir": None,
    },
}

# The allowed discrete progress values the VLM may return.
# 0 = not started (LED off), 10 step until 130 (overcooked cap).
ALLOWED_PROGRESS_VALUES: tuple = (
    0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130,
)


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
        if progress not in ALLOWED_PROGRESS_VALUES:
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
    # The progress value is stated explicitly in the user turn so the VLM
    # has an image-label correspondence in the vision track, not only in the
    # assistant-JSON track.
    few_shots = _load_image_few_shots(prompt_template.get("few_shot_subdir"))
    for progress, shot_data_url in few_shots:
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Reference anchor image: this is what progress = {progress} "
                            f"looks like under this exact camera and lighting setup."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": shot_data_url, "detail": "high"},
                    },
                ],
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": json.dumps(
                    {"closest_anchor": progress, "progress": progress}
                ),
            }
        )

    # Actual query with the live camera frame + full instruction.
    messages.append(
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt_template["instruction"]},
                {
                    "type": "image_url",
                    "image_url": {"url": image_data_url, "detail": "high"},
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

    # Snap to the closest allowed discrete progress value.
    value = min(ALLOWED_PROGRESS_VALUES, key=lambda candidate: abs(candidate - value))
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
                max_tokens=200,
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
