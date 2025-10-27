from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .ros_communicate import (
    communicate,
    init_ros_communication,
    shutdown_ros_communication,
)
from .translate import InstructionTranslator


class ActionRequest(BaseModel):
    """Represents the request model for an action to be executed.

    Attributes:
        primitive_action: The primitive action string to be executed.
    """

    primitive_action: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> None:
    """Handles startup and shutdown events for the FastAPI application.

    Args:
        app: The FastAPI application instance.
    """
    print("Initializing ROS communication...")
    init_ros_communication()
    yield
    print("Shutting down ROS communication...")
    shutdown_ros_communication()


app = FastAPI(lifespan=lifespan)
translator = InstructionTranslator()


@app.post("/execute_action")
async def execute_action(action_request: ActionRequest) -> Dict[str, Any]:
    """Execute a primitive action via ROS.

    This endpoint receives a primitive action, translates it, sends it to the
    ROS service, and returns the result.

    Args:
        action_request: The request containing the primitive action.

    Returns:
        A dictionary with the success status of the action.
    """
    try:
        translated_action = translator.translate(action_request.primitive_action)
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(None, communicate, translated_action)

        if success:
            return {"success": True}
        else:
            raise HTTPException(
                status_code=500, detail="Action execution failed on ROS side."
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


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
