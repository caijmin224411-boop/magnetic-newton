import csv
import math
import os
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parent
CASE_PREFIX = os.environ.get("MNC_CASE_PREFIX", "realfield_left_release")
FORCE_TABLE = ROOT / os.environ.get("MNC_FORCE_TABLE", "force_table_measured_70mT_disk_2d.csv")
OUTPUT_DIR = Path(os.environ.get("MNC_OUTPUT_DIR", str(ROOT)))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_TS = OUTPUT_DIR / f"{CASE_PREFIX}_time_domain.csv"
OUT_FFT = OUTPUT_DIR / f"{CASE_PREFIX}_frequency_spectrum.csv"
OUT_LYAP = OUTPUT_DIR / f"{CASE_PREFIX}_lyapunov.csv"
OUT_TIME_PNG = OUTPUT_DIR / f"{CASE_PREFIX}_time_domain.png"
OUT_FREQ_PNG = OUTPUT_DIR / f"{CASE_PREFIX}_frequency_spectrum.png"
OUT_LYAP_PNG = OUTPUT_DIR / f"{CASE_PREFIX}_lyapunov.png"
OUT_EQUILIBRIUM = OUTPUT_DIR / f"{CASE_PREFIX}_equilibrium.csv"

N = 5
g = 9.81
m = 0.050
L = np.array([0.132, 0.134, 0.135, 0.134, 0.132], dtype=float)
if "MNC_LENGTHS_M" in os.environ:
    L = np.array([float(v) for v in os.environ["MNC_LENGTHS_M"].split(",")], dtype=float)
    if len(L) != N:
        raise ValueError("MNC_LENGTHS_M must contain five comma-separated lengths in meters")
elif "MNC_LENGTH_M" in os.environ:
    L = np.full(N, float(os.environ["MNC_LENGTH_M"]), dtype=float)
m = float(os.environ.get("MNC_MASS_KG", m))
pivot_spacing = float(os.environ.get("MNC_PIVOT_SPACING_M", "0.030"))
pivot_x = (np.arange(1, N + 1) - (N + 1) / 2) * pivot_spacing
disk_radius = 0.015
damping = np.array([2.2, 2.0, 1.8, 2.0, 2.2]) * 1e-8
linear_damping = np.full(N, float(os.environ.get("MNC_DAMPING_C1_NMS", "0.0")), dtype=float)
quadratic_damping = np.full(N, float(os.environ.get("MNC_DAMPING_C2_NMS2", "0.0")), dtype=float)

# Physical near-contact boundary: the magnet faces cannot be mathematically zero distance apart.
# Replace this with a measured casing/air gap when available.
disk_radius = float(os.environ.get("MNC_DISK_RADIUS_M", disk_radius))
min_surface_gap = float(os.environ.get("MNC_MIN_GAP_M", "0.0015"))
mag_force_scale = float(os.environ.get("MNC_MAG_FORCE_SCALE", "1.0"))

dt = 1.0 / float(os.environ.get("MNC_SAMPLE_HZ", "720.0"))
duration = float(os.environ.get("MNC_DURATION_S", "20.0"))
steps = int(duration / dt)
sample_stride = 3
initial_delta = 1e-7
renorm_interval = 0.05
renorm_steps = max(1, int(renorm_interval / dt))


def read_force_table(path):
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append((float(row["gap_m"]), float(row["offset_m"]),
                         float(row["force_axial_N"]), float(row["force_lateral_N"])))
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


gaps, offsets, axial_table, lateral_table = read_force_table(FORCE_TABLE)


def interp2(gap, offset, table):
    gap = float(np.clip(gap, min_surface_gap, gaps[-1]))
    offset = float(np.clip(abs(offset), offsets[0], offsets[-1]))
    i = int(np.clip(np.searchsorted(gaps, gap) - 1, 0, len(gaps) - 2))
    j = int(np.clip(np.searchsorted(offsets, offset) - 1, 0, len(offsets) - 2))
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
    a = np.zeros(N)
    for i in range(N):
        rx = x[i] - pivot_x[i]
        ry = y[i]
        if os.environ.get("MNC_USE_NONLINEAR_DAMPING", "0") == "1":
            tau = (-m * g * L[i] * math.sin(theta[i])
                   - linear_damping[i] * omega[i]
                   - quadratic_damping[i] * omega[i] * abs(omega[i]))
        else:
            tau = -m * g * L[i] * math.sin(theta[i]) - damping[i] * omega[i]
        for j in (i - 1, i + 1):
            if j < 0 or j >= N:
                continue
            dx = x[i] - x[j]
            dy = y[i] - y[j]
            gap = abs(dx) - 2 * disk_radius
            fax = abs(interp2(gap, abs(dy), axial_table))
            flat = abs(interp2(gap, abs(dy), lateral_table))
            fx = mag_force_scale * (math.copysign(fax, dx) if abs(dx) > 1e-12 else 0.0)
            fy = mag_force_scale * (math.copysign(flat, dy) if abs(dy) > 1e-12 else 0.0)
            tau += rx * fy - ry * fx
        a[i] = tau / (m * L[i] ** 2)
    return a


def rhs(state):
    return np.r_[state[N:], acceleration(state[:N], state[N:])]


def rk4_step(state):
    k1 = rhs(state)
    k2 = rhs(state + 0.5 * dt * k1)
    k3 = rhs(state + 0.5 * dt * k2)
    k4 = rhs(state + dt * k3)
    return state + dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6


def equilibrium_objective(theta):
    tau_accel = acceleration(theta, np.zeros(N))
    symmetry_penalty = 0.0
    for i in range(N):
        symmetry_penalty += (theta[i] + theta[N - 1 - i]) ** 2
    return float(np.sum(tau_accel ** 2) + 0.05 * symmetry_penalty)


def solve_equilibrium():
    theta = np.array([float(v) for v in os.environ.get("MNC_EQUILIBRIUM_GUESS", "-0.6,-0.3,0,0.3,0.6").split(",")], dtype=float)
    step_size = float(os.environ.get("MNC_EQUILIBRIUM_STEP", "0.10"))
    lower = float(os.environ.get("MNC_EQUILIBRIUM_MIN", "-1.25"))
    upper = float(os.environ.get("MNC_EQUILIBRIUM_MAX", "1.25"))
    best = equilibrium_objective(theta)
    for _ in range(4500):
        improved = False
        for i in range(N):
            for direction in (-1.0, 1.0):
                candidate = theta.copy()
                candidate[i] = np.clip(candidate[i] + direction * step_size, lower, upper)
                value = equilibrium_objective(candidate)
                if value < best:
                    theta, best = candidate, value
                    improved = True
        if not improved:
            step_size *= 0.72
            if step_size < 2e-6:
                break
    # Enforce mirror symmetry after optimization; the apparatus and parameters are symmetric.
    theta = 0.5 * (theta - theta[::-1])
    with OUT_EQUILIBRIUM.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["bob", "theta_equilibrium_rad", "theta_equilibrium_deg", "residual_accel_rad_s2"])
        residual = acceleration(theta, np.zeros(N))
        for i in range(N):
            w.writerow([i + 1, f"{theta[i]:.10g}", f"{math.degrees(theta[i]):.10g}", f"{residual[i]:.10g}"])
    return theta


def initial_state():
    if os.environ.get("MNC_USE_SOLVED_EQUILIBRIUM", "1") == "1":
        theta = solve_equilibrium()
    else:
        theta_default = "-0.62,-0.30,0.0,0.30,0.62"
        theta = np.array([float(v) for v in os.environ.get("MNC_INITIAL_THETA", theta_default).split(",")], dtype=float)
    release_index = int(os.environ.get("MNC_RELEASE_INDEX", "0"))
    release_delta = float(os.environ.get("MNC_RELEASE_DELTA_RAD", "-0.38"))
    theta[release_index] += release_delta
    return np.r_[theta, np.zeros(N)]


def simulate_time_series():
    state = initial_state()
    rows = []
    for k in range(steps):
        if k % sample_stride == 0:
            rows.append((k * dt, *state))
        state = rk4_step(state)
    data = np.array(rows)
    return data[:, 0], data[:, 1:1 + N], data[:, 1 + N:]


def spectrum(theta, sample_rate):
    sig = theta - np.mean(theta, axis=0, keepdims=True)
    window = np.hanning(sig.shape[0])[:, None]
    fft = np.fft.rfft(sig * window, axis=0)
    freq = np.fft.rfftfreq(sig.shape[0], d=1.0 / sample_rate)
    amp = 2 * np.abs(fft) / np.sum(window)
    return freq, amp


def write_tables(time, theta, omega, freq, amp):
    with OUT_TS.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t_s", *[f"theta{i}" for i in range(1, N + 1)], *[f"omega{i}" for i in range(1, N + 1)]])
        for k, t in enumerate(time):
            w.writerow([f"{t:.8f}", *[f"{v:.10g}" for v in theta[k]], *[f"{v:.10g}" for v in omega[k]]])
    with OUT_FFT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["frequency_Hz", *[f"amp_theta{i}_rad" for i in range(1, N + 1)]])
        for k, fr in enumerate(freq):
            w.writerow([f"{fr:.8f}", *[f"{v:.10g}" for v in amp[k]]])


def lyapunov():
    base = initial_state()
    perturbed = base.copy()
    perturbed[0] += initial_delta
    times, running, window_logs = [], [], []
    sum_logs = 0.0
    for k in range(1, steps + 1):
        base = rk4_step(base)
        perturbed = rk4_step(perturbed)
        if k % renorm_steps == 0:
            delta = perturbed - base
            dist = max(float(np.linalg.norm(delta)), 1e-15)
            growth = math.log(dist / initial_delta)
            sum_logs += growth
            t = k * dt
            times.append(t)
            window_logs.append(growth)
            running.append(sum_logs / t)
            perturbed = base + delta / dist * initial_delta
    times = np.array(times)
    running = np.array(running)
    window_logs = np.array(window_logs)
    cumulative = np.cumsum(window_logs)
    mask = (times >= 3.0) & (times <= duration * 0.85)
    lambda_fit = float(np.polyfit(times[mask], cumulative[mask], 1)[0])
    with OUT_LYAP.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time_s", "lambda_running_1_per_s", "log_growth_window"])
        for row in zip(times, running, window_logs):
            w.writerow([f"{row[0]:.8f}", f"{row[1]:.10e}", f"{row[2]:.10e}"])
    return times, running, lambda_fit


def plot_lines(path, x, ys, xlim, ylim, title, xlabel, ylabel):
    width, height = 1280, 760
    img = np.full((height, width, 3), (248, 247, 242), dtype=np.uint8)
    left, top, right, bottom = 105, 90, 1215, 645
    cv2.rectangle(img, (left, top), (right, bottom), (30, 30, 30), 1)
    cv2.putText(img, title, (left, top - 22), cv2.FONT_HERSHEY_SIMPLEX, 0.74, (30, 30, 30), 2, cv2.LINE_AA)
    colors = [(214, 72, 60), (40, 112, 185), (48, 150, 102), (222, 154, 40), (110, 80, 165)]
    for gx in np.linspace(xlim[0], xlim[1], 7):
        px = int(left + (gx - xlim[0]) / (xlim[1] - xlim[0]) * (right - left))
        cv2.line(img, (px, top), (px, bottom), (225, 222, 215), 1)
        cv2.putText(img, f"{gx:g}", (px - 16, bottom + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (80, 80, 80), 1, cv2.LINE_AA)
    for gy in np.linspace(ylim[0], ylim[1], 7):
        py = int(bottom - (gy - ylim[0]) / (ylim[1] - ylim[0]) * (bottom - top))
        cv2.line(img, (left, py), (right, py), (225, 222, 215), 1)
        cv2.putText(img, f"{gy:.2g}", (28, py + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (80, 80, 80), 1, cv2.LINE_AA)
    mask = (x >= xlim[0]) & (x <= xlim[1])
    for i in range(ys.shape[1]):
        pts = []
        for xv, yv in zip(x[mask], ys[mask, i]):
            px = int(left + (xv - xlim[0]) / (xlim[1] - xlim[0]) * (right - left))
            py = int(bottom - (yv - ylim[0]) / (ylim[1] - ylim[0]) * (bottom - top))
            pts.append((px, py))
        cv2.polylines(img, [np.array(pts, dtype=np.int32)], False, colors[i], 2, cv2.LINE_AA)
        cv2.putText(img, f"bob {i + 1}", (970, 112 + i * 30), cv2.FONT_HERSHEY_SIMPLEX, 0.48, colors[i], 1, cv2.LINE_AA)
    cv2.putText(img, xlabel, ((left + right) // 2 - 45, bottom + 48), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (60, 60, 60), 1, cv2.LINE_AA)
    cv2.putText(img, ylabel, (left - 82, top + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.43, (60, 60, 60), 1, cv2.LINE_AA)
    cv2.imwrite(str(path), img)


time, theta, omega = simulate_time_series()
freq, amp = spectrum(theta, sample_rate=1.0 / (dt * sample_stride))
write_tables(time, theta, omega, freq, amp)

if os.environ.get("MNC_SKIP_PLOTS", "0") != "1":
    plot_lines(OUT_TIME_PNG, time, theta, (0, duration), (np.min(theta) * 1.1, np.max(theta) * 1.1),
               "Real-field model: time-domain angular displacement", "time / s", "theta / rad")
    freq_mask = freq <= 10.0
    plot_lines(OUT_FREQ_PNG, freq, amp, (0, 10.0), (0, np.max(amp[freq_mask]) * 1.15),
               "Real-field model: frequency spectrum", "frequency / Hz", "FFT amplitude / rad")
lambda_fit = None
if os.environ.get("MNC_SKIP_LYAPUNOV", "0") != "1":
    lyap_t, lyap_running, lambda_fit = lyapunov()
    if os.environ.get("MNC_SKIP_PLOTS", "0") != "1":
        plot_lines(OUT_LYAP_PNG, lyap_t, lyap_running[:, None], (0, duration),
                   (min(-0.5, np.min(lyap_running) * 1.1), max(0.5, np.max(lyap_running) * 1.1)),
                   f"Real-field model: Lyapunov estimate, lambda_fit={lambda_fit:.3f} 1/s",
                   "time / s", "lambda / 1/s")

print(f"min_surface_gap_m={min_surface_gap}")
if lambda_fit is not None:
    print(f"lambda_fit_1_per_s={lambda_fit:.8f}")
else:
    print("lambda_fit_1_per_s=skipped")
for i in range(N):
    valid = (freq > 0.05) & (freq < 10.0)
    f_valid = freq[valid]
    a_valid = amp[valid, i]
    peak_idx = np.argsort(a_valid)[-3:][::-1]
    print(f"bob {i + 1}: " + ", ".join(f"{f_valid[p]:.3f} Hz ({a_valid[p]:.4f} rad)" for p in peak_idx))
print(OUT_TIME_PNG)
print(OUT_FREQ_PNG)
if lambda_fit is not None:
    print(OUT_LYAP_PNG)
