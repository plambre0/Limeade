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

CV_DIR = Path(__file__).resolve().parent.parent / "cv" / "model"

# Custom pothole model
pothole_model = YOLO(str(CV_DIR / "runs" / "detect" / "train20" / "weights" / "best.pt"))

# COCO pretrained model for vehicles, pedestrians, infrastructure
coco_model = YOLO(str(CV_DIR / "yolov8n.pt"))

# COCO classes we care about, mapped to categories
COCO_CLASS_MAP = {
    "car": "vehicle",
    "truck": "vehicle",
    "bus": "vehicle",
    "motorcycle": "vehicle",
    "person": "pedestrian",
    "bicycle": "pedestrian",
    "traffic light": "infrastructure",
    "stop sign": "infrastructure",
}

claude = anthropic.AsyncAnthropic(api_key=os.environ.get("CLAUDE_API_KEY"))

frame_counter = 0

ASSESSOR_PROMPT = """You are an AI safety system for an electric scooter rider. You receive a camera frame from the rider's phone mounted on the handlebars, plus computer vision detection data.

Your job: assess the real danger level. The CV system may flag things that look dangerous but aren't (a car in a parallel lane, a parked vehicle, a pedestrian far away). You provide the reasoning the CV system cannot.

Detection data for this frame:
{detections_json}

Respond with ONLY valid JSON (no markdown):
{{
  "urgency": <1-5 integer>,
  "threat_type": "fast_vehicle" | "nearby_vehicle" | "pedestrian_conflict" | "road_hazard" | "construction" | "none",
  "threat_summary": "<one sentence>",
  "is_real_threat": true | false,
  "rider_action": "<what the rider should do>"
}}"""


async def assess_and_send(websocket: WebSocket, frame: int, image_b64: str, detections: list):
    try:
        prompt = ASSESSOR_PROMPT.format(detections_json=json.dumps(detections, indent=2))
        response = await claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        assessment = json.loads(response.content[0].text)
        logger.info("Frame %d assessed: %s", frame, assessment)
        await websocket.send_json({
            "type": "assessment",
            "frame": frame,
            "detections": detections,
            "assessment": assessment,
        })
    except Exception as e:
        logger.warning("Claude assessment failed: %s", e)


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

            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            t_decode = time.perf_counter()

            detections = []
            if img is not None:
                h, w = img.shape[:2]
                if max(h, w) > 640:
                    scale = 640 / max(h, w)
                    img = cv2.resize(img, (int(w * scale), int(h * scale)))

                # Run COCO model for vehicles/pedestrians/infrastructure
                coco_results = coco_model(img, imgsz=640, verbose=False)
                for box in coco_results[0].boxes:
                    label = coco_results[0].names[int(box.cls)]
                    if label in COCO_CLASS_MAP:
                        detections.append({
                            "label": label,
                            "category": COCO_CLASS_MAP[label],
                            "confidence": round(float(box.conf), 3),
                            "bbox": [round(float(c), 1) for c in box.xyxy[0]],
                        })

                # Run pothole model for road hazards
                pothole_results = pothole_model(img, imgsz=640, verbose=False)
                for box in pothole_results[0].boxes:
                    detections.append({
                        "label": pothole_results[0].names[int(box.cls)],
                        "category": "hazard",
                        "confidence": round(float(box.conf), 3),
                        "bbox": [round(float(c), 1) for c in box.xyxy[0]],
                    })

                t_infer = time.perf_counter()
            else:
                t_infer = t_decode

            t_total = time.perf_counter()
            latency_ms = {
                "decode": round((t_decode - t_start) * 1000, 1),
                "inference": round((t_infer - t_decode) * 1000, 1),
                "total": round((t_total - t_start) * 1000, 1),
            }

            await websocket.send_json({
                "type": "detection",
                "status": "ok",
                "frame": frame_counter,
                "detections": detections,
                "latency_ms": latency_ms,
            })

            # Only send to Claude when there are actionable detections
            has_threats = any(
                d["category"] in ("vehicle", "pedestrian", "hazard")
                for d in detections
            )
            if has_threats:
                det_summary = ", ".join(
                    f"{d['label']}({d['category']}:{d['confidence']})"
                    for d in detections
                )
                logger.info(
                    "Frame %d: [%s] lat=%s lng=%s latency=%s",
                    frame_counter, det_summary, lat, lng, latency_ms,
                )
                task = asyncio.create_task(
                    assess_and_send(websocket, frame_counter, image_b64, detections)
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
