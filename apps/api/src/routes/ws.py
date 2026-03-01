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

DANGER_THRESHOLD = 0.5

ASSESSOR_PROMPT = """You are an AI safety system for an electric scooter rider. You receive a camera frame from the rider's phone mounted on the handlebars, plus computer vision detection data including tracked approach rates.

Your job: assess the real danger level. The CV system may flag things that look dangerous but aren't (a car in a parallel lane, a parked vehicle, a pedestrian far away). You provide the reasoning the CV system cannot.

Key data points:
- approach_rate > 0 means object is getting closer, > 0.15 means fast approach
- estimated_distance: "close" (large bbox), "medium", "far" (small bbox)
- danger_score: pre-computed score from CV rules (0.0-1.0)

Detection data for this frame:
{detections_json}

Danger score: {danger_score}

Respond with ONLY valid JSON (no markdown):
{{
  "urgency": <1-5 integer>,
  "threat_type": "fast_vehicle" | "nearby_vehicle" | "pedestrian_conflict" | "road_hazard" | "construction" | "none",
  "threat_summary": "<one sentence>",
  "is_real_threat": true | false,
  "rider_action": "<what the rider should do>"
}}"""


# --- Object tracking ---

def compute_iou(box_a: list, box_b: list) -> float:
    """Compute IoU between two [x1, y1, x2, y2] boxes."""
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0


def bbox_area(bbox: list) -> float:
    return (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])


def bbox_center_x(bbox: list, frame_width: int) -> float:
    """Return center x as fraction of frame width (0.0 = left, 1.0 = right)."""
    cx = (bbox[0] + bbox[2]) / 2
    return cx / frame_width


def estimate_distance(bbox: list, frame_area: float) -> str:
    """Rough distance estimate based on bbox size relative to frame."""
    ratio = bbox_area(bbox) / frame_area
    if ratio > 0.15:
        return "close"
    elif ratio > 0.03:
        return "medium"
    return "far"


def track_detections(prev_detections: list, curr_detections: list) -> list:
    """Match current detections to previous frame using IoU, compute approach rate."""
    if not prev_detections:
        for d in curr_detections:
            d["approach_rate"] = 0.0
        return curr_detections

    # Greedy IoU matching: for each current detection, find best match in prev
    used = set()
    for det in curr_detections:
        best_iou = 0.0
        best_idx = -1
        for i, prev in enumerate(prev_detections):
            if i in used or prev["label"] != det["label"]:
                continue
            iou = compute_iou(det["bbox"], prev["bbox"])
            if iou > best_iou:
                best_iou = iou
                best_idx = i

        if best_iou > 0.2 and best_idx >= 0:
            used.add(best_idx)
            prev_area = bbox_area(prev_detections[best_idx]["bbox"])
            curr_area = bbox_area(det["bbox"])
            if prev_area > 0:
                det["approach_rate"] = round((curr_area - prev_area) / prev_area, 3)
            else:
                det["approach_rate"] = 0.0
        else:
            det["approach_rate"] = 0.0

    return curr_detections


def compute_danger_score(detections: list, frame_width: int, rider_speed_mph: float = 0) -> float:
    """Pre-agent danger scoring from design doc section 4.3."""
    score = 0.0

    for d in detections:
        if d["category"] == "vehicle":
            # Fast approach
            if d.get("approach_rate", 0) > 0.15:
                score += 0.4
            # On collision course: centered + growing
            if d.get("approach_rate", 0) > 0 and d.get("estimated_distance") in ("close", "medium"):
                cx = bbox_center_x(d["bbox"], frame_width)
                if 0.25 < cx < 0.75:
                    score += 0.3

        if d["category"] == "hazard" and d.get("estimated_distance") in ("close", "medium"):
            score += 0.3

    # Multiple vehicles in close proximity
    close_vehicles = [d for d in detections if d["category"] == "vehicle" and d.get("estimated_distance") == "close"]
    if len(close_vehicles) >= 2:
        score += 0.2

    # High rider speed
    if rider_speed_mph > 15:
        score += 0.1

    return round(min(score, 1.0), 2)


async def assess_and_send(websocket: WebSocket, frame: int, image_b64: str, detections: list, danger_score: float):
    try:
        prompt = ASSESSOR_PROMPT.format(
            detections_json=json.dumps(detections, indent=2),
            danger_score=danger_score,
        )
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
            "danger_score": danger_score,
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
    prev_detections: list = []
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
            frame_width = 640
            frame_height = 480
            if img is not None:
                h, w = img.shape[:2]
                frame_width = w
                frame_height = h
                if max(h, w) > 640:
                    scale = 640 / max(h, w)
                    img = cv2.resize(img, (int(w * scale), int(h * scale)))
                    frame_width = int(w * scale)
                    frame_height = int(h * scale)

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

                # Track objects across frames and compute approach rates
                frame_area = frame_width * frame_height
                for d in detections:
                    d["estimated_distance"] = estimate_distance(d["bbox"], frame_area)
                detections = track_detections(prev_detections, detections)

                # Compute danger score
                danger_score = compute_danger_score(detections, frame_width)

                # Store for next frame's tracking
                prev_detections = detections
            else:
                t_infer = t_decode
                danger_score = 0.0

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
                "danger_score": danger_score,
                "latency_ms": latency_ms,
            })

            # Only send to Claude when danger score exceeds threshold
            if danger_score >= DANGER_THRESHOLD:
                det_summary = ", ".join(
                    f"{d['label']}({d['category']}:{d['confidence']} ar={d.get('approach_rate', 0)} {d.get('estimated_distance', '?')})"
                    for d in detections
                )
                logger.info(
                    "Frame %d: danger=%.2f [%s] lat=%s lng=%s latency=%s",
                    frame_counter, danger_score, det_summary, lat, lng, latency_ms,
                )
                task = asyncio.create_task(
                    assess_and_send(websocket, frame_counter, image_b64, detections, danger_score)
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
