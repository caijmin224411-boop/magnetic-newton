from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "paper_like_magnetic_pendulum_basin.png"
OUT_SHIFT = ROOT / "paper_like_magnetic_pendulum_basin_shifted.png"


def simulate_basin(magnet_shift=0.0, n=360, extent=2.0, dt=0.018, steps=3600):
    # Dimensionless model following the cited magnetic-pendulum paper:
    # x'' + alpha x' - sum_j (x_j - x)/r_j^3 + K x = 0
    # y'' + alpha y' - sum_j (y_j - y)/r_j^3 + K y = 0
    alpha = 0.20
    k = 0.50
    d = 0.25
    side_radius = 1.0
    magnets = np.array(
        [
            [0.0, side_radius],
            [-np.sqrt(3) / 2 * side_radius, -0.5 * side_radius],
            [np.sqrt(3) / 2 * side_radius, -0.5 * side_radius],
        ],
        dtype=np.float32,
    )
    magnets[:, 0] += magnet_shift

    xs = np.linspace(-extent, extent, n, dtype=np.float32)
    ys = np.linspace(extent, -extent, n, dtype=np.float32)
    x, y = np.meshgrid(xs, ys)
    vx = np.zeros_like(x)
    vy = np.zeros_like(y)

    d2 = np.float32(d * d)
    for _ in range(steps):
        ax = -alpha * vx - k * x
        ay = -alpha * vy - k * y
        for mx, my in magnets:
            dx = mx - x
            dy = my - y
            r2 = dx * dx + dy * dy + d2
            inv_r3 = 1.0 / (r2 * np.sqrt(r2))
            ax += dx * inv_r3
            ay += dy * inv_r3
        vx += dt * ax
        vy += dt * ay
        x += dt * vx
        y += dt * vy

    dist = np.stack([(x - mx) ** 2 + (y - my) ** 2 for mx, my in magnets], axis=0)
    label = np.argmin(dist, axis=0).astype(np.uint8)
    speed = np.sqrt(vx * vx + vy * vy)
    return label, speed, magnets


def draw_basin(label, speed, magnets, out_path, title):
    colors = np.array(
        [
            [226, 72, 58],
            [46, 124, 196],
            [56, 154, 104],
        ],
        dtype=np.uint8,
    )
    img = colors[label]

    # Darken slow/settled points slightly less; unresolved high-speed points become pale.
    unresolved = speed > np.percentile(speed, 96)
    img[unresolved] = (0.65 * img[unresolved] + 0.35 * np.array([245, 241, 230])).astype(np.uint8)

    # Highlight fractal basin boundaries.
    boundary = np.zeros(label.shape, dtype=bool)
    boundary[:-1, :] |= label[:-1, :] != label[1:, :]
    boundary[:, :-1] |= label[:, :-1] != label[:, 1:]
    img[boundary] = np.array([20, 24, 28], dtype=np.uint8)

    h, w = img.shape[:2]
    canvas = np.full((h + 90, w + 30, 3), (246, 243, 235), dtype=np.uint8)
    canvas[70 : 70 + h, 15 : 15 + w] = img

    cv2.putText(canvas, title, (18, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (25, 31, 38), 2, cv2.LINE_AA)
    cv2.putText(
        canvas,
        "initial velocity = 0; color = final attractor; black = basin boundary",
        (18, 58),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (70, 78, 86),
        1,
        cv2.LINE_AA,
    )

    # Map magnet coordinates to image pixels.
    extent = 2.0
    for i, (mx, my) in enumerate(magnets):
        px = int(15 + (mx + extent) / (2 * extent) * (w - 1))
        py = int(70 + (extent - my) / (2 * extent) * (h - 1))
        cv2.circle(canvas, (px, py), 8, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(canvas, (px, py), 8, (25, 31, 38), 2, cv2.LINE_AA)
        cv2.putText(canvas, "ABC"[i], (px + 10, py - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (25, 31, 38), 2, cv2.LINE_AA)

    cv2.imwrite(str(out_path), canvas)


def main():
    label, speed, magnets = simulate_basin(magnet_shift=0.0)
    draw_basin(label, speed, magnets, OUT, "Fractal basin of attraction: symmetric three-magnet pendulum")
    label2, speed2, magnets2 = simulate_basin(magnet_shift=0.28)
    draw_basin(label2, speed2, magnets2, OUT_SHIFT, "Basin deformation when magnet triangle shifts right")
    print(OUT)
    print(OUT_SHIFT)


if __name__ == "__main__":
    main()
