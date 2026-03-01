"""
ScootSafe Module E — Backend Hub
==================================
WebSocket server that bridges Module A (React Native phone app) and
Module D (haptics/sound on phone) via CV processing and Claude Haiku reasoning.

Architecture:
  Phone (Module A)  →  WebSocket CLIENT  →  Module E (this file)
  Module E          →  CV pipeline       →  DetectionEvent
  CV trigger        →  Haiku API call    →  AlertDecision
  Module E          →  WebSocket CLIENT  →  Phone (Module D)

Run with:
  export ANTHROPIC_API_KEY=your_key_here
  python Module_E.py
"""

import asyncio
import base64
import json
import time
import logging
import os
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import cv2
import numpy as np
import websockets
from anthropic import AsyncAnthropic

from CV_Module import CVPipeline


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HOST = "0.0.0.0"       # listen on all interfaces so phone can connect over WiFi
PORT = 8765
COOLDOWN_SECONDS = 3.0  # minimum seconds between Haiku API calls
HAIKU_MODEL = "claude-haiku-4-5-20251001"
HAIKU_MAX_TOKENS = 512


# ---------------------------------------------------------------------------
# Haiku system prompt
# ---------------------------------------------------------------------------
HAIKU_SYSTEM_PROMPT = """You are a real-time safety reasoning engine for an electric scooter rider in Chicago.

You receive structured detection data from a computer vision system (YOLOv8).
You do NOT see the camera image — you reason from the detection data only.

You receive:
- current_event: full detection data for the triggering frame
- trend: last 3 frames showing danger_score trajectory (oldest first)

Use the trend to determine if the situation is ESCALATING or RESOLVING:
- danger_score increasing across trend = ESCALATING → higher urgency
- danger_score decreasing = RESOLVING → lower urgency or no alert

FALSE POSITIVE SIGNALS (do NOT alert):
- Vehicles with approach_rate near 0 (parallel traffic, parked cars)
- Pedestrians at far/very_far distance
- track_age of 1 (just appeared, unconfirmed)

REAL THREAT SIGNALS (DO alert):
- approach_rate > 0.15 AND direction contains "center"
- estimated_distance is "very_close" or "close" AND approach_rate positive
- Multiple hazards detected
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
  "threat_type": "fast_vehicle" or "pothole" or "construction" or "pedestrian" or "multi_threat" or "false_positive",
  "threat_summary": "one sentence describing the threat",
  "rider_action": "what the rider should do",
  "alert_type": "haptic_only" or "sound_only" or "haptic_and_sound" or "none",
  "haptic_pattern": "single_pulse" or "double_pulse" or "triple_pulse" or "continuous" or "none",
  "sound_type": "chime" or "beep" or "spoken" or "none",
  "sound_content": "spoken text if sound_type is spoken, otherwise empty string",
  "reasoning": "one sentence explaining your decision referencing the detection data"
}"""


# ---------------------------------------------------------------------------
# ScootSafeServer
# ---------------------------------------------------------------------------

class ScootSafeServer:
    """
    Top-level server class. All state lives here.
    One asyncio event loop drives everything:
      - WebSocket server (async)
      - CV processing (ThreadPoolExecutor — never blocks the loop)
      - Haiku API calls (async, fired from trigger_queue)
    """

    def __init__(self):
        self.pipeline = CVPipeline()
        self.pipeline.on_trigger_callback = self._on_cv_trigger

        self.anthropic = AsyncAnthropic()  # reads ANTHROPIC_API_KEY from environment
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.loop: asyncio.AbstractEventLoop | None = None

        # Cooldown state
        self.last_haiku_call: float = 0.0  # unix timestamp of last Haiku call

        # Connected WebSocket clients — store all connections so we can broadcast AlertDecision
        self.clients: set = set()

        # Pending trigger payload — CV thread sets this, async loop reads it
        # Using asyncio.Queue so the thread can safely hand off to the async world
        self.trigger_queue: asyncio.Queue = asyncio.Queue()

        # Frame counter for metadata seq numbers
        self.frame_counter: int = 0

        logging.basicConfig(level=logging.INFO)
        self.log = logging.getLogger("ScootSafe.ModuleE")

    # ------------------------------------------------------------------
    async def handle_client(self, websocket):
        """
        Handles one connected React Native client.
        Module A sends a single JSON message per frame:
          { "image": "<base64 jpeg>", "latitude": 41.8781, "longitude": -87.6298 }

        After processing we send back an ack so the phone's sendAndWait()
        resolves and it can send the next frame.
        """
        self.clients.add(websocket)
        self.log.info(f"Client connected: {websocket.remote_address}")
        try:
            async for message in websocket:
                if not isinstance(message, str):
                    continue

                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    self.log.warning("Received invalid JSON, skipping")
                    await websocket.send(json.dumps({"type": "ack"}))
                    continue

                b64 = data.get("image")
                if not b64:
                    self.log.warning("No image field in message, skipping")
                    await websocket.send(json.dumps({"type": "ack"}))
                    continue

                frame = self._decode_base64_jpeg(b64)
                if frame is None:
                    self.log.warning("Failed to decode base64 JPEG, skipping")
                    await websocket.send(json.dumps({"type": "ack"}))
                    continue

                metadata = {
                    "seq": self.frame_counter,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "gps": {
                        "lat": data.get("latitude", 0.0),
                        "lng": data.get("longitude", 0.0),
                        "speed_mph": 0.0,
                    },
                    "orientation": {},
                }
                self.frame_counter += 1

                # Submit to CV pipeline in thread pool (non-blocking)
                self.loop.run_in_executor(
                    self.executor,
                    self.pipeline.process_frame,
                    frame,
                    metadata,
                )

                # Ack immediately so phone's sendAndWait resolves
                await websocket.send(json.dumps({"type": "ack"}))

        except websockets.exceptions.ConnectionClosed:
            self.log.info(f"Client disconnected: {websocket.remote_address}")
        finally:
            self.clients.discard(websocket)

    # ------------------------------------------------------------------
    def _decode_base64_jpeg(self, b64_string: str) -> np.ndarray | None:
        """Decode a base64 JPEG string to a BGR numpy array."""
        try:
            jpg_bytes = base64.b64decode(b64_string)
            arr = np.frombuffer(jpg_bytes, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            return frame  # None if decode failed
        except Exception as exc:
            self.log.error(f"Base64 JPEG decode error: {exc}")
            return None

    # ------------------------------------------------------------------
    def _on_cv_trigger(self, payload: dict) -> None:
        """
        Called by CVPipeline from a worker thread when danger is detected.
        Hands payload to the asyncio event loop via thread-safe queue put.
        """
        if self.loop is not None:
            self.loop.call_soon_threadsafe(
                self.trigger_queue.put_nowait, payload
            )

    # ------------------------------------------------------------------
    async def process_triggers(self):
        """
        Continuously reads from trigger_queue.
        Enforces cooldown. Fires Haiku API call when cooldown has passed.
        Runs forever as an asyncio task.
        """
        while True:
            payload = await self.trigger_queue.get()

            now = time.monotonic()
            time_since_last = now - self.last_haiku_call

            if time_since_last < COOLDOWN_SECONDS:
                remaining = COOLDOWN_SECONDS - time_since_last
                self.log.info(f"[Cooldown] Skipping trigger, {remaining:.1f}s remaining")
                continue

            self.last_haiku_call = now
            self.log.info(f"[Trigger] Cooldown passed — firing Haiku call")

            # Fire async Haiku call (non-blocking, awaited here but loop continues)
            asyncio.create_task(self._call_haiku(payload))

    # ------------------------------------------------------------------
    async def _call_haiku(self, payload: dict):
        """
        Calls Claude Haiku with the CV trigger payload.
        Sends AlertDecision to all connected WebSocket clients on success.
        """
        try:
            # Format the user message
            current = payload["current_event"]
            trend = payload["trend"]

            scene = current.get("scene_summary", {})
            detections = current.get("detections", [])
            hazards = current.get("hazards", [])

            det_lines = []
            for d in detections:
                det_lines.append(
                    f"  - {d['label']} | conf={d['confidence']:.2f} | "
                    f"dist={d.get('estimated_distance','?')} | "
                    f"approach={d.get('approach_rate', 0):.3f} | "
                    f"dir={d.get('direction','?')} | "
                    f"track_age={d.get('track_age', 0)}"
                )
            for h in hazards:
                det_lines.append(
                    f"  - HAZARD: {h['label']} | conf={h['confidence']:.2f} | "
                    f"dist={h.get('estimated_distance','?')}"
                )

            trend_lines = [
                f"  frame {t['frame_seq']}: danger={t['danger_score']} | "
                f"dist={t['closest_vehicle_distance']} | "
                f"approach={t['fastest_approach_rate']}"
                for t in trend
            ]

            user_message = (
                f"CURRENT FRAME (seq={current.get('frame_seq')}):\n"
                f"  danger_score: {current.get('danger_score')}\n"
                f"  rider_speed_mph: {current.get('rider_speed_mph', 0)}\n"
                f"  closest_vehicle: {scene.get('closest_vehicle_distance')}\n"
                f"  fastest_approach: {scene.get('fastest_approach_rate')}\n"
                f"  total_vehicles: {scene.get('total_vehicles')}\n"
                f"  total_hazards: {scene.get('total_hazards')}\n"
                f"\nDETECTIONS:\n" + ("\n".join(det_lines) if det_lines else "  none") +
                f"\n\nTREND (oldest → newest):\n" + "\n".join(trend_lines)
            )

            response = await self.anthropic.messages.create(
                model=HAIKU_MODEL,
                max_tokens=HAIKU_MAX_TOKENS,
                system=HAIKU_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )

            raw = response.content[0].text.strip()

            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw.rsplit("```", 1)[0]

            alert_decision = json.loads(raw.strip())

            self.log.info(
                f"[Haiku] is_real_threat={alert_decision.get('is_real_threat')} | "
                f"urgency={alert_decision.get('urgency')} | "
                f"type={alert_decision.get('threat_type')}"
            )

            # Only forward to Module D if it's a real threat
            if alert_decision.get("is_real_threat"):
                await self._send_alert(alert_decision)

        except json.JSONDecodeError as exc:
            self.log.error(f"[Haiku] Failed to parse response JSON: {exc}")
        except Exception as exc:
            self.log.error(f"[Haiku] API call failed: {exc}")

    # ------------------------------------------------------------------
    async def _send_alert(self, alert_decision: dict):
        """
        Broadcast AlertDecision JSON to all connected WebSocket clients.
        Module D (React Native) receives this and triggers haptics/sound.
        """
        if not self.clients:
            self.log.warning("[Alert] No connected clients to send alert to")
            return

        message = json.dumps({
            "type": "alert",
            "payload": alert_decision
        })

        # Send to all connected clients concurrently
        disconnected = set()
        for ws in self.clients:
            try:
                await ws.send(message)
                self.log.info(f"[Alert] Sent to {ws.remote_address}: urgency={alert_decision.get('urgency')}")
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(ws)

        self.clients -= disconnected

    # ------------------------------------------------------------------
    async def start(self):
        """
        Start the WebSocket server and trigger processor.
        Both run concurrently on the same event loop.
        """
        self.loop = asyncio.get_running_loop()

        # Start trigger processor as background task
        asyncio.create_task(self.process_triggers())

        self.log.info(f"ScootSafe Module E starting on ws://{HOST}:{PORT}")
        self.log.info("Waiting for React Native client to connect...")

        async with websockets.serve(self.handle_client, HOST, PORT):
            await asyncio.Future()  # run forever


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY environment variable not set.")
        print("Run: export ANTHROPIC_API_KEY=your_key_here")
        sys.exit(1)

    server = ScootSafeServer()
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\nShutting down ScootSafe Module E.")