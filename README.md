# Limeade — real-time scooter hazard alerts + mapping

Real-time safety system for electric scooter riders: detects road hazards ahead, alerts riders via haptics/TTS, and logs hazards into a database so future rides get warned instantly.

---

<img width="1776" height="994" alt="image" src="https://github.com/user-attachments/assets/aa6f771e-c4e9-4f58-8b12-37207e78246b" />


---

## Features
- Real-time pipeline: **Phone (5 FPS) → WebSocket → YOLOv8 CV → Claude Haiku → Alert → Phone haptics/TTS**
- Detects scooter-critical hazards (potholes, metal plates, surface transitions, grates, uneven pavement)
- “Known hazard” mode: warns instantly from the hazard DB (no repeat AI cost)
- “New hazard” mode: AI flags hazards within seconds and stores photo + type + severity + location
- Hands-free rider experience (no screen interaction required during ride)
- Hazard data layer for fleet ops + city planners (dashboard-ready via FastAPI hazard DB)
- Designed to scale from phone-on-scooter prototype to built-in scooter sensor kit (camera + accelerometer)

---

## Tech Stack
- Python
- WebSocket server (Module E)
- YOLOv8 (computer vision)
- Anthropic Claude Haiku (hazard analysis / labeling)
- FastAPI (hazard DB API)

---

## Quickstart (Backend)

### Prereqs
- Python 3.x
- `pip`
- Anthropic API key

### Install
```bash
cd apps/api
pip install -r requirements.txt
```
### Dataset Source
https://universe.roboflow.com/damz/dash-cam-pothole-detection-uplo2

