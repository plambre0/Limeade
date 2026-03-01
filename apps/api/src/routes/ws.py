import base64
import json
import logging
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["ws"])
logger = logging.getLogger("uvicorn.error")

FRAMES_DIR = Path("frames")
FRAMES_DIR.mkdir(exist_ok=True)

frame_counter = 0


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global frame_counter
    await websocket.accept()
    logger.info("WebSocket client connected")
    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)

            image_b64 = data["image"]
            lat = data.get("latitude")
            lng = data.get("longitude")

            image_bytes = base64.b64decode(image_b64)
            frame_counter += 1
            path = FRAMES_DIR / f"frame_{frame_counter:04d}.jpg"
            path.write_bytes(image_bytes)

            logger.info(
                "Frame %d: %d bytes, lat=%s, lng=%s -> %s",
                frame_counter,
                len(image_bytes),
                lat,
                lng,
                path,
            )

            await websocket.send_json(
                {"status": "ok", "frame": frame_counter, "bytes": len(image_bytes)}
            )
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception:
        await websocket.close(code=1011)
