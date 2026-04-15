from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
import serial
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .ros_communicate import (
    communicate,
    init_ros_communication,
    shutdown_ros_communication,
)

logger = logging.getLogger(__name__)

# Instruction ID for MONITORING actions
_MONITORING_INSTRUCTION = 20

# ROS topic for the RealSense color image
COLOR_TOPIC = "/camera/color/image_raw"

# Arduino serial port for LED control
ARDUINO_PORT = "/dev/arduino"
ARDUINO_BAUD = 9600


class ActionPartsRequest(BaseModel):
    """Represents a request carrying already translated action parts.

    Attributes:
        action_parts: The translated action payload to send to the robot.
        instruction: The full natural-language instruction given at program
            start (e.g. "Cook Sausage and Do Laundry").  Passed through to
            the VLM progress estimator for monitoring actions so the correct
            prompt template can be selected.
    """

    action_parts: List[Any]
    instruction: Optional[str] = None


class RosCamera:
    """Subscribes to a ROS Image topic and always holds the latest frame.

    Exposes a ``read()`` method compatible with cv2.VideoCapture so that
    VLMProgressEstimator can use it as a drop-in replacement.
    """

    def __init__(self, topic: str = COLOR_TOPIC) -> None:
        self._frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._topic = topic
        self._sub = None

    def start(self) -> None:
        """Create ROS subscriber (must be called after rclpy.init)."""
        from .ros_communicate import _ros_client_node
        from sensor_msgs.msg import Image

        if _ros_client_node is None:
            print("[RosCamera] WARNING: ROS node not available.", flush=True)
            return

        self._sub = _ros_client_node.create_subscription(
            Image, self._topic, self._image_callback, 1
        )
        print(f"[RosCamera] Subscribed to {self._topic}", flush=True)

    def _image_callback(self, msg: Any) -> None:
        """Convert ROS Image to BGR numpy array and store."""
        try:
            h, w = msg.height, msg.width
            if msg.encoding == "rgb8":
                frame = np.frombuffer(msg.data, dtype=np.uint8).reshape(h, w, 3)
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            elif msg.encoding == "bgr8":
                frame = np.frombuffer(msg.data, dtype=np.uint8).reshape(h, w, 3)
            else:
                frame = np.frombuffer(msg.data, dtype=np.uint8).reshape(h, w, 3)
            with self._lock:
                self._frame = frame
        except Exception as e:
            logger.error("RosCamera callback error: %s", e)

    def read(self) -> tuple:
        """Return (success, frame) like cv2.VideoCapture.read()."""
        with self._lock:
            if self._frame is not None:
                return True, self._frame.copy()
        return False, None

    def release(self) -> None:
        pass


def _init_arduino(port: str = ARDUINO_PORT, baud: int = ARDUINO_BAUD) -> Optional[serial.Serial]:
    """Open serial connection to Arduino for LED control."""
    try:
        ser = serial.Serial(port, baud, timeout=1)
        print(f"[ros_bridge] Arduino connected on {port}", flush=True)
        return ser
    except Exception as e:
        print(f"[ros_bridge] WARNING: Arduino not available ({e})", flush=True)
        return None


def _send_arduino_task_mode(ser: Optional[serial.Serial], instruction: Optional[str]) -> None:
    """Send T1 (sausage) or T2 (tomato) to Arduino based on instruction."""
    if ser is None or instruction is None:
        return
    inst_lower = instruction.lower()
    if "tomato" in inst_lower:
        cmd = "T2\n"
    elif "sausage" in inst_lower:
        cmd = "T1\n"
    else:
        return
    ser.write(cmd.encode())
    print(f"[ros_bridge] Sent to Arduino: {cmd.strip()}", flush=True)


def _init_vlm_estimator(camera: Any) -> Any:
    """Create the VLM progress estimator (lazy OpenAI client)."""
    try:
        from .vlm_progress_estimator import VLMProgressEstimator

        estimator = VLMProgressEstimator(camera=camera)
        print("[ros_bridge] VLM progress estimator created.", flush=True)
        return estimator
    except Exception as e:
        print(f"[ros_bridge] ERROR: Failed to create VLM progress estimator: {e}", flush=True)
        return None


@asynccontextmanager
async def lifespan(app: FastAPI) -> None:
    """Handles startup and shutdown events for the FastAPI application."""
    print("Initializing ROS communication...")
    init_ros_communication()

    camera = RosCamera(COLOR_TOPIC)
    camera.start()
    app.state.camera = camera
    app.state.vlm_estimator = _init_vlm_estimator(camera)
    app.state.arduino = _init_arduino()
    app.state.arduino_task_set = False  # track whether we've sent T1/T2

    yield

    if app.state.arduino is not None:
        try:
            app.state.arduino.close()
        except Exception:
            pass
    if camera is not None:
        try:
            camera.release()
        except Exception:
            pass
    print("Shutting down ROS communication...")
    shutdown_ros_communication()


app = FastAPI(lifespan=lifespan)


@app.post("/execute_translated_action")
async def execute_translated_action(parts_request: ActionPartsRequest) -> Dict[str, Any]:
    """Execute a pre-translated primitive action via ROS.

    For monitoring actions (instruction 20), after the ROS service call
    completes a camera frame is captured and sent to a VLM to estimate
    cooking progress.  The progress value (0-130, step 10) is included
    in the response.
    """
    try:
        # Set Arduino LED task mode on first request with instruction
        if not app.state.arduino_task_set and parts_request.instruction:
            _send_arduino_task_mode(app.state.arduino, parts_request.instruction)
            app.state.arduino_task_set = True

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, communicate, parts_request.action_parts
        )

        if not result.get("success", False):
            raise HTTPException(
                status_code=500, detail="Action execution failed on ROS side."
            )

        # For monitoring actions, capture image and query VLM
        instruction = None
        try:
            instruction = int(parts_request.action_parts[1])
        except (IndexError, ValueError, TypeError):
            pass

        if instruction == _MONITORING_INSTRUCTION:
            object_id = None
            try:
                object_id = int(parts_request.action_parts[2])
            except (IndexError, ValueError, TypeError):
                pass

            progress = await _estimate_monitoring_progress(
                parts_request.instruction, object_id
            )
            result["progress"] = progress

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


async def _estimate_monitoring_progress(
    instruction: Optional[str],
    object_id: Optional[int] = None,
) -> Optional[int]:
    """Capture a frame and query the VLM for cooking progress."""
    estimator = app.state.vlm_estimator
    if estimator is None:
        logger.warning("VLM estimator not available — returning progress=None.")
        return None

    loop = asyncio.get_event_loop()
    progress = await loop.run_in_executor(
        None, estimator.estimate_progress, instruction, object_id, None
    )
    return progress


@app.post("/shutdown")
async def shutdown_server() -> Dict[str, str]:
    return {"message": "Shutdown command received. Note: This is a placeholder."}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
