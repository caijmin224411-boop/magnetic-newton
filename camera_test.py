import cv2
import time


def main():
    for index in range(5):
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 60)
        if not cap.isOpened():
            cap = cv2.VideoCapture(index)
        opened = cap.isOpened()
        ok, frame = cap.read() if opened else (False, None)
        measured_fps = 0.0
        if opened and ok:
            frames = 0
            started = time.monotonic()
            while time.monotonic() - started < 2.0:
                ok_loop, _ = cap.read()
                if ok_loop:
                    frames += 1
            elapsed = time.monotonic() - started
            measured_fps = frames / elapsed if elapsed > 0 else 0.0
        if frame is None:
            print(f"camera {index}: opened={opened}, frame={ok}")
        else:
            h, w = frame.shape[:2]
            print(f"camera {index}: opened={opened}, frame={ok}, size={w}x{h}, fps={measured_fps:.1f}")
        cap.release()


if __name__ == "__main__":
    main()
