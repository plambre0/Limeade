import base64
import json
import logging
import time
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
            t_start = time.perf_counter()

            # decode image for inference
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            t_decode = time.perf_counter()

            detections = []
            if img is not None:
                h, w = img.shape[:2]
                if max(h, w) > 640:
                    scale = 640 / max(h, w)
                    img = cv2.resize(img, (int(w * scale), int(h * scale)))
                results = model(img, imgsz=640, verbose=False)
                t_infer = time.perf_counter()
                for box in results[0].boxes:
                    detections.append({
                        "label": results[0].names[int(box.cls)],
                        "confidence": round(float(box.conf), 3),
                        "bbox": [round(float(c), 1) for c in box.xyxy[0]],
                    })
            else:
                t_infer = t_decode

            t_total = time.perf_counter()
            latency_ms = {
                "decode": round((t_decode - t_start) * 1000, 1),
                "inference": round((t_infer - t_decode) * 1000, 1),
                "total": round((t_total - t_start) * 1000, 1),
            }

            if detections:
                logger.info(
                    "Frame %d: %d detections, lat=%s, lng=%s, latency=%s",
                    frame_counter, len(detections), lat, lng, latency_ms,
                )

            await websocket.send_json({
                "status": "ok",
                "frame": frame_counter,
                "detections": detections,
                "latency_ms": latency_ms,
            })
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception:
        await websocket.close(code=1011)
