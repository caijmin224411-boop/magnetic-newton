import argparse
import csv
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np


@dataclass
class PendulumConfig:
    pendulum_id: int
    pivot_x: float
    pivot_y: float
    init_box: tuple


@dataclass
class TrackPoint:
    frame: int
    time_s: float
    pendulum_id: int
    x_px: float
    y_px: float
    angle_rad: float
    angle_deg: float
    omega_rad_s: float
    speed_px_s: float
    confidence: float


class CamShiftPendulumTracker:
    def __init__(self, frame, config: PendulumConfig):
        self.config = config
        self.window = tuple(int(v) for v in config.init_box)
        self.last_center = None
        self.last_angle = None
        self.last_time = None
        self.last_x = None
        self.last_y = None
        self.trail = []

        x, y, w, h = self.window
        roi = frame[y : y + h, x : x + w]
        if roi.size == 0:
            raise ValueError(f"pendulum {config.pendulum_id}: initial box is empty")

        self.initial_center = (x + w / 2.0, y + h / 2.0)
        self.length_px = max(
            20.0,
            math.hypot(self.initial_center[0] - config.pivot_x, self.initial_center[1] - config.pivot_y),
        )
        self.radius_tolerance = max(22.0, 0.18 * self.length_px, max(w, h) * 1.6)
        self.search_margin = int(max(28.0, max(w, h) * 2.5))
        self.max_angle_rad = math.radians(78.0)

        hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        self.target_hsv, self.hue_tol, self.sat_tol, self.val_tol, self.track_white = self._learn_color_profile(hsv_roi)
        mask = cv2.inRange(hsv_roi, (0, 25, 35), (179, 255, 255))
        hist = cv2.calcHist([hsv_roi], [0, 1], mask, [36, 32], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 255, cv2.NORM_MINMAX)
        self.hist = hist
        self.term_crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 12, 1)

    def _learn_color_profile(self, hsv_roi):
        pixels = hsv_roi.reshape(-1, 3)
        saturated = pixels[(pixels[:, 1] >= 45) & (pixels[:, 2] >= 45)]
        if len(saturated) >= max(8, len(pixels) * 0.08):
            sample = saturated
            track_white = False
        else:
            bright = pixels[(pixels[:, 1] <= 80) & (pixels[:, 2] >= 120)]
            sample = bright if len(bright) >= 6 else pixels
            track_white = True

        target = np.median(sample, axis=0).astype(np.float32)
        spread = np.std(sample.astype(np.float32), axis=0)

        if track_white:
            hue_tol = 90
            sat_tol = max(35, int(spread[1] * 2.5 + 20))
            val_tol = max(45, int(spread[2] * 2.5 + 25))
        else:
            hue_tol = max(8, min(22, int(spread[0] * 2.5 + 8)))
            sat_tol = max(45, min(110, int(spread[1] * 2.5 + 35)))
            val_tol = max(55, min(130, int(spread[2] * 2.5 + 45)))
        return target, hue_tol, sat_tol, val_tol, track_white

    def _color_mask(self, hsv_region):
        h = hsv_region[:, :, 0].astype(np.int16)
        s = hsv_region[:, :, 1].astype(np.int16)
        v = hsv_region[:, :, 2].astype(np.int16)
        th, ts, tv = self.target_hsv.astype(np.int16)

        if self.track_white:
            mask = (s <= max(95, ts + self.sat_tol)) & (v >= max(80, tv - self.val_tol))
        else:
            hue_delta = np.abs(h - th)
            hue_delta = np.minimum(hue_delta, 180 - hue_delta)
            mask = (
                (hue_delta <= self.hue_tol)
                & (np.abs(s - ts) <= self.sat_tol)
                & (np.abs(v - tv) <= self.val_tol)
                & (s >= max(35, ts - self.sat_tol))
                & (v >= max(35, tv - self.val_tol))
            )
        return mask.astype(np.uint8) * 255

    def _search_bounds(self, frame_shape):
        h, w = frame_shape[:2]
        px, py = self.config.pivot_x, self.config.pivot_y
        reach_x = self.length_px * math.sin(self.max_angle_rad) + self.radius_tolerance + self.search_margin
        reach_up = self.radius_tolerance + self.search_margin
        reach_down = self.length_px + self.radius_tolerance + self.search_margin
        x1 = max(0, int(px - reach_x))
        y1 = max(0, int(py - reach_up))
        x2 = min(w, int(px + reach_x))
        y2 = min(h, int(py + reach_down))
        return x1, y1, x2, y2

    def _geometry_mask(self, height, width, offset_x, offset_y):
        yy, xx = np.mgrid[0:height, 0:width]
        gx = xx + offset_x
        gy = yy + offset_y
        dx = gx - self.config.pivot_x
        dy = gy - self.config.pivot_y
        radius = np.sqrt(dx * dx + dy * dy)
        angle = np.arctan2(dx, dy)
        return (
            (np.abs(radius - self.length_px) <= self.radius_tolerance)
            & (np.abs(angle) <= self.max_angle_rad)
            & (dy > 0)
        )

    def _measure_point(self, cx, cy, confidence, frame_idx, time_s):
        angle = math.atan2(cx - self.config.pivot_x, self.config.pivot_y - cy)
        if self.last_angle is None or self.last_time is None or time_s <= self.last_time:
            omega = 0.0
            speed = 0.0
        else:
            dt = time_s - self.last_time
            dtheta = math.atan2(math.sin(angle - self.last_angle), math.cos(angle - self.last_angle))
            omega = dtheta / dt
            speed = math.hypot(cx - self.last_x, cy - self.last_y) / dt

        self.last_center = (cx, cy)
        self.last_angle = angle
        self.last_time = time_s
        self.last_x = cx
        self.last_y = cy
        self.trail.append((int(cx), int(cy)))
        self.trail = self.trail[-90:]

        return TrackPoint(
            frame=frame_idx,
            time_s=time_s,
            pendulum_id=self.config.pendulum_id,
            x_px=float(cx),
            y_px=float(cy),
            angle_rad=float(angle),
            angle_deg=float(math.degrees(angle)),
            omega_rad_s=float(omega),
            speed_px_s=float(speed),
            confidence=float(confidence),
        )

    def _best_component_from_mask(self, mask, sx1, sy1):
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
        best = None
        predicted = self.last_center or self.initial_center

        for label in range(1, num_labels):
            area = int(stats[label, cv2.CC_STAT_AREA])
            if area < 5:
                continue
            local_cx, local_cy = centroids[label]
            cx = float(local_cx + sx1)
            cy = float(local_cy + sy1)
            distance_penalty = 0.04 * math.hypot(cx - predicted[0], cy - predicted[1])
            radius_penalty = 0.025 * abs(
                math.hypot(cx - self.config.pivot_x, cy - self.config.pivot_y) - self.length_px
            )
            score = area - distance_penalty - radius_penalty
            if best is None or score > best[0]:
                best = (score, cx, cy, min(1.0, area / 80.0))
        return best

    def update(self, frame, frame_idx, time_s):
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        back_proj = cv2.calcBackProject([hsv], [0, 1], self.hist, [0, 180, 0, 256], 1)
        back_proj = cv2.GaussianBlur(back_proj, (5, 5), 0)

        h, w = frame.shape[:2]
        sx1, sy1, sx2, sy2 = self._search_bounds(frame.shape)
        search = back_proj[sy1:sy2, sx1:sx2]
        if search.size:
            geom = self._geometry_mask(search.shape[0], search.shape[1], sx1, sy1)
            hsv_search = hsv[sy1:sy2, sx1:sx2]
            color_mask = self._color_mask(hsv_search)
            color_mask[~geom] = 0
            best_color = self._best_component_from_mask(color_mask, sx1, sy1)
            if best_color is not None:
                cx, cy, confidence = best_color[1], best_color[2], best_color[3]
                box_size = int(max(16, min(80, self.radius_tolerance)))
                self.window = (
                    max(0, int(cx - box_size / 2)),
                    max(0, int(cy - box_size / 2)),
                    min(box_size, w),
                    min(box_size, h),
                )
                return self._measure_point(cx, cy, confidence, frame_idx, time_s)

            bright = cv2.inRange(hsv_search, (0, 0, 130), (179, 90, 255))
            combined = search.copy()
            combined[bright > 0] = np.maximum(combined[bright > 0], 220)
            combined[~geom] = 0
            nonzero = combined[combined > 0]
            if nonzero.size:
                threshold = max(35, int(np.percentile(nonzero, 88)))
                mask = (combined >= threshold).astype(np.uint8) * 255
                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
                mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
                num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
                best = None
                predicted = self.last_center or self.initial_center
                for label in range(1, num_labels):
                    area = int(stats[label, cv2.CC_STAT_AREA])
                    if area < 6:
                        continue
                    local_cx, local_cy = centroids[label]
                    cx = float(local_cx + sx1)
                    cy = float(local_cy + sy1)
                    distance_penalty = 0.02 * math.hypot(cx - predicted[0], cy - predicted[1])
                    radius_penalty = 0.015 * abs(
                        math.hypot(cx - self.config.pivot_x, cy - self.config.pivot_y) - self.length_px
                    )
                    component_values = combined[labels == label]
                    score = float(np.mean(component_values)) + 0.18 * area - distance_penalty - radius_penalty
                    if best is None or score > best[0]:
                        best = (score, cx, cy, float(np.mean(component_values) / 255.0))
                if best is not None:
                    cx, cy, confidence = best[1], best[2], best[3]
                    box_size = int(max(16, min(80, self.radius_tolerance)))
                    self.window = (
                        max(0, int(cx - box_size / 2)),
                        max(0, int(cy - box_size / 2)),
                        min(box_size, w),
                        min(box_size, h),
                    )
                    return self._measure_point(cx, cy, confidence, frame_idx, time_s)

        x, y, bw, bh = self.window
        x = max(0, min(x, w - 1))
        y = max(0, min(y, h - 1))
        bw = max(10, min(bw, w - x))
        bh = max(10, min(bh, h - y))
        self.window = (x, y, bw, bh)

        try:
            rotated_rect, new_window = cv2.CamShift(back_proj, self.window, self.term_crit)
        except cv2.error:
            rotated_rect = ((x + bw / 2, y + bh / 2), (bw, bh), 0)
            new_window = self.window

        cx, cy = rotated_rect[0]
        self.window = tuple(int(v) for v in new_window)

        x0, y0, ww, hh = self.window
        x1 = max(0, min(x0, w - 1))
        y1 = max(0, min(y0, h - 1))
        x2 = max(x1 + 1, min(x0 + ww, w))
        y2 = max(y1 + 1, min(y0 + hh, h))
        confidence = float(np.mean(back_proj[y1:y2, x1:x2]) / 255.0)
        return self._measure_point(cx, cy, confidence, frame_idx, time_s)

    def draw(self, frame, point: TrackPoint):
        color = palette(self.config.pendulum_id)
        px, py = int(self.config.pivot_x), int(self.config.pivot_y)
        cx, cy = int(point.x_px), int(point.y_px)
        cv2.circle(frame, (px, py), 4, color, -1)
        cv2.line(frame, (px, py), (cx, cy), color, 2, cv2.LINE_AA)
        cv2.circle(frame, (cx, cy), 9, color, 2, cv2.LINE_AA)
        if len(self.trail) >= 2:
            cv2.polylines(frame, [np.array(self.trail, dtype=np.int32)], False, color, 1, cv2.LINE_AA)
        cv2.putText(
            frame,
            f"P{self.config.pendulum_id}",
            (cx + 10, cy - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )


def palette(index):
    colors = [
        (0, 255, 255),
        (0, 180, 255),
        (80, 220, 80),
        (255, 160, 80),
        (255, 80, 200),
        (180, 120, 255),
        (255, 255, 80),
        (120, 255, 220),
    ]
    return colors[(index - 1) % len(colors)]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Record and track a magnetic Newton's cradle / coupled pendulum experiment."
    )
    parser.add_argument("--camera", type=int, default=0, help="camera index, usually 0")
    parser.add_argument("--num-pendulums", type=int, default=5, help="number of pendulums to track")
    parser.add_argument("--output-dir", type=Path, default=Path("magnetic_cradle_runs"))
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--config", type=Path, default=None, help="reuse a saved calibration JSON")
    parser.add_argument("--no-preview", action="store_true", help="record without live preview after calibration")
    parser.add_argument("--duration", type=float, default=None, help="seconds to record in no-preview mode")
    return parser.parse_args()


def click_pivots(frame, count):
    points = []
    work = frame.copy()
    window = "click pendulum pivots"

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(points) < count:
            points.append((x, y))

    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(window, on_mouse)

    while True:
        view = work.copy()
        for idx, (x, y) in enumerate(points, start=1):
            cv2.circle(view, (x, y), 5, palette(idx), -1)
            cv2.putText(view, str(idx), (x + 8, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, palette(idx), 2)
        cv2.putText(
            view,
            f"Click pivot points left to right: {len(points)}/{count}. Enter=confirm, Backspace=undo",
            (20, 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.imshow(window, view)
        key = cv2.waitKey(20) & 0xFF
        if key in (13, 10) and len(points) == count:
            break
        if key in (8, 127) and points:
            points.pop()
        if key in (27, ord("q")):
            raise KeyboardInterrupt("calibration cancelled")

    cv2.destroyWindow(window)
    return points


def calibrate(frame, num_pendulums):
    pivots = click_pivots(frame, num_pendulums)
    configs = []
    for idx, pivot in enumerate(pivots, start=1):
        hint = frame.copy()
        cv2.circle(hint, tuple(map(int, pivot)), 6, palette(idx), -1)
        cv2.putText(
            hint,
            f"Select bob/marker box for pendulum {idx}, then press Enter/Space",
            (20, 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        box = cv2.selectROI(f"select bob {idx}", hint, fromCenter=False, showCrosshair=True)
        cv2.destroyWindow(f"select bob {idx}")
        if box[2] <= 0 or box[3] <= 0:
            raise KeyboardInterrupt("empty bob box selected")
        configs.append(PendulumConfig(idx, float(pivot[0]), float(pivot[1]), tuple(int(v) for v in box)))
    return configs


def make_capture(camera_index, width, height, fps):
    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera index {camera_index}")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    return cap


def save_config(path, configs):
    payload = {"pendulums": [asdict(c) for c in configs]}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_config(path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        PendulumConfig(
            int(item["pendulum_id"]),
            float(item["pivot_x"]),
            float(item["pivot_y"]),
            tuple(int(v) for v in item["init_box"]),
        )
        for item in payload["pendulums"]
    ]


def open_writers(run_dir, frame_shape, fps):
    h, w = frame_shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    raw = cv2.VideoWriter(str(run_dir / "raw_video.mp4"), fourcc, fps, (w, h))
    annotated = cv2.VideoWriter(str(run_dir / "annotated_tracking.mp4"), fourcc, fps, (w, h))
    if not raw.isOpened() or not annotated.isOpened():
        raise RuntimeError("Cannot open video writer. Try another output directory or codec.")
    return raw, annotated


def write_csvs(run_dir, rows, configs):
    long_path = run_dir / "pendulum_tracking_long.csv"
    wide_path = run_dir / "pendulum_tracking_wide.csv"

    long_fields = [
        "frame",
        "time_s",
        "pendulum_id",
        "x_px",
        "y_px",
        "angle_rad",
        "angle_deg",
        "omega_rad_s",
        "speed_px_s",
        "confidence",
    ]
    with long_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=long_fields)
        writer.writeheader()
        for point in rows:
            writer.writerow({name: getattr(point, name) for name in long_fields})

    by_frame = {}
    for point in rows:
        item = by_frame.setdefault(point.frame, {"frame": point.frame, "time_s": point.time_s})
        prefix = f"p{point.pendulum_id}"
        item[f"{prefix}_x_px"] = point.x_px
        item[f"{prefix}_y_px"] = point.y_px
        item[f"{prefix}_angle_deg"] = point.angle_deg
        item[f"{prefix}_omega_rad_s"] = point.omega_rad_s
        item[f"{prefix}_confidence"] = point.confidence

    wide_fields = ["frame", "time_s"]
    for cfg in configs:
        prefix = f"p{cfg.pendulum_id}"
        wide_fields.extend(
            [
                f"{prefix}_x_px",
                f"{prefix}_y_px",
                f"{prefix}_angle_deg",
                f"{prefix}_omega_rad_s",
                f"{prefix}_confidence",
            ]
        )
    with wide_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=wide_fields)
        writer.writeheader()
        for frame in sorted(by_frame):
            writer.writerow(by_frame[frame])

    return long_path, wide_path


def plot_angles(run_dir, rows):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    if not rows:
        return None

    fig, ax = plt.subplots(figsize=(10, 5))
    ids = sorted({p.pendulum_id for p in rows})
    for pendulum_id in ids:
        subset = [p for p in rows if p.pendulum_id == pendulum_id]
        ax.plot([p.time_s for p in subset], [p.angle_deg for p in subset], label=f"P{pendulum_id}", lw=1.2)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("angle (deg)")
    ax.set_title("Tracked pendulum angles")
    ax.grid(True, alpha=0.3)
    ax.legend(ncol=min(5, len(ids)))
    fig.tight_layout()
    path = run_dir / "angle_timeseries.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def main():
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run_dir = args.output_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    cap = make_capture(args.camera, args.width, args.height, args.fps)
    ok, first_frame = cap.read()
    if not ok:
        cap.release()
        raise RuntimeError("Camera opened, but no frame was received.")

    if args.config:
        configs = load_config(args.config)
    else:
        configs = calibrate(first_frame, args.num_pendulums)
        save_config(run_dir / "calibration.json", configs)

    trackers = [CamShiftPendulumTracker(first_frame, cfg) for cfg in configs]
    raw_writer, annotated_writer = open_writers(run_dir, first_frame.shape, args.fps)

    rows = []
    recording = False
    frame_idx = 0
    segment_start_tick = None
    recorded_time_s = 0.0
    preview_name = "magnetic Newton cradle recorder"
    if not args.no_preview:
        cv2.namedWindow(preview_name, cv2.WINDOW_NORMAL)

    print("Controls: r=start/stop recording, q=quit and save")
    print(f"Saving to: {run_dir}")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            now_tick = cv2.getTickCount()
            if args.no_preview:
                recording = True
                if segment_start_tick is None:
                    segment_start_tick = now_tick
            elif recording and segment_start_tick is None:
                segment_start_tick = now_tick

            time_s = recorded_time_s
            if recording and segment_start_tick is not None:
                time_s += (now_tick - segment_start_tick) / cv2.getTickFrequency()

            annotated = frame.copy()
            current_points = []
            for tracker in trackers:
                point = tracker.update(frame, frame_idx, time_s)
                current_points.append(point)
                tracker.draw(annotated, point)

            status = "REC" if recording else "READY"
            status_color = (0, 0, 255) if recording else (60, 220, 60)
            cv2.putText(
                annotated,
                f"{status}  t={time_s:.2f}s  r=start/stop  q=save/quit",
                (20, 34),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                status_color,
                2,
                cv2.LINE_AA,
            )

            if recording:
                raw_writer.write(frame)
                annotated_writer.write(annotated)
                rows.extend(current_points)
                frame_idx += 1
                if args.no_preview and args.duration is not None and time_s >= args.duration:
                    recorded_time_s = time_s
                    break

            if not args.no_preview:
                cv2.imshow(preview_name, annotated)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("r"):
                    if recording:
                        recorded_time_s = time_s
                        segment_start_tick = None
                        recording = False
                        print("Recording paused")
                    else:
                        recording = True
                        segment_start_tick = cv2.getTickCount()
                        print("Recording started")
                elif key in (ord("q"), 27):
                    if recording:
                        recorded_time_s = time_s
                    break

    finally:
        cap.release()
        raw_writer.release()
        annotated_writer.release()
        cv2.destroyAllWindows()

    long_csv, wide_csv = write_csvs(run_dir, rows, configs)
    plot_path = plot_angles(run_dir, rows)

    print(f"Raw video: {run_dir / 'raw_video.mp4'}")
    print(f"Annotated video: {run_dir / 'annotated_tracking.mp4'}")
    print(f"Long CSV: {long_csv}")
    print(f"Wide CSV: {wide_csv}")
    if plot_path:
        print(f"Angle plot: {plot_path}")


if __name__ == "__main__":
    main()
