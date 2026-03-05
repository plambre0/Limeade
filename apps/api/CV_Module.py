"""
ScootSafe Module B — Computer Vision Pipeline
===============================================
Real-time scooter rider safety: detects vehicles & road hazards,
tracks them across frames, computes motion + optical flow features,
and outputs a rich feature dict for the Claude Haiku reasoning agent.

Real-time CV pipeline with danger scoring and trigger logic.
Computes features, scores danger (0.0–1.0), and fires a callback
to Module E when 3 consecutive frames exceed the danger threshold.

Libraries: ultralytics (YOLOv8), opencv-python-headless, numpy
"""

import time
import uuid
from collections import deque
from datetime import datetime, timezone

import cv2
import numpy as np
from ultralytics import YOLO

# ---------------------------------------------------------------------------
# Allowed COCO labels for the vehicle/general model
# ---------------------------------------------------------------------------
VEHICLE_LABELS = frozenset([
    "bicycle", "car", "motorcycle",
    "bus", "truck", "traffic light", "stop sign",
])

# Confidence floor
VEHICLE_CONF = 0.25   # low — catch distant vehicles early

# Tracker constants
IOU_MATCH_THRESHOLD = 0.2   # low for slow-moving distant objects at 2-5 FPS
MAX_TRACK_HISTORY   = 10    # frames of history kept per track
MAX_MISSES          = 5     # consecutive misses before pruning a track

# Danger scoring constants
DANGER_THRESHOLD        = 0.5   # minimum score to be considered dangerous
CONSECUTIVE_TRIGGER     = 3     # consecutive high-score frames before firing
EVENT_BUFFER_SIZE       = 20    # rolling buffer of recent DetectionEvents
TREND_WINDOW            = 3     # number of recent frames sent as trend to Module E


# ═══════════════════════════════════════════════════════════════════════════
# Utility
# ═══════════════════════════════════════════════════════════════════════════

def compute_iou(bbox_a: tuple, bbox_b: tuple) -> float:
    """Standard Intersection-over-Union for two (x1, y1, x2, y2) boxes."""
    ix1 = max(bbox_a[0], bbox_b[0])
    iy1 = max(bbox_a[1], bbox_b[1])
    ix2 = min(bbox_a[2], bbox_b[2])
    iy2 = min(bbox_a[3], bbox_b[3])

    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)

    area_a = (bbox_a[2] - bbox_a[0]) * (bbox_a[3] - bbox_a[1])
    area_b = (bbox_b[2] - bbox_b[0]) * (bbox_b[3] - bbox_b[1])
    union = area_a + area_b - inter

    return inter / union if union > 0 else 0.0


def compute_danger_score(event: dict) -> float:
    """
    Compute a danger score between 0.0 and 1.0 from a DetectionEvent.
    """
    scene_summary = event.get("scene_summary", {})

    # Step 1 — distance score
    dist_map = {
        "very_close": 1.0,
        "close":      0.75,
        "medium":     0.4,
        "far":        0.15,
        "very_far":   0.0,
        "none":       0.0,
    }
    closest = scene_summary.get("closest_vehicle_distance", "none")
    distance_score = dist_map.get(closest, 0.0)

    # Step 2 — approach score
    fastest_approach_rate = scene_summary.get("fastest_approach_rate", 0.0)
    approach_score = min(max(fastest_approach_rate / 0.3, 0.0), 1.0)

    # Step 3 — hazard score
    total_hazards = scene_summary.get("total_hazards", 0)
    hazard_score = min(total_hazards * 0.3, 1.0)

    # Step 4 — weighted combination
    danger_score = (
        distance_score  * 0.45 +
        approach_score  * 0.40 +
        hazard_score    * 0.15
    )

    # Step 5 — return rounded
    return round(danger_score, 4)


# ═══════════════════════════════════════════════════════════════════════════
# Class 1 — ObjectDetector
# ═══════════════════════════════════════════════════════════════════════════

class ObjectDetector:
    """
    Single-model YOLO detector.
      Model A  — YOLOv8s (COCO) for vehicles, pedestrians, signs.
    """

    def __init__(self):
        # Model A: vehicles & general (YOLOv8 small, 11.2M params)
        self.vehicle_model = YOLO("yolov8s.pt")

    # ------------------------------------------------------------------
    def detect(self, frame: np.ndarray) -> list[dict]:
        """
        Run vehicle model on *frame* (BGR, 720p).
        Returns list of detection dicts (label, confidence, bbox, source).
        """
        detections: list[dict] = []

        # --- Model A: vehicles / general ---
        results_a = self.vehicle_model(frame, conf=VEHICLE_CONF, verbose=False)
        for box in results_a[0].boxes:
            label = self.vehicle_model.names[int(box.cls)]
            if label not in VEHICLE_LABELS:
                continue
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            detections.append({
                "label": label,
                "confidence": float(box.conf),
                "bbox": (int(x1), int(y1), int(x2), int(y2)),
                "source": "vehicle_model",
            })

        return detections


# ═══════════════════════════════════════════════════════════════════════════
# Class 2 — BboxTracker
# ═══════════════════════════════════════════════════════════════════════════

class BboxTracker:
    """
    IoU-based multi-object tracker.
    Assigns persistent track IDs, maintains per-track history,
    accumulates confidence, and prunes stale tracks.
    """

    def __init__(self):
        self.tracks: dict[int, list[dict]] = {}      # track_id → recent detections
        self.next_id: int = 0
        self.prev_detections: list[dict] = []
        self.miss_counts: dict[int, int] = {}         # track_id → consecutive misses

    # ------------------------------------------------------------------
    def _new_id(self) -> int:
        tid = self.next_id
        self.next_id += 1
        return tid

    # ------------------------------------------------------------------
    def update(self, detections: list[dict]) -> list[dict]:
        """
        Match *detections* to previous frame via IoU, assign track IDs,
        update history, prune dead tracks.  Returns detections augmented
        with track_id, track_age, accumulated_confidence.
        """

        # ---- First frame: assign fresh IDs to everything ----
        if not self.prev_detections:
            for det in detections:
                tid = self._new_id()
                det["track_id"] = tid
                det["track_age"] = 1
                det["accumulated_confidence"] = det["confidence"]
                self.tracks[tid] = [det]
                self.miss_counts[tid] = 0
            self.prev_detections = detections
            return detections

        # ---- Build IoU score list ----
        pairs: list[tuple[float, int, int]] = []
        for ci, cur in enumerate(detections):
            for pi, prev in enumerate(self.prev_detections):
                iou = compute_iou(cur["bbox"], prev["bbox"])
                if iou > 0:
                    pairs.append((iou, ci, pi))
        pairs.sort(key=lambda x: x[0], reverse=True)

        # ---- Greedy matching ----
        matched_cur: set[int] = set()
        matched_prev: set[int] = set()
        cur_to_tid: dict[int, int] = {}

        for iou_val, ci, pi in pairs:
            if ci in matched_cur or pi in matched_prev:
                continue
            if iou_val < IOU_MATCH_THRESHOLD:
                break  # sorted descending — nothing useful below this
            tid = self.prev_detections[pi]["track_id"]
            cur_to_tid[ci] = tid
            matched_cur.add(ci)
            matched_prev.add(pi)

        # ---- Assign IDs and update history ----
        active_tids: set[int] = set()

        for ci, det in enumerate(detections):
            if ci in cur_to_tid:
                tid = cur_to_tid[ci]
            else:
                tid = self._new_id()
                self.tracks[tid] = []
                self.miss_counts[tid] = 0

            det["track_id"] = tid
            active_tids.add(tid)

            # Append to history (cap at MAX_TRACK_HISTORY)
            self.tracks[tid].append(det)
            if len(self.tracks[tid]) > MAX_TRACK_HISTORY:
                self.tracks[tid] = self.tracks[tid][-MAX_TRACK_HISTORY:]

            det["track_age"] = len(self.tracks[tid])
            det["accumulated_confidence"] = max(
                d["confidence"] for d in self.tracks[tid]
            )

            # Reset miss counter for active tracks
            self.miss_counts[tid] = 0

        # ---- Increment misses for unmatched previous tracks ----
        prev_tids = {d["track_id"] for d in self.prev_detections}
        for tid in prev_tids:
            if tid not in active_tids:
                self.miss_counts[tid] = self.miss_counts.get(tid, 0) + 1

        # ---- Prune dead tracks ----
        dead = [tid for tid, m in self.miss_counts.items() if m >= MAX_MISSES]
        for tid in dead:
            self.tracks.pop(tid, None)
            self.miss_counts.pop(tid, None)

        self.prev_detections = detections
        return detections


# ═══════════════════════════════════════════════════════════════════════════
# Class 3 — MotionAnalyzer
# ═══════════════════════════════════════════════════════════════════════════

class MotionAnalyzer:
    """
    Computes per-track motion features from:
      A) Bounding-box growth rate (geometric)
      B) Dense optical flow cropped to each bbox region
    """

    # ------------------------------------------------------------------
    # A — Bbox growth helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _bbox_area(bbox: tuple) -> int:
        return (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])

    @staticmethod
    def _bbox_center(bbox: tuple) -> tuple[float, float]:
        return (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0

    @staticmethod
    def _direction_label(cx: float, cy: float, w: int, h: int) -> str:
        if cy < h * 0.4:
            vert = "upper"
        elif cy < h * 0.7:
            vert = "middle"
        else:
            vert = "lower"

        if cx < w * 0.33:
            horiz = "left"
        elif cx < w * 0.67:
            horiz = "center"
        else:
            horiz = "right"

        return f"{vert}-{horiz}"

    @staticmethod
    def _distance_bucket(area_ratio: float) -> str:
        if area_ratio > 0.20:
            return "very_close"
        if area_ratio > 0.08:
            return "close"
        if area_ratio > 0.02:
            return "medium"
        if area_ratio > 0.005:
            return "far"
        return "very_far"

    # ------------------------------------------------------------------
    # B — Optical flow helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _flow_features(flow: np.ndarray | None, bbox: tuple) -> dict:
        """Extract flow stats inside a bbox region."""
        defaults = {
            "flow_magnitude": 0.0,
            "flow_dx": 0.0,
            "flow_dy": 0.0,
            "flow_expansion": 0.0,
        }
        if flow is None:
            return defaults

        x1, y1, x2, y2 = bbox
        # Clamp to flow array bounds
        fh, fw = flow.shape[:2]
        x1c = max(0, min(x1, fw - 1))
        y1c = max(0, min(y1, fh - 1))
        x2c = max(x1c + 1, min(x2, fw))
        y2c = max(y1c + 1, min(y2, fh))

        region = flow[y1c:y2c, x1c:x2c]
        if region.size == 0:
            return defaults

        dx = region[:, :, 0]
        dy = region[:, :, 1]
        mag = np.sqrt(dx ** 2 + dy ** 2)

        mean_mag = float(np.mean(mag))
        mean_dx = float(np.mean(dx))
        mean_dy = float(np.mean(dy))

        # Expansion score: do flow vectors point outward from bbox center?
        rh, rw = region.shape[:2]
        if rh < 2 or rw < 2:
            return {
                "flow_magnitude": mean_mag,
                "flow_dx": mean_dx,
                "flow_dy": mean_dy,
                "flow_expansion": 0.0,
            }

        # Grid of pixel positions relative to region center
        ys, xs = np.mgrid[0:rh, 0:rw]
        cx_r, cy_r = rw / 2.0, rh / 2.0
        pos_x = (xs - cx_r).astype(np.float32)
        pos_y = (ys - cy_r).astype(np.float32)
        pos_mag = np.sqrt(pos_x ** 2 + pos_y ** 2) + 1e-6

        # Dot product of (position vector, flow vector) normalised by position magnitude
        dot = (pos_x * dx + pos_y * dy) / pos_mag
        flow_mag_safe = mag + 1e-6
        expansion = dot / flow_mag_safe          # normalise by flow magnitude too
        expansion_score = float(np.clip(np.mean(expansion), -1.0, 1.0))

        return {
            "flow_magnitude": mean_mag,
            "flow_dx": mean_dx,
            "flow_dy": mean_dy,
            "flow_expansion": expansion_score,
        }

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def analyze(
        self,
        tracks: dict[int, list[dict]],
        flow: np.ndarray | None,
        frame_width: int,
        frame_height: int,
    ) -> dict[int, dict]:
        """
        Compute per-track motion features (bbox growth + optical flow).
        Returns {track_id: {feature_dict}}.
        """
        frame_area = frame_width * frame_height
        results: dict[int, dict] = {}

        for tid, history in tracks.items():
            if not history:
                continue

            latest = history[-1]
            bbox = latest["bbox"]
            area_now = self._bbox_area(bbox)
            cx, cy = self._bbox_center(bbox)
            area_ratio = area_now / max(frame_area, 1)

            # --- Approach rate ---
            approach_rate = 0.0
            acceleration = None
            lateral_drift = 0.0

            if len(history) >= 2:
                prev_bbox = history[-2]["bbox"]
                area_prev = self._bbox_area(prev_bbox)
                approach_rate = (area_now - area_prev) / max(area_prev, 1)

                cx_prev, _ = self._bbox_center(prev_bbox)
                lateral_drift = cx - cx_prev

            if len(history) >= 3:
                prev2_bbox = history[-3]["bbox"]
                prev1_bbox = history[-2]["bbox"]
                area_p2 = self._bbox_area(prev2_bbox)
                area_p1 = self._bbox_area(prev1_bbox)
                prev_approach = (area_p1 - area_p2) / max(area_p2, 1)
                acceleration = approach_rate - prev_approach

            # --- Flow features ---
            ff = self._flow_features(flow, bbox)

            results[tid] = {
                "approach_rate": round(approach_rate, 5),
                "acceleration": (
                    round(acceleration, 5)
                    if acceleration is not None
                    else None
                ),
                "direction": self._direction_label(cx, cy, frame_width, frame_height),
                "lateral_drift": round(lateral_drift, 2),
                "estimated_distance": self._distance_bucket(area_ratio),
                "bbox_area_ratio": round(area_ratio, 6),
                "flow_magnitude": round(ff["flow_magnitude"], 3),
                "flow_dx": round(ff["flow_dx"], 3),
                "flow_dy": round(ff["flow_dy"], 3),
                "flow_expansion": round(ff["flow_expansion"], 4),
                "track_age": len(history),
                "accumulated_confidence": round(
                    max(d["confidence"] for d in history), 3
                ),
            }

        return results


# ═══════════════════════════════════════════════════════════════════════════
# Class 4 — CVPipeline (orchestrator)
# ═══════════════════════════════════════════════════════════════════════════

class CVPipeline:
    """
    Top-level pipeline called by Module E (Backend).
    process_frame() → DetectionEvent dict  (consumed by Haiku agent)
    draw_overlays()  → annotated frame     (for monitoring dashboard)
    """

    def __init__(self):
        self.detector = ObjectDetector()
        self.tracker = BboxTracker()
        self.motion = MotionAnalyzer()
        self.prev_gray: np.ndarray | None = None
        self.frame_seq: int = 0
        self.frame_width: int = 1280
        self.frame_height: int = 720

        # Rolling buffer of recent DetectionEvents (for trend + trigger logic)
        self.event_buffer: deque = deque(maxlen=EVENT_BUFFER_SIZE)

        # Consecutive high-score frame counter
        self.consecutive_high: int = 0

        # Callback to Module E — set externally after instantiation
        # Signature: callback(payload: dict) -> None
        # Will be called by Module E asynchronously.
        # If None, trigger fires but nothing is called.
        self.on_trigger_callback = None  # type: ignore

    # ------------------------------------------------------------------
    def process_frame(
        self, frame: np.ndarray, metadata: dict | None = None
    ) -> dict:
        """
        Full pipeline: detect → track → optical flow → motion analysis.
        Returns a DetectionEvent dict.
        """
        rider_speed_mph = 0.0
        if metadata is not None:
            rider_speed_mph = metadata.get("gps", {}).get("speed_mph", 0.0)
        h, w = frame.shape[:2]
        self.frame_width = w
        self.frame_height = h

        # Grayscale for optical flow
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Optical flow (skip first frame)
        flow = None
        if self.prev_gray is not None:
            flow = cv2.calcOpticalFlowFarneback(
                self.prev_gray, gray,
                None,             # no initial flow estimate
                pyr_scale=0.5,
                levels=3,
                winsize=15,
                iterations=3,
                poly_n=5,
                poly_sigma=1.2,
                flags=0,
            )

        # Detect
        raw_detections = self.detector.detect(frame)

        # Track
        tracked = self.tracker.update(raw_detections)

        # Motion analysis
        motion_data = self.motion.analyze(
            self.tracker.tracks, flow, self.frame_width, self.frame_height
        )

        # Merge motion features into each detection
        for det in tracked:
            tid = det["track_id"]
            if tid in motion_data:
                det.update(motion_data[tid])
            else:
                # Fallback defaults (should not normally happen)
                det.update({
                    "approach_rate": 0.0,
                    "acceleration": None,
                    "direction": "middle-center",
                    "lateral_drift": 0.0,
                    "estimated_distance": "very_far",
                    "bbox_area_ratio": 0.0,
                    "flow_magnitude": 0.0,
                    "flow_dx": 0.0,
                    "flow_dy": 0.0,
                    "flow_expansion": 0.0,
                })

        # Store for next frame
        self.prev_gray = gray
        self.frame_seq += 1

        # ---- Build DetectionEvent ----
        vehicles = []
        for det in tracked:
            # Convert bbox tuple to list for JSON serialization
            entry = dict(det)
            entry["bbox"] = list(entry["bbox"])
            vehicles.append(entry)
        hazards = []  # potholes handled separately by teammates' pipeline

        # Scene summary
        vehicle_distances = [
            v["estimated_distance"]
            for v in vehicles
            if v["label"] in ("car", "motorcycle", "bus", "truck", "bicycle")
        ]
        dist_order = ["very_close", "close", "medium", "far", "very_far"]
        closest = "none"
        for d in dist_order:
            if d in vehicle_distances:
                closest = d
                break

        approach_rates = [v.get("approach_rate", 0.0) for v in vehicles]
        flow_mags = [
            v.get("flow_magnitude", 0.0) for v in vehicles + hazards
        ]

        event = {
            "event_id": f"evt-{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "frame_seq": self.frame_seq,
            "rider_speed_mph": rider_speed_mph,
            "detections": vehicles,
            "hazards": hazards,
            "scene_summary": {
                "total_vehicles": sum(
                    1
                    for v in vehicles
                    if v["label"]
                    in ("car", "motorcycle", "bus", "truck", "bicycle")
                ),
                "total_pedestrians": sum(
                    1 for v in vehicles if v["label"] == "person"
                ),
                "total_hazards": len(hazards),
                "closest_vehicle_distance": closest,
                "fastest_approach_rate": round(
                    max(approach_rates) if approach_rates else 0.0, 5
                ),
                "max_flow_magnitude": round(
                    max(flow_mags) if flow_mags else 0.0, 3
                ),
                "frame_width": self.frame_width,
                "frame_height": self.frame_height,
            },
        }
        event["danger_score"] = compute_danger_score(event)

        # --- Rolling buffer ---
        self.event_buffer.append(event)

        # --- Consecutive high-score trigger ---
        if event["danger_score"] >= DANGER_THRESHOLD:
            self.consecutive_high += 1
        else:
            self.consecutive_high = 0

        if self.consecutive_high >= CONSECUTIVE_TRIGGER:
            self.consecutive_high = 0  # reset so it does not re-fire every frame
            self._fire_trigger()

        return event

    # ------------------------------------------------------------------
    def _fire_trigger(self) -> None:
        """
        Package the Haiku payload and invoke the Module E callback.

        Payload structure sent to Module E:
        {
            "current_event": <most recent full DetectionEvent dict>,
            "trend": [
                {
                    "frame_seq": int,
                    "danger_score": float,
                    "closest_vehicle_distance": str,
                    "fastest_approach_rate": float
                },
                ... up to TREND_WINDOW entries, oldest first
            ]
        }

        The trend is the last TREND_WINDOW events from self.event_buffer,
        oldest first. Each trend entry contains only those 4 fields.
        Do not include the full event in the trend entries.

        If self.on_trigger_callback is None, return silently.
        If the callback raises an exception, print it and continue.
        Do not let a callback failure crash the CV pipeline.
        """
        if not self.event_buffer:
            return

        current_event = self.event_buffer[-1]

        recent = list(self.event_buffer)[-TREND_WINDOW:]
        trend = [
            {
                "frame_seq": e["frame_seq"],
                "danger_score": e["danger_score"],
                "closest_vehicle_distance": (
                    e["scene_summary"]["closest_vehicle_distance"]
                ),
                "fastest_approach_rate": (
                    e["scene_summary"]["fastest_approach_rate"]
                ),
            }
            for e in recent
        ]

        payload = {
            "current_event": current_event,
            "trend": trend,
        }

        if self.on_trigger_callback is not None:
            try:
                self.on_trigger_callback(payload)
            except Exception as exc:
                print(f"[CVPipeline] on_trigger_callback raised: {exc}")

    # ------------------------------------------------------------------
    def draw_overlays(self, frame: np.ndarray, event: dict) -> np.ndarray:
        """
        Annotate *frame* with bounding boxes, labels, motion info.
        Returns a new image (does not mutate original).
        """
        out = frame.copy()
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.5
        thickness = 1

        # Colour map by estimated distance
        dist_colors = {
            "very_far": (0, 200, 0),
            "far": (0, 200, 0),
            "medium": (0, 255, 255),
            "close": (0, 165, 255),
            "very_close": (0, 0, 255),
        }

        all_dets = event.get("detections", [])

        for det in all_dets:
            x1, y1, x2, y2 = det["bbox"]
            dist = det.get("estimated_distance", "very_far")

            color = dist_colors.get(dist, (0, 200, 0))

            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)

            # Label line
            lbl = det.get("label", "?")
            conf = det.get("confidence", 0)
            label_text = f"{lbl} {conf:.0%} d={dist}"
            cv2.putText(out, label_text, (x1, y1 - 8), font, scale, color, thickness)

            # Approach rate (vehicles)
            ar = det.get("approach_rate", 0.0)
            if ar is not None:
                cv2.putText(
                    out,
                    f"rate={ar:+.2f}",
                    (x1, y2 + 15),
                    font,
                    scale * 0.9,
                    color,
                    thickness,
                )

            # Arrow if approaching fast
            if ar is not None and ar > 0.1:
                mid_x = (x1 + x2) // 2
                cv2.arrowedLine(
                    out,
                    (mid_x, y1 + 10),
                    (mid_x, y2 - 10),
                    (0, 0, 255),
                    2,
                    tipLength=0.3,
                )

        # HUD — top left
        seq = event.get("frame_seq", 0)
        spd = event.get("rider_speed_mph", 0)
        cv2.putText(
            out,
            f"Limade CV | {seq} | {spd:.1f} mph",
            (10, 25),
            font,
            0.6,
            (255, 255, 255),
            2,
        )

        # HUD — top right: total detections
        total = len(all_dets)
        cv2.putText(
            out,
            f"Det: {total}",
            (self.frame_width - 100, 25),
            font,
            0.6,
            (255, 255, 255),
            2,
        )

        return out


# ═══════════════════════════════════════════════════════════════════════════
# Test Block
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import json

    pipeline = CVPipeline()

    def test_trigger_callback(payload: dict):
        print("\n[TRIGGER FIRED] Module E would be called now.")
        danger = payload["current_event"]["danger_score"]
        print(f"  current danger_score : {danger}")
        trend_scores = [t["danger_score"] for t in payload["trend"]]
        print(f"  trend scores         : {trend_scores}")
        scene = payload["current_event"]["scene_summary"]
        closest = scene["closest_vehicle_distance"]
        print(f"  closest distance     : {closest}")

    pipeline.on_trigger_callback = test_trigger_callback
    cap = cv2.VideoCapture(0)  # default webcam

    if not cap.isOpened():
        print("Cannot open webcam. Testing with synthetic frames.")
        # Generate 30 synthetic frames with a growing rectangle
        # (simulated approaching car)
        for i in range(30):
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            frame[:] = (40, 40, 40)
            # Simulated car: grows from small to large (approaching)
            size = 30 + i * 8
            cx, cy = 640, 400
            x1, y1 = cx - size, cy - size // 2
            x2, y2 = cx + size, cy + size // 2
            cv2.rectangle(frame, (x1, y1), (x2, y2), (180, 180, 200), -1)
            cv2.putText(
                frame,
                f"Synthetic frame {i}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 200, 0),
                2,
            )

            t = time.time()
            mock_metadata = {
                "seq": pipeline.frame_seq,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "gps": {"lat": 41.8781, "lng": -87.6298, "speed_mph": 12.0},
                "orientation": {"alpha": 0, "beta": 85, "gamma": 2}
            }
            event = pipeline.process_frame(frame, metadata=mock_metadata)
            elapsed = (time.time() - t) * 1000

            annotated = pipeline.draw_overlays(frame.copy(), event)

            if i % 5 == 0:
                print(f"\nFrame {i} ({elapsed:.0f}ms):")
                print(json.dumps(event, indent=2, default=str))

            cv2.imshow("ScootSafe CV Test", annotated)
            if cv2.waitKey(100) & 0xFF == ord("q"):
                break
    else:
        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Ensure 720p
            if frame.shape[1] != 1280:
                frame = cv2.resize(frame, (1280, 720))

            t = time.time()
            mock_metadata = {
                "seq": pipeline.frame_seq,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "gps": {"lat": 41.8781, "lng": -87.6298, "speed_mph": 10.0},
                "orientation": {"alpha": 0, "beta": 85, "gamma": 2}
            }
            event = pipeline.process_frame(frame, metadata=mock_metadata)
            elapsed = (time.time() - t) * 1000

            annotated = pipeline.draw_overlays(frame.copy(), event)

            cv2.putText(
                annotated,
                f"{elapsed:.0f}ms",
                (1150, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )

            cv2.imshow("ScootSafe CV", annotated)

            frame_count += 1
            if frame_count % 10 == 0:
                print(
                    f"Frame {frame_count} | {elapsed:.0f}ms | "
                    f"vehicles={event['scene_summary']['total_vehicles']} | "
                    f"hazards={event['scene_summary']['total_hazards']} | "
                    f"fastest_approach={event['scene_summary']['fastest_approach_rate']:.3f}"
                )

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    cv2.destroyAllWindows()
    print("Done.")