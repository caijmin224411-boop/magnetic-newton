import json
import threading
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import cv2
from flask import Flask, Response, jsonify, request, send_from_directory

from magnetic_newton_cradle_recorder import (
    CamShiftPendulumTracker,
    PendulumConfig,
    make_capture,
    open_writers,
    plot_angles,
    save_config,
    write_csvs,
)


app = Flask(__name__, static_folder="static", static_url_path="/static")


class RecorderState:
    def __init__(self):
        self.lock = threading.Lock()
        self.cap = None
        self.thread = None
        self.running = False
        self.camera_index = 0
        self.width = 1280
        self.height = 720
        self.fps = 30.0
        self.output_dir = Path("magnetic_cradle_runs")

        self.latest_frame = None
        self.latest_jpeg = None
        self.frame_size = None
        self.error = None

        self.configs = []
        self.trackers = []
        self.recording = False
        self.run_dir = None
        self.raw_writer = None
        self.annotated_writer = None
        self.rows = []
        self.frame_idx = 0
        self.record_started_at = None
        self.recorded_offset_s = 0.0
        self.last_result = None


STATE = RecorderState()


def draw_idle_overlay(frame):
    view = frame.copy()
    cv2.putText(
        view,
        "Ready",
        (20, 34),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.85,
        (80, 230, 80),
        2,
        cv2.LINE_AA,
    )
    return view


def camera_loop():
    while True:
        with STATE.lock:
            if not STATE.running or STATE.cap is None:
                break
            recording = STATE.recording
            trackers = list(STATE.trackers)

        ok, frame = STATE.cap.read()
        if not ok:
            with STATE.lock:
                STATE.error = "摄像头没有返回画面"
            time.sleep(0.05)
            continue

        annotated = draw_idle_overlay(frame)
        points = []

        with STATE.lock:
            if STATE.frame_size is None:
                h, w = frame.shape[:2]
                STATE.frame_size = {"width": w, "height": h}
            if recording and STATE.record_started_at is None:
                STATE.record_started_at = time.monotonic()
            time_s = STATE.recorded_offset_s
            if recording and STATE.record_started_at is not None:
                time_s += time.monotonic() - STATE.record_started_at
            frame_idx = STATE.frame_idx

        if trackers:
            annotated = frame.copy()
            for tracker in trackers:
                point = tracker.update(frame, frame_idx, time_s)
                points.append(point)
                tracker.draw(annotated, point)

            status = "REC" if recording else "READY"
            color = (0, 0, 255) if recording else (80, 230, 80)
            cv2.putText(
                annotated,
                f"{status}  t={time_s:.2f}s",
                (20, 34),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.85,
                color,
                2,
                cv2.LINE_AA,
            )

        if recording:
            with STATE.lock:
                if STATE.raw_writer and STATE.annotated_writer:
                    STATE.raw_writer.write(frame)
                    STATE.annotated_writer.write(annotated)
                    STATE.rows.extend(points)
                    STATE.frame_idx += 1

        ok_jpeg, buffer = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        with STATE.lock:
            STATE.latest_frame = frame.copy()
            if ok_jpeg:
                STATE.latest_jpeg = buffer.tobytes()

        delay = max(0.001, 1.0 / max(STATE.fps, 1.0))
        time.sleep(delay)


def stop_camera_locked():
    STATE.running = False
    if STATE.cap is not None:
        STATE.cap.release()
        STATE.cap = None
    STATE.thread = None


def close_writers_locked():
    if STATE.raw_writer is not None:
        STATE.raw_writer.release()
        STATE.raw_writer = None
    if STATE.annotated_writer is not None:
        STATE.annotated_writer.release()
        STATE.annotated_writer = None


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.post("/api/camera/start")
def start_camera():
    data = request.get_json(force=True, silent=True) or {}
    camera = int(data.get("camera", 0))
    width = int(data.get("width", 1280))
    height = int(data.get("height", 720))
    fps = float(data.get("fps", 30))

    with STATE.lock:
        if STATE.recording:
            return jsonify({"ok": False, "error": "请先停止录像"}), 400
        if STATE.cap is not None:
            stop_camera_locked()
        STATE.camera_index = camera
        STATE.width = width
        STATE.height = height
        STATE.fps = fps
        STATE.error = None
        STATE.latest_jpeg = None
        STATE.latest_frame = None
        STATE.frame_size = None

    try:
        cap = make_capture(camera, width, height, fps)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    with STATE.lock:
        STATE.cap = cap
        STATE.running = True
        STATE.thread = threading.Thread(target=camera_loop, daemon=True)
        STATE.thread.start()
    return jsonify({"ok": True})


@app.post("/api/camera/stop")
def stop_camera():
    with STATE.lock:
        if STATE.recording:
            return jsonify({"ok": False, "error": "请先停止录像"}), 400
        stop_camera_locked()
    return jsonify({"ok": True})


@app.get("/api/video")
def video_feed():
    def generate():
        while True:
            with STATE.lock:
                jpeg = STATE.latest_jpeg
                running = STATE.running
            if not running:
                break
            if jpeg:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            time.sleep(0.04)

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/status")
def status():
    with STATE.lock:
        return jsonify(
            {
                "running": STATE.running,
                "recording": STATE.recording,
                "frameSize": STATE.frame_size,
                "pendulums": [asdict(c) for c in STATE.configs],
                "runDir": str(STATE.run_dir) if STATE.run_dir else None,
                "lastResult": STATE.last_result,
                "error": STATE.error,
            }
        )


@app.post("/api/calibration")
def set_calibration():
    data = request.get_json(force=True)
    pendulums = data.get("pendulums", [])
    if not pendulums:
        return jsonify({"ok": False, "error": "没有收到标定数据"}), 400

    configs = []
    for idx, item in enumerate(pendulums, start=1):
        box = item.get("box", {})
        pivot = item.get("pivot", {})
        init_box = (
            int(round(box["x"])),
            int(round(box["y"])),
            int(round(box["w"])),
            int(round(box["h"])),
        )
        if init_box[2] <= 2 or init_box[3] <= 2:
            return jsonify({"ok": False, "error": f"第 {idx} 个摆球框太小"}), 400
        configs.append(
            PendulumConfig(
                pendulum_id=idx,
                pivot_x=float(pivot["x"]),
                pivot_y=float(pivot["y"]),
                init_box=init_box,
            )
        )

    with STATE.lock:
        if STATE.latest_frame is None:
            return jsonify({"ok": False, "error": "摄像头还没有画面"}), 400
        frame = STATE.latest_frame.copy()

    try:
        trackers = [CamShiftPendulumTracker(frame, cfg) for cfg in configs]
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    with STATE.lock:
        STATE.configs = configs
        STATE.trackers = trackers
    return jsonify({"ok": True, "pendulums": [asdict(c) for c in configs]})


@app.post("/api/record/start")
def start_recording():
    with STATE.lock:
        if not STATE.running or STATE.latest_frame is None:
            return jsonify({"ok": False, "error": "请先打开摄像头"}), 400
        if not STATE.trackers:
            return jsonify({"ok": False, "error": "请先完成标定"}), 400
        if STATE.recording:
            return jsonify({"ok": True})

        STATE.output_dir.mkdir(parents=True, exist_ok=True)
        STATE.run_dir = STATE.output_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
        STATE.run_dir.mkdir(parents=True, exist_ok=True)
        raw, annotated = open_writers(STATE.run_dir, STATE.latest_frame.shape, STATE.fps)
        save_config(STATE.run_dir / "calibration.json", STATE.configs)

        STATE.raw_writer = raw
        STATE.annotated_writer = annotated
        STATE.rows = []
        STATE.frame_idx = 0
        STATE.record_started_at = time.monotonic()
        STATE.recorded_offset_s = 0.0
        STATE.recording = True
        STATE.last_result = None
        for tracker in STATE.trackers:
            tracker.trail.clear()
            tracker.last_angle = None
            tracker.last_time = None

    return jsonify({"ok": True, "runDir": str(STATE.run_dir)})


@app.post("/api/record/stop")
def stop_recording():
    with STATE.lock:
        if not STATE.recording:
            return jsonify({"ok": True, "result": STATE.last_result})
        if STATE.record_started_at is not None:
            STATE.recorded_offset_s += time.monotonic() - STATE.record_started_at
        STATE.recording = False
        STATE.record_started_at = None
        run_dir = STATE.run_dir
        rows = list(STATE.rows)
        configs = list(STATE.configs)
        close_writers_locked()

    long_csv, wide_csv = write_csvs(run_dir, rows, configs)
    plot_path = plot_angles(run_dir, rows)
    result = {
        "runDir": str(run_dir),
        "rawVideo": str(run_dir / "raw_video.mp4"),
        "annotatedVideo": str(run_dir / "annotated_tracking.mp4"),
        "longCsv": str(long_csv),
        "wideCsv": str(wide_csv),
        "plot": str(plot_path) if plot_path else None,
        "frames": max((point.frame for point in rows), default=-1) + 1,
    }
    (run_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    with STATE.lock:
        STATE.last_result = result
    return jsonify({"ok": True, "result": result})


@app.route("/runs/<path:filename>")
def runs(filename):
    return send_from_directory(STATE.output_dir, filename)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=7860, threaded=True)
