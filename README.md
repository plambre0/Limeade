# ScootSafe

Real-time safety system for electric scooter riders.

## How it works
Phone (5 FPS) → WebSocket → YOLOv8 CV → Claude Haiku → Alert → Phone haptics/TTS

## Run the backend
```bash
cd apps/api
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
python Module_E.py
```

## Ports
- Module E (CV + Haiku): ws://0.0.0.0:8765
- FastAPI (hazard DB): http://localhost:8000