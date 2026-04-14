from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

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


def _init_realsense_camera() -> Any:
    """Try to initialise the RealSense camera; return ``None`` on failure."""
    try:
        from object_detect_topic.opencv_realsense import realsense_camera

        cam = realsense_camera(
            height=480, width=640, fps=30, use_color=True, use_depth=False
        )
        if cam.isOpened():
            logger.info("RealSense camera initialised successfully.")
            return cam
        else:
            logger.warning("RealSense camera could not be opened.")
            return None
    except Exception:
        logger.exception("Failed to initialise RealSense camera.")
        return None


def _init_vlm_estimator(camera: Any) -> Any:
    """Create the VLM progress estimator (lazy OpenAI client)."""
    try:
        from .vlm_progress_estimator import VLMProgressEstimator

        estimator = VLMProgressEstimator(camera=camera)
        logger.info("VLM progress estimator created.")
        return estimator
    except Exception:
        logger.exception("Failed to create VLM progress estimator.")
        return None


@asynccontextmanager
async def lifespan(app: FastAPI) -> None:
    """Handles startup and shutdown events for the FastAPI application.

    Args:
        app: The FastAPI application instance.
    """
    print("Initializing ROS communication...")
    init_ros_communication()

    # Initialise RealSense camera and VLM estimator once at startup
    camera = _init_realsense_camera()
    app.state.realsense_cam = camera
    app.state.vlm_estimator = _init_vlm_estimator(camera)

    yield

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

    This endpoint receives already translated action parts from the client
    (ttp container) and forwards them to the ROS service without reading
    or translating any mapping/position files on the ROS side.

    For monitoring actions (instruction 20), after the ROS service call
    completes a RealSense frame is captured and sent to a VLM to
    estimate cooking progress.  The progress value (0-130, step 10) is
    included in the response.

    Args:
        parts_request: The request containing translated action parts.

    Returns:
        A dictionary with at least ``success``.  For monitoring actions
        it additionally contains ``progress`` (int or None).
    """
    try:
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
            # action_parts[2] is the object_id (e.g. 33 for stove)
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
        logger.warning(
            "VLM estimator not available — returning progress=None."
        )
        return None

    loop = asyncio.get_event_loop()
    progress = await loop.run_in_executor(
        None, estimator.estimate_progress, instruction, object_id, None
    )
    return progress


@app.post("/shutdown")
async def shutdown_server() -> Dict[str, str]:
    """A placeholder for a graceful shutdown endpoint.

    Note:
        A simple shutdown endpoint like this might not work with all server
        configurations (e.g., multiple uvicorn workers). A more robust
        solution might involve process signaling.
    """

    return {"message": "Shutdown command received. Note: This is a placeholder."}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
