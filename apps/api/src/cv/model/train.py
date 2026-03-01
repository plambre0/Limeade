from ultralytics import YOLO

def main():
    model = YOLO("yolov8n.pt")

    model.train(
        data="dataset.yaml",
        epochs=20,
        imgsz=640,
        batch=16,
        device=0,      # use GPU
        workers=4,     # multiprocessing workers
        amp=True
    )

if __name__ == "__main__":
    main()