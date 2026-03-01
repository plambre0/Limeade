import base64
import json
import logging
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ultralytics import YOLO

router = APIRouter(tags=["ws"])
logger = logging.getLogger("uvicorn.error")

FRAMES_DIR = Path("frames")
FRAMES_DIR.mkdir(exist_ok=True)

MODEL_PATH = Path(__file__).resolve().parent.parent / "cv" / "model" / "runs" / "detect" / "train20" / "weights" / "best.pt"
model = YOLO(str(MODEL_PATH))

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

            # decode image for inference
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            detections = []
            if img is not None:
                results = model(img, verbose=False)
                for box in results[0].boxes:
                    detections.append({
                        "label": results[0].names[int(box.cls)],
                        "confidence": round(float(box.conf), 3),
                        "bbox": [round(float(c), 1) for c in box.xyxy[0]],
                    })

            if detections:
                logger.info(
                    "Frame %d: %d detections, lat=%s, lng=%s",
                    frame_counter, len(detections), lat, lng,
                )

            await websocket.send_json({
                "status": "ok",
                "frame": frame_counter,
                "detections": detections,
            })
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception:
        await websocket.close(code=1011)
