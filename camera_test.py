import cv2


def main():
    for index in range(5):
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(index)
        opened = cap.isOpened()
        ok, frame = cap.read() if opened else (False, None)
        if frame is None:
            print(f"camera {index}: opened={opened}, frame={ok}")
        else:
            h, w = frame.shape[:2]
            print(f"camera {index}: opened={opened}, frame={ok}, size={w}x{h}")
        cap.release()


if __name__ == "__main__":
    main()
