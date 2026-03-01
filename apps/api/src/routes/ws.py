import asyncio
import base64
import json
import logging
import os
import time
from pathlib import Path

import anthropic
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

claude = anthropic.AsyncAnthropic(api_key=os.environ.get("CLAUDE_API_KEY"))

frame_counter = 0

CLASSIFY_PROMPT = """You are analyzing a road hazard detected by a pothole detection model.
Look at the detected region and respond with ONLY a JSON object (no markdown):
{
  "severity": "low" | "medium" | "high",
  "hazard_type": "pothole" | "crack" | "uneven_surface" | "other",
  "description": "<one sentence description>"
}"""


async def classify_and_send(websocket: WebSocket, frame: int, image_b64: str, detections: list):
    try:
        response = await claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                    {"type": "text", "text": CLASSIFY_PROMPT},
                ],
            }],
        )
        classification = json.loads(response.content[0].text)
        logger.info("Frame %d classified: %s", frame, classification)
        await websocket.send_json({
            "type": "classification",
            "frame": frame,
            "detections": detections,
            "classification": classification,
        })
    except Exception as e:
        logger.warning("Claude classification failed: %s", e)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global frame_counter
    await websocket.accept()
    logger.info("WebSocket client connected")
    background_tasks: set[asyncio.Task] = set()
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

            # send YOLO results immediately
            await websocket.send_json({
                "type": "detection",
                "status": "ok",
                "frame": frame_counter,
                "detections": detections,
                "latency_ms": latency_ms,
            })

            # fire off Claude classification in background
            if detections:
                logger.info(
                    "Frame %d: %d detections, lat=%s, lng=%s, latency=%s",
                    frame_counter, len(detections), lat, lng, latency_ms,
                )
                task = asyncio.create_task(
                    classify_and_send(websocket, frame_counter, image_b64, detections)
                )
                background_tasks.add(task)
                task.add_done_callback(background_tasks.discard)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception:
        await websocket.close(code=1011)
    finally:
        for task in background_tasks:
            task.cancel()
