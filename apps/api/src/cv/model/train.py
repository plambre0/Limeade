import argparse

from ultralytics import YOLO

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", choices=["n", "s", "m", "l"], default="m",
                        help="model size: n=nano, s=small, m=medium, l=large")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch", type=int, default=16)
    args = parser.parse_args()

    model = YOLO(f"yolov8{args.size}.pt")

    model.train(
        data="dataset.yaml",
        epochs=args.epochs,
        imgsz=640,
        batch=args.batch,
        device=0,
        workers=4,
        amp=True,
    )

if __name__ == "__main__":
    main()