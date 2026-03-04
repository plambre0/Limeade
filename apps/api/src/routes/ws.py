import asyncio
import base64
import json
import logging
import os
import time
from collections import deque                          # [NEW] for trend buffer
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import cv2
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ultralytics import YOLO

from src.db import SessionLocal
from src.models import Hazard

router = APIRouter(tags=["ws"])
logger = logging.getLogger("uvicorn.error")

FRAMES_DIR = Path("frames")
FRAMES_DIR.mkdir(exist_ok=True)

CV_DIR = Path(__file__).resolve().parent.parent / "cv" / "model"

# Custom pothole model
pothole_model = YOLO(str(CV_DIR / "runs" / "detect" / "train20" / "weights" / "best.pt"))

# COCO pretrained model for vehicles, pedestrians, infrastructure
coco_model = YOLO(str(CV_DIR / "yolov8n.pt"))

# COCO classes, mapped to categories
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
CONSECUTIVE_TRIGGER = 3      # frames above threshold before calling Haiku
COOLDOWN_SECONDS = 3.0       # minimum seconds between Haiku calls


# rules, and structured haptic/sound output fields.
HAIKU_SYSTEM_PROMPT = """You are a real-time safety reasoning engine for an electric scooter rider in Chicago.

You receive a camera frame from the rider's phone mounted on the handlebars,
PLUS structured detection data from a computer vision system (YOLOv8).
Use both the image and the detection data together.

You receive:
- The camera image (use this to visually confirm detections)
- current frame detection data with approach rates and optical flow features
- trend: last 3 frames showing danger_score trajectory (oldest first)

Use the trend to determine if the situation is ESCALATING or RESOLVING:
- danger_score increasing across trend = ESCALATING → higher urgency
- danger_score decreasing = RESOLVING → lower urgency or no alert

Key data points:
- approach_rate > 0 means object is getting closer, > 0.15 means fast approach
- estimated_distance: "close" (large bbox), "medium", "far" (small bbox)
- flow_magnitude: optical flow inside the detection bbox — high value = fast motion
- flow_dx: horizontal flow — positive = moving right, negative = moving left
- danger_score: pre-computed score from CV rules (0.0-1.0)

FALSE POSITIVE SIGNALS (do NOT alert):
- Vehicles with approach_rate near 0 (parallel traffic, parked cars)
- Pedestrians at far distance
- Detections where the image shows no real threat

REAL THREAT SIGNALS (DO alert):
- approach_rate > 0.15 AND object is centered in frame
- estimated_distance is "close" AND approach_rate positive
- Multiple hazards detected simultaneously
- Trend shows 3 consecutive rising danger_scores

URGENCY SCALE:
1-2 = minor hazard, gentle alert
3   = vehicle nearby, caution
4   = fast approach, act now
5   = imminent collision, emergency

Respond with ONLY valid JSON, no explanation, no markdown:
{
  "is_real_threat": true or false,
  "urgency": 1 to 5,
  "threat_type": "fast_vehicle" or "nearby_vehicle" or "pedestrian_conflict" or "road_hazard" or "construction" or "multi_threat" or "none",
  "threat_summary": "one sentence describing the threat",
  "rider_action": "what the rider should do",
  "alert_type": "haptic_only" or "sound_only" or "haptic_and_sound" or "none",
  "haptic_pattern": "single_pulse" or "double_pulse" or "triple_pulse" or "continuous" or "none",
  "sound_type": "chime" or "beep" or "spoken" or "none",
  "sound_content": "spoken text if sound_type is spoken, otherwise empty string",
  "reasoning": "one sentence explaining your decision referencing the detection data"
}"""


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

        if d["category"] == "pedestrian":
            if d.get("estimated_distance") == "close":
                score += 0.4
            elif d.get("estimated_distance") == "medium":
                score += 0.2

        if d["category"] == "hazard":
            score += 0.5

    # Multiple vehicles in close proximity
    close_vehicles = [d for d in detections if d["category"] == "vehicle" and d.get("estimated_distance") == "close"]
    if len(close_vehicles) >= 2:
        score += 0.2

    # High rider speed
    if rider_speed_mph > 15:
        score += 0.1

    return round(min(score, 1.0), 2)

# ------



# The DB write block is completely unchanged.
async def assess_and_send(
    websocket: WebSocket, frame: int, image_b64: str,
    detections: list, danger_score: float, lat: float, lng: float,
    trend: list,                                               # trend data
):
    try:
        # Build rich detection summary for the user message
        det_lines = []
        for d in detections:
            det_lines.append(
                f"  - {d['label']} ({d['category']}) | conf={d['confidence']} | "
                f"dist={d.get('estimated_distance', '?')} | "
                f"approach={d.get('approach_rate', 0):.3f} | "
                f"flow_mag={d.get('flow_magnitude', 0):.3f} | "
                f"flow_dx={d.get('flow_dx', 0):.3f}"
            )

        # Build trend summary (last 3 frames, oldest first)
        trend_lines = [
            f"  frame {t['frame_seq']}: danger={t['danger_score']} | "
            f"closest={t['closest_distance']} | "
            f"fastest_approach={t['fastest_approach']}"
            for t in trend
        ]

        # User message with detection data + trend
        user_text = (
            f"CURRENT FRAME (seq={frame}):\n"
            f"  danger_score: {danger_score}\n"
            f"\nDETECTIONS:\n"
            + ("\n".join(det_lines) if det_lines else "  none")
            + f"\n\nTREND (oldest → newest, last 3 frames):\n"
            + ("\n".join(trend_lines) if trend_lines else "  no trend yet")
        )

        # Now uses system prompt + image + rich user text
        # max_tokens raised to 512 to fit the larger JSON response
        response = await claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=HAIKU_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": user_text},
                ],
            }],
        )

        # Strip markdown fences if Claude wraps in ```json
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        assessment = json.loads(raw.strip())

        logger.info("Frame %d assessed: %s", frame, assessment)

        # Send assessment back to phone
        await websocket.send_json({
            "type": "assessment",
            "frame": frame,
            "detections": detections,
            "danger_score": danger_score,
            "assessment": assessment,
        })

        # ----------------------------------------------------------------
        # DB write — Only reads is_real_threat, urgency,
        # threat_type, threat_summary.
        # ----------------------------------------------------------------
        if assessment.get("is_real_threat") and lat and lng:
            urgency = assessment.get("urgency", 1)
            severity = min(max(urgency, 1), 5)
            async with SessionLocal() as session:
                hazard = Hazard(
                    latitude=lat,
                    longitude=lng,
                    hazard_type=assessment.get("threat_type", "unknown"),
                    severity=severity,
                    description=assessment.get("threat_summary", ""),
                    source="cv_detection",
                )
                session.add(hazard)
                await session.commit()
                logger.info("Frame %d: saved hazard id=%d type=%s", frame, hazard.id, hazard.hazard_type)

    except Exception as e:
        logger.warning("Claude assessment failed: %s", e)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global frame_counter
    await websocket.accept()
    logger.info("WebSocket client connected")

    background_tasks: set[asyncio.Task] = set()
    prev_detections: list = []

    # Connection-scoped state for optical flow, trigger, and cooldown.
    # These reset automatically when the client disconnects (function exits).
    prev_gray: np.ndarray | None = None          # previous grayscale frame for optical flow
    consecutive_danger: int = 0                   # frames above DANGER_THRESHOLD in a row
    last_haiku_time: float = 0.0                  # time.monotonic() of last Haiku call
    trend_buffer: deque = deque(maxlen=3)         # rolling last-3-frames summary for Haiku

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

                # Optical flow — Farneback dense flow, annotates each detection
                # with flow_magnitude, flow_dx, flow_dy inside its bounding box.
                # Inserted after tracking (so bboxes are finalized), before danger score.
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                if prev_gray is not None and prev_gray.shape == gray.shape:
                    flow = cv2.calcOpticalFlowFarneback(
                        prev_gray, gray, None,
                        pyr_scale=0.5, levels=3, winsize=15,
                        iterations=3, poly_n=5, poly_sigma=1.2, flags=0,
                    )
                    fh, fw = flow.shape[:2]
                    for d in detections:
                        x1, y1, x2, y2 = [int(v) for v in d["bbox"]]
                        # Clamp bbox coords to flow array bounds
                        x1c = max(0, min(x1, fw - 1))
                        y1c = max(0, min(y1, fh - 1))
                        x2c = max(x1c + 1, min(x2, fw))
                        y2c = max(y1c + 1, min(y2, fh))
                        roi = flow[y1c:y2c, x1c:x2c]
                        if roi.size > 0:
                            mag = np.sqrt(roi[..., 0] ** 2 + roi[..., 1] ** 2)
                            d["flow_magnitude"] = round(float(np.mean(mag)), 3)
                            d["flow_dx"] = round(float(np.mean(roi[..., 0])), 3)
                            d["flow_dy"] = round(float(np.mean(roi[..., 1])), 3)
                        else:
                            d["flow_magnitude"] = 0.0
                            d["flow_dx"] = 0.0
                            d["flow_dy"] = 0.0
                else:
                    # First frame or shape mismatch — no flow available yet
                    for d in detections:
                        d["flow_magnitude"] = 0.0
                        d["flow_dx"] = 0.0
                        d["flow_dy"] = 0.0
                prev_gray = gray
                # [END optical flow block]

                # Compute danger score
                danger_score = compute_danger_score(detections, frame_width)

                # Store for next frame's tracking
                prev_detections = detections

                # Append this frame's summary to the trend buffer
                vehicle_distances = [
                    d.get("estimated_distance", "far")
                    for d in detections
                    if d["category"] == "vehicle"
                ]
                dist_order = ["close", "medium", "far"]
                closest_dist = "none"
                for dist in dist_order:
                    if dist in vehicle_distances:
                        closest_dist = dist
                        break
                approach_rates = [d.get("approach_rate", 0.0) for d in detections]
                trend_buffer.append({
                    "frame_seq": frame_counter,
                    "danger_score": danger_score,
                    "closest_distance": closest_dist,
                    "fastest_approach": round(max(approach_rates) if approach_rates else 0.0, 3),
                })

            else:
                t_infer = t_decode
                danger_score = 0.0

            t_total = time.perf_counter()
            latency_ms = {
                "decode": round((t_decode - t_start) * 1000, 1),
                "inference": round((t_infer - t_decode) * 1000, 1),
                "total": round((t_total - t_start) * 1000, 1),
            }

            # Immediate detection ack — resolves phone's sendAndWait.
            await websocket.send_json({
                "type": "detection",
                "status": "ok",
                "frame": frame_counter,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "detections": detections,
                "danger_score": danger_score,
                "latency_ms": latency_ms,
            })

            # Save hazard and optionally assess with Claude
            if danger_score >= DANGER_THRESHOLD and lat and lng:
                det_summary = ", ".join(
                    f"{d['label']}({d['category']}:{d['confidence']} ar={d.get('approach_rate', 0)} {d.get('estimated_distance', '?')})"
                    for d in detections
                )
                logger.info(
                    "Frame %d: danger=%.2f [%s] lat=%s lng=%s latency=%s",
                    frame_counter, danger_score, det_summary, lat, lng, latency_ms,
                )

                # Determine hazard type from detections
                categories = [d["category"] for d in detections]
                if "hazard" in categories:
                    hazard_type = "road_hazard"
                elif "vehicle" in categories:
                    hazard_type = "vehicle"
                elif "pedestrian" in categories:
                    hazard_type = "pedestrian"
                else:
                    hazard_type = "unknown"

                # Map danger score to severity 1-5
                severity = min(max(int(danger_score * 5) + 1, 1), 5)
                description = det_summary

                # Save directly to DB (no Claude needed)
                try:
                    async with SessionLocal() as session:
                        hazard = Hazard(
                            latitude=lat,
                            longitude=lng,
                            hazard_type=hazard_type,
                            severity=severity,
                            description=description,
                            source="cv_detection",
                        )
                        session.add(hazard)
                        await session.commit()
                        logger.info("Frame %d: saved hazard id=%d type=%s sev=%d", frame_counter, hazard.id, hazard_type, severity)
                except Exception as e:
                    logger.warning("Failed to save hazard: %s", e)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception:
        await websocket.close(code=1011)
    finally:
        for task in background_tasks:
            task.cancel()