from ultralytics import YOLO

def main():
    model = YOLO(r"runs\detect\train20\weights\best.pt")
    # Run validation on test set
    metrics = model.val(data=r"dataset.yaml", split="test")
    print(metrics)


if __name__ == "__main__":
    main()