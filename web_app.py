import json
import threading
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from werkzeug.utils import secure_filename

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
        self.width = 640
        self.height = 480
        self.fps = 60.0
        self.preview_quality = 68
        self.output_dir = Path("magnetic_cradle_runs")

        self.latest_frame = None
        self.latest_jpeg = None
        self.frame_size = None
        self.error = None
        self.actual_fps = 0.0
        self._fps_frames = 0
        self._fps_started_at = time.monotonic()

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


class OfflineState:
    def __init__(self):
        self.lock = threading.Lock()
        self.video_path = None
        self.first_frame = None
        self.frame_size = None
        self.source_fps = 0.0
        self.total_frames = 0
        self.configs = []
        self.running = False
        self.progress = 0.0
        self.message = "No video loaded"
        self.result = None
        self.error = None


OFFLINE = OfflineState()
VIDEOS_DIR = Path("videos")
VIDEO_RUNS_DIR = Path("video_runs")


def draw_idle_overlay(frame):
    view = frame.copy()
    cv2.putText(view, "Ready", (20, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (80, 230, 80), 2, cv2.LINE_AA)
    return view


def update_actual_fps():
    STATE._fps_frames += 1
    elapsed = time.monotonic() - STATE._fps_started_at
    if elapsed >= 1.0:
        STATE.actual_fps = STATE._fps_frames / elapsed
        STATE._fps_frames = 0
        STATE._fps_started_at = time.monotonic()


def camera_loop():
    while True:
        with STATE.lock:
            if not STATE.running or STATE.cap is None:
                break
            recording = STATE.recording
            trackers = list(STATE.trackers)
            preview_quality = STATE.preview_quality

        ok, frame = STATE.cap.read()
        if not ok:
            with STATE.lock:
                STATE.error = "camera returned no frame"
            time.sleep(0.01)
            continue

        annotated = draw_idle_overlay(frame)
        points = []

        with STATE.lock:
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

        ok_jpeg, buffer = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), preview_quality])
        with STATE.lock:
            STATE.latest_frame = frame.copy()
            if ok_jpeg:
                STATE.latest_jpeg = buffer.tobytes()
            update_actual_fps()


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
    width = int(data.get("width", 640))
    height = int(data.get("height", 480))
    fps = float(data.get("fps", 60))
    preview_quality = int(data.get("previewQuality", 68))

    with STATE.lock:
        if STATE.recording:
            return jsonify({"ok": False, "error": "stop recording first"}), 400
        if STATE.cap is not None:
            stop_camera_locked()
        STATE.camera_index = camera
        STATE.width = width
        STATE.height = height
        STATE.fps = fps
        STATE.preview_quality = max(35, min(90, preview_quality))
        STATE.error = None
        STATE.latest_jpeg = None
        STATE.latest_frame = None
        STATE.frame_size = None
        STATE.actual_fps = 0.0
        STATE._fps_frames = 0
        STATE._fps_started_at = time.monotonic()

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


@app.get("/api/cameras")
def list_cameras():
    devices = []
    with STATE.lock:
        if STATE.running:
            return jsonify(
                {
                    "ok": True,
                    "devices": [
                        {
                            "index": STATE.camera_index,
                            "opened": True,
                            "frame": STATE.frame_size is not None,
                            "width": STATE.frame_size["width"] if STATE.frame_size else None,
                            "height": STATE.frame_size["height"] if STATE.frame_size else None,
                            "active": True,
                        }
                    ],
                }
            )

    for index in range(5):
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        else:
            cap = cv2.VideoCapture(index)
        opened = cap.isOpened()
        ok, frame = cap.read() if opened else (False, None)
        devices.append(
            {
                "index": index,
                "opened": bool(opened),
                "frame": bool(ok),
                "width": int(frame.shape[1]) if frame is not None else None,
                "height": int(frame.shape[0]) if frame is not None else None,
                "active": False,
            }
        )
        cap.release()
    return jsonify({"ok": True, "devices": devices})


@app.post("/api/camera/stop")
def stop_camera():
    with STATE.lock:
        if STATE.recording:
            return jsonify({"ok": False, "error": "stop recording first"}), 400
        stop_camera_locked()
    return jsonify({"ok": True})


@app.get("/api/video")
def video_feed():
    def generate():
        last = None
        while True:
            with STATE.lock:
                jpeg = STATE.latest_jpeg
                running = STATE.running
            if not running:
                break
            if jpeg and jpeg is not last:
                last = jpeg
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            time.sleep(0.003)

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/status")
def status():
    with STATE.lock:
        return jsonify(
            {
                "running": STATE.running,
                "recording": STATE.recording,
                "frameSize": STATE.frame_size,
                "actualFps": round(STATE.actual_fps, 1),
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
        return jsonify({"ok": False, "error": "no calibration data"}), 400

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
            return jsonify({"ok": False, "error": f"marker box {idx} is too small"}), 400
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
            return jsonify({"ok": False, "error": "camera has no frame yet"}), 400
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
            return jsonify({"ok": False, "error": "start camera first"}), 400
        if not STATE.trackers:
            return jsonify({"ok": False, "error": "calibrate first"}), 400
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


@app.route("/video-runs/<path:filename>")
def video_runs(filename):
    return send_from_directory(VIDEO_RUNS_DIR, filename)


@app.post("/api/offline/upload")
def offline_upload():
    uploaded = request.files.get("video")
    if not uploaded or not uploaded.filename:
        return jsonify({"ok": False, "error": "No video file received"}), 400

    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    filename = secure_filename(uploaded.filename)
    if not filename:
        filename = f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
    video_path = VIDEOS_DIR / filename
    uploaded.save(video_path)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return jsonify({"ok": False, "error": "Cannot open uploaded video"}), 400
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        return jsonify({"ok": False, "error": "Cannot read first frame"}), 400

    h, w = frame.shape[:2]
    with OFFLINE.lock:
        OFFLINE.video_path = video_path
        OFFLINE.first_frame = frame
        OFFLINE.frame_size = {"width": w, "height": h}
        OFFLINE.source_fps = fps
        OFFLINE.total_frames = total_frames
        OFFLINE.configs = []
        OFFLINE.progress = 0.0
        OFFLINE.message = "Video loaded. Calibrate pivots and yellow markers."
        OFFLINE.result = None
        OFFLINE.error = None

    return jsonify(
        {
            "ok": True,
            "video": str(video_path),
            "frameSize": OFFLINE.frame_size,
            "sourceFps": round(fps, 3),
            "totalFrames": total_frames,
        }
    )


@app.get("/api/offline/frame")
def offline_frame():
    with OFFLINE.lock:
        frame = None if OFFLINE.first_frame is None else OFFLINE.first_frame.copy()
    if frame is None:
        return jsonify({"ok": False, "error": "No video loaded"}), 400
    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok:
        return jsonify({"ok": False, "error": "Cannot encode frame"}), 500
    return Response(buffer.tobytes(), mimetype="image/jpeg")


@app.post("/api/offline/calibration")
def offline_calibration():
    data = request.get_json(force=True)
    pendulums = data.get("pendulums", [])
    if not pendulums:
        return jsonify({"ok": False, "error": "No calibration data"}), 400

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
            return jsonify({"ok": False, "error": f"Marker box {idx} is too small"}), 400
        configs.append(
            PendulumConfig(
                pendulum_id=idx,
                pivot_x=float(pivot["x"]),
                pivot_y=float(pivot["y"]),
                init_box=init_box,
            )
        )

    with OFFLINE.lock:
        if OFFLINE.first_frame is None:
            return jsonify({"ok": False, "error": "Load a video first"}), 400
        frame = OFFLINE.first_frame.copy()

    try:
        [CamShiftPendulumTracker(frame, cfg) for cfg in configs]
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    with OFFLINE.lock:
        OFFLINE.configs = configs
        OFFLINE.message = "Calibration saved. Ready to analyze."
    return jsonify({"ok": True, "pendulums": [asdict(c) for c in configs]})


def offline_result_links(result):
    run_name = Path(result["run_dir"]).name
    return {
        "runDir": result["run_dir"],
        "rawVideo": f"/video-runs/{run_name}/raw_video.mp4",
        "annotatedVideo": f"/video-runs/{run_name}/annotated_tracking.mp4",
        "wideCsv": f"/video-runs/{run_name}/pendulum_tracking_wide.csv",
        "longCsv": f"/video-runs/{run_name}/pendulum_tracking_long.csv",
        "plot": f"/video-runs/{run_name}/angle_timeseries.png" if result.get("plot") else None,
        "resultJson": f"/video-runs/{run_name}/result.json",
        "frames": result.get("processed_frames", 0),
    }


def offline_worker(options):
    with OFFLINE.lock:
        video_path = OFFLINE.video_path
        first_frame = None if OFFLINE.first_frame is None else OFFLINE.first_frame.copy()
        configs = list(OFFLINE.configs)
        source_fps = float(options.get("fps") or OFFLINE.source_fps or 30.0)
        total_frames = OFFLINE.total_frames
        OFFLINE.running = True
        OFFLINE.progress = 0.0
        OFFLINE.message = "Analyzing video..."
        OFFLINE.result = None
        OFFLINE.error = None

    try:
        if video_path is None or first_frame is None:
            raise RuntimeError("No video loaded")
        if not configs:
            raise RuntimeError("Calibrate before analysis")

        start_s = max(0.0, float(options.get("start") or 0.0))
        end_value = options.get("end")
        end_s = None if end_value in (None, "") else float(end_value)
        preview_every = max(1, int(options.get("previewEvery") or 1))
        start_frame = max(0, int(round(start_s * source_fps)))
        end_frame = total_frames - 1 if end_s is None else min(total_frames - 1, int(round(end_s * source_fps)))
        if total_frames <= 0 or start_frame > end_frame:
            raise RuntimeError("Invalid video frame range")

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError("Cannot open video")
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        run_dir = VIDEO_RUNS_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=True)
        save_config(run_dir / "calibration.json", configs)
        trackers = [CamShiftPendulumTracker(first_frame, cfg) for cfg in configs]
        raw_writer, annotated_writer = open_writers(run_dir, first_frame.shape, source_fps / preview_every)
        rows = []
        processed = 0
        total_to_process = end_frame - start_frame + 1
        source_frame = start_frame

        while source_frame <= end_frame:
            ok, frame = cap.read()
            if not ok:
                break
            time_s = (source_frame - start_frame) / source_fps
            annotated = frame.copy()
            frame_points = []
            for tracker in trackers:
                point = tracker.update(frame, processed, time_s)
                frame_points.append(point)
                tracker.draw(annotated, point)
            rows.extend(frame_points)

            if processed % preview_every == 0:
                raw_writer.write(frame)
                annotated_writer.write(annotated)

            processed += 1
            source_frame += 1
            if processed % 20 == 0:
                with OFFLINE.lock:
                    OFFLINE.progress = processed / total_to_process
                    OFFLINE.message = f"Analyzing {processed}/{total_to_process} frames"

        cap.release()
        raw_writer.release()
        annotated_writer.release()
        long_csv, wide_csv = write_csvs(run_dir, rows, configs)
        plot_path = plot_angles(run_dir, rows)
        result = {
            "video": str(video_path),
            "source_fps": source_fps,
            "source_frames": total_frames,
            "start_frame": start_frame,
            "end_frame": end_frame,
            "processed_frames": processed,
            "run_dir": str(run_dir),
            "raw_video": str(run_dir / "raw_video.mp4"),
            "annotated_video": str(run_dir / "annotated_tracking.mp4"),
            "long_csv": str(long_csv),
            "wide_csv": str(wide_csv),
            "plot": str(plot_path) if plot_path else None,
            "pendulums": [asdict(cfg) for cfg in configs],
        }
        (run_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        with OFFLINE.lock:
            OFFLINE.running = False
            OFFLINE.progress = 1.0
            OFFLINE.message = "Analysis complete"
            OFFLINE.result = offline_result_links(result)
    except Exception as exc:
        with OFFLINE.lock:
            OFFLINE.running = False
            OFFLINE.error = str(exc)
            OFFLINE.message = "Analysis failed"


@app.post("/api/offline/analyze")
def offline_analyze():
    options = request.get_json(force=True, silent=True) or {}
    with OFFLINE.lock:
        if OFFLINE.running:
            return jsonify({"ok": False, "error": "Analysis already running"}), 400
    thread = threading.Thread(target=offline_worker, args=(options,), daemon=True)
    thread.start()
    return jsonify({"ok": True})


@app.get("/api/offline/status")
def offline_status():
    with OFFLINE.lock:
        return jsonify(
            {
                "ok": True,
                "running": OFFLINE.running,
                "progress": round(OFFLINE.progress, 4),
                "message": OFFLINE.message,
                "error": OFFLINE.error,
                "result": OFFLINE.result,
                "frameSize": OFFLINE.frame_size,
                "sourceFps": round(OFFLINE.source_fps, 3),
                "totalFrames": OFFLINE.total_frames,
                "pendulums": [asdict(c) for c in OFFLINE.configs],
            }
        )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=7860, threaded=True)
