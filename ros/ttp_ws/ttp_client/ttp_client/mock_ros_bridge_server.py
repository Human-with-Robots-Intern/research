"""Mock ROS bridge server for local testing without a real robot.

Mimics the real ros_bridge_server.py API but just logs actions and returns success.
No ROS dependencies required.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel


class ActionPartsRequest(BaseModel):
    action_parts: List[Any]


app = FastAPI()


@app.post("/execute_translated_action")
async def execute_translated_action(parts_request: ActionPartsRequest) -> Dict[str, Any]:
    print(f"[MOCK] Received action: {parts_request.action_parts}")
    time.sleep(0.5)  # simulate execution delay
    return {"success": True}


@app.post("/shutdown")
async def shutdown_server() -> Dict[str, str]:
    return {"message": "Mock shutdown received."}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
