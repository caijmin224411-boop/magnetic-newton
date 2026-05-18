import csv
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parent
FORCE_TABLE = ROOT / "force_table_5cm_220mT_disk_2d.csv"
EQUILIBRIUM = ROOT / "realfield_4cm_220mT_solved_eq_left_release_equilibrium.csv"
OUT = ROOT / "cradle_initial_condition_response_map.png"

N = 5
g = 9.81
m = 0.070
L = np.array([0.132, 0.134, 0.135, 0.134, 0.132], dtype=np.float64)
pivot_spacing = 0.040
pivot_x = (np.arange(1, N + 1) - (N + 1) / 2) * pivot_spacing
disk_radius = 0.015
min_gap = 0.002
damping = np.array([2.2, 2.0, 1.8, 2.0, 2.2]) * 1e-8


def read_force_table():
    rows = []
    with FORCE_TABLE.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append((float(row["gap_m"]), float(row["offset_m"]),
                         abs(float(row["force_axial_N"])), abs(float(row["force_lateral_N"]))))
    gaps = sorted({r[0] for r in rows})
    offsets = sorted({r[1] for r in rows})
    axial = np.zeros((len(gaps), len(offsets)))
    lateral = np.zeros_like(axial)
    gi = {v: i for i, v in enumerate(gaps)}
    oi = {v: i for i, v in enumerate(offsets)}
    for gap, offset, fax, flat in rows:
        axial[gi[gap], oi[offset]] = fax
        lateral[gi[gap], oi[offset]] = flat
    return np.array(gaps), np.array(offsets), axial, lateral


def read_equilibrium():
    vals = []
    with EQUILIBRIUM.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            vals.append(float(row["theta_equilibrium_rad"]))
    return np.array(vals)


gaps, offsets, axial_table, lateral_table = read_force_table()
theta_eq = read_equilibrium()


def interp2(gap, offset, table):
    gap = np.clip(gap, min_gap, gaps[-1])
    offset = np.clip(np.abs(offset), offsets[0], offsets[-1])
    i = np.clip(np.searchsorted(gaps, gap) - 1, 0, len(gaps) - 2)
    j = np.clip(np.searchsorted(offsets, offset) - 1, 0, len(offsets) - 2)
    gx = (gap - gaps[i]) / (gaps[i + 1] - gaps[i])
    oy = (offset - offsets[j]) / (offsets[j + 1] - offsets[j])
    return ((1 - gx) * (1 - oy) * table[i, j]
            + gx * (1 - oy) * table[i + 1, j]
            + (1 - gx) * oy * table[i, j + 1]
            + gx * oy * table[i + 1, j + 1])


def centers(theta):
    return pivot_x + np.sin(theta) * L, -np.cos(theta) * L


def acceleration(theta, omega):
    x, y = centers(theta)
    a = np.zeros_like(theta)
    for i in range(N):
        rx = x[..., i] - pivot_x[i]
        ry = y[..., i]
        tau = -m * g * L[i] * np.sin(theta[..., i]) - damping[i] * omega[..., i]
        for j in (i - 1, i + 1):
            if j < 0 or j >= N:
                continue
            dx = x[..., i] - x[..., j]
            dy = y[..., i] - y[..., j]
            gap = np.abs(dx) - 2 * disk_radius
            fax = interp2(gap, np.abs(dy), axial_table)
            flat = interp2(gap, np.abs(dy), lateral_table)
            fx = np.sign(dx) * fax
            fy = np.sign(dy) * flat
            tau = tau + rx * fy - ry * fx
        a[..., i] = tau / (m * L[i] ** 2)
    return a


def main():
    # This is a two-dimensional section through the full 10D phase space:
    # x-axis: additional left-bob release angle; y-axis: initial angular velocity of left bob.
    nx, ny = 150, 120
    release_deg = np.linspace(0, 80, nx)
    omega0 = np.linspace(-4.0, 4.0, ny)
    rel, omg = np.meshgrid(np.deg2rad(release_deg), omega0)

    theta = np.zeros((ny, nx, N), dtype=np.float64) + theta_eq
    omega = np.zeros_like(theta)
    theta[..., 0] = theta_eq[0] - rel
    omega[..., 0] = omg

    peak = np.abs(theta - theta_eq)
    dt = 0.006
    steps = int(10.0 / dt)
    for _ in range(steps):
        omega += acceleration(theta, omega) * dt
        theta += omega * dt
        peak = np.maximum(peak, np.abs(theta - theta_eq))

    dominant = np.argmax(peak, axis=2).astype(np.uint8)
    strength = np.max(peak, axis=2)
    strength_norm = np.clip(strength / np.percentile(strength, 96), 0, 1)

    colors = np.array([
        [210, 68, 55],
        [46, 112, 185],
        [48, 150, 102],
        [220, 154, 40],
        [112, 82, 166],
    ], dtype=np.float64)
    img = colors[dominant]
    img = (0.45 * img + 0.55 * img * strength_norm[..., None] + 245 * (1 - strength_norm[..., None]) * 0.22)
    img = np.clip(img, 0, 255).astype(np.uint8)

    boundary = np.zeros((ny, nx), dtype=bool)
    boundary[:-1, :] |= dominant[:-1, :] != dominant[1:, :]
    boundary[:, :-1] |= dominant[:, :-1] != dominant[:, 1:]
    img[boundary] = [20, 24, 28]

    scale = 4
    field = cv2.resize(img, (nx * scale, ny * scale), interpolation=cv2.INTER_NEAREST)
    h, w = field.shape[:2]
    canvas = np.full((h + 120, w + 70, 3), (246, 243, 235), dtype=np.uint8)
    canvas[70:70 + h, 50:50 + w] = field

    cv2.putText(canvas, "Magnetic Newton cradle: initial-condition response section", (28, 32),
                cv2.FONT_HERSHEY_SIMPLEX, 0.72, (25, 31, 38), 2, cv2.LINE_AA)
    cv2.putText(canvas, "color = bob with largest peak angle over first 10 s; black = switching boundary",
                (28, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.43, (70, 78, 86), 1, cv2.LINE_AA)
    cv2.putText(canvas, "release angle of left bob / deg", (w // 2 - 60, h + 108),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (45, 52, 60), 1, cv2.LINE_AA)
    cv2.putText(canvas, "initial omega / rad/s", (4, 92),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (45, 52, 60), 1, cv2.LINE_AA)

    for val in [0, 20, 40, 60, 80]:
        x = int(50 + val / 80 * (w - 1))
        cv2.line(canvas, (x, 70 + h), (x, 70 + h + 5), (40, 40, 40), 1)
        cv2.putText(canvas, str(val), (x - 10, 70 + h + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (45, 52, 60), 1, cv2.LINE_AA)
    for val in [-4, -2, 0, 2, 4]:
        y = int(70 + (4 - val) / 8 * (h - 1))
        cv2.line(canvas, (45, y), (50, y), (40, 40, 40), 1)
        cv2.putText(canvas, str(val), (18, y + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (45, 52, 60), 1, cv2.LINE_AA)

    for i, col in enumerate(colors.astype(np.uint8)):
        x0 = 50 + i * 92
        y0 = h + 72
        cv2.rectangle(canvas, (x0, y0), (x0 + 18, y0 + 18), tuple(int(c) for c in col.tolist()), -1)
        cv2.putText(canvas, f"bob {i+1}", (x0 + 24, y0 + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (45, 52, 60), 1, cv2.LINE_AA)

    cv2.imwrite(str(OUT), canvas)
    print(OUT)


if __name__ == "__main__":
    main()
