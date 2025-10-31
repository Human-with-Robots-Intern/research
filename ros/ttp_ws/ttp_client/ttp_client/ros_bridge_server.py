from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict, List

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .ros_communicate import (
    communicate,
    init_ros_communication,
    shutdown_ros_communication,
)



class ActionPartsRequest(BaseModel):
    """Represents a request carrying already translated action parts.

    Attributes:
        action_parts: The translated action payload to send to the robot.
    """

    action_parts: List[Any]


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


@app.post("/execute_translated_action")
async def execute_translated_action(parts_request: ActionPartsRequest) -> Dict[str, Any]:
    """Execute a pre-translated primitive action via ROS.

    This endpoint receives already translated action parts from the client
    (ttp container) and forwards them to the ROS service without reading
    or translating any mapping/position files on the ROS side.

    Args:
        parts_request: The request containing translated action parts.

    Returns:
        A dictionary with the success status of the action.
    """
    try:
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(None, communicate, parts_request.action_parts)
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
