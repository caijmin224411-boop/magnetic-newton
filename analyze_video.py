import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import cv2

from magnetic_newton_cradle_recorder import (
    CamShiftPendulumTracker,
    PendulumConfig,
    calibrate,
    load_config,
    open_writers,
    plot_angles,
    save_config,
    write_csvs,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Analyze a recorded magnetic Newton cradle video frame by frame.")
    parser.add_argument("--video", type=Path, required=True, help="video file to analyze")
    parser.add_argument("--num-pendulums", type=int, default=5, help="number of pendulums to track")
    parser.add_argument("--output-dir", type=Path, default=Path("video_runs"))
    parser.add_argument("--config", type=Path, default=None, help="reuse a saved calibration JSON")
    parser.add_argument("--start", type=float, default=0.0, help="start time in seconds")
    parser.add_argument("--end", type=float, default=None, help="end time in seconds")
    parser.add_argument("--fps", type=float, default=None, help="override video FPS when metadata is wrong")
    parser.add_argument("--display-scale", type=float, default=1.0, help="interactive calibration display scale")
    parser.add_argument("--preview-every", type=int, default=1, help="write every Nth frame to annotated preview video")
    return parser.parse_args()


def read_frame_at(cap, frame_index):
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = cap.read()
    if not ok:
        raise RuntimeError(f"Cannot read frame {frame_index}")
    return frame


def scale_frame(frame, scale):
    if abs(scale - 1.0) < 1e-6:
        return frame
    h, w = frame.shape[:2]
    return cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def unscale_configs(configs, scale):
    if abs(scale - 1.0) < 1e-6:
        return configs
    fixed = []
    for cfg in configs:
        x, y, w, h = cfg.init_box
        fixed.append(
            PendulumConfig(
                pendulum_id=cfg.pendulum_id,
                pivot_x=cfg.pivot_x / scale,
                pivot_y=cfg.pivot_y / scale,
                init_box=(
                    int(round(x / scale)),
                    int(round(y / scale)),
                    int(round(w / scale)),
                    int(round(h / scale)),
                ),
            )
        )
    return fixed


def make_run_dir(output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    run_dir = output_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def analyze_video(args):
    if not args.video.exists():
        raise FileNotFoundError(args.video)

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {args.video}")

    source_fps = args.fps or cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    start_frame = max(0, int(round(args.start * source_fps)))
    end_frame = total_frames - 1 if args.end is None else min(total_frames - 1, int(round(args.end * source_fps)))
    if total_frames <= 0 or start_frame > end_frame:
        raise RuntimeError("Invalid video frame range")

    first_frame = read_frame_at(cap, start_frame)
    if args.config:
        configs = load_config(args.config)
    else:
        calibration_frame = scale_frame(first_frame, args.display_scale)
        configs = calibrate(calibration_frame, args.num_pendulums)
        configs = unscale_configs(configs, args.display_scale)

    run_dir = make_run_dir(args.output_dir)
    save_config(run_dir / "calibration.json", configs)

    trackers = [CamShiftPendulumTracker(first_frame, cfg) for cfg in configs]
    raw_writer, annotated_writer = open_writers(run_dir, first_frame.shape, source_fps / max(1, args.preview_every))
    rows = []

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    processed = 0
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

        if processed % max(1, args.preview_every) == 0:
            raw_writer.write(frame)
            annotated_writer.write(annotated)

        processed += 1
        source_frame += 1
        if processed % 200 == 0:
            print(f"processed {processed}/{end_frame - start_frame + 1} frames")

    cap.release()
    raw_writer.release()
    annotated_writer.release()

    long_csv, wide_csv = write_csvs(run_dir, rows, configs)
    plot_path = plot_angles(run_dir, rows)
    result = {
        "video": str(args.video),
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
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def main():
    analyze_video(parse_args())


if __name__ == "__main__":
    main()
