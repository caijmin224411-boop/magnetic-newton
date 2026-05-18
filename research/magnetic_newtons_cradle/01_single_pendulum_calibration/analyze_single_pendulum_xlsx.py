import csv
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r"C:\Users\66\Desktop\niudundanbai.xlsx")
OUT_DIR = ROOT / "04_data_outputs" / "single_pendulum_calibration"
FIG_DIR = ROOT / "03_key_figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

G = 9.81
MASS_KG = 0.070


def font(size):
    for name in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/arial.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def load_tracker_xlsx(path):
    raw = pd.read_excel(path, sheet_name=0, header=None)
    header = 1
    df = pd.read_excel(path, sheet_name=0, header=header)
    df = df.apply(pd.to_numeric, errors="coerce")
    t = df["t"].to_numpy(float)
    x = df["x"].to_numpy(float)
    y = df["y"].to_numpy(float)
    mask = np.isfinite(t) & np.isfinite(x) & np.isfinite(y)
    t, x, y = t[mask], x[mask], y[mask]
    order = np.argsort(t)
    return t[order], x[order], y[order]


def circle_fit(x, y):
    # Algebraic least-squares circle fit: x^2 + y^2 + ax + by + c = 0.
    A = np.column_stack([x, y, np.ones_like(x)])
    b = -(x * x + y * y)
    a, bcoef, c = np.linalg.lstsq(A, b, rcond=None)[0]
    xc = -a / 2
    yc = -bcoef / 2
    r = math.sqrt(max(0.0, (a * a + bcoef * bcoef) / 4 - c))
    residual = np.sqrt((x - xc) ** 2 + (y - yc) ** 2) - r
    return xc, yc, r, residual


def uniform(t, data):
    dt = float(np.median(np.diff(t)))
    tu = np.arange(t[0], t[-1], dt)
    du = np.interp(tu, t, data)
    return tu - tu[0], du, 1.0 / dt


def spectrum(t, theta):
    dt = float(np.median(np.diff(t)))
    sig = theta - np.mean(theta)
    w = np.hanning(len(sig))
    freq = np.fft.rfftfreq(len(sig), dt)
    amp = 2 * np.abs(np.fft.rfft(sig * w)) / np.sum(w)
    return freq, amp


def dominant_peak(freq, amp, lo=0.1, hi=5.0):
    mask = (freq >= lo) & (freq <= hi)
    idx = np.where(mask)[0]
    local = []
    for i in idx:
        if i == 0 or i == len(freq) - 1:
            continue
        if amp[i] >= amp[i - 1] and amp[i] >= amp[i + 1]:
            local.append(i)
    if not local:
        local = list(idx)
    best = max(local, key=lambda i: amp[i])
    return float(freq[best]), float(amp[best])


def find_peaks(t, theta):
    sig = theta - np.mean(theta)
    peaks = []
    troughs = []
    for i in range(1, len(sig) - 1):
        if sig[i] >= sig[i - 1] and sig[i] >= sig[i + 1]:
            peaks.append((t[i], theta[i], abs(sig[i])))
        if sig[i] <= sig[i - 1] and sig[i] <= sig[i + 1]:
            troughs.append((t[i], theta[i], abs(sig[i])))
    return peaks, troughs


def fit_damping(extrema):
    data = np.array([(t, amp) for t, _theta, amp in extrema if amp > 1e-6], dtype=float)
    if len(data) < 8:
        return math.nan, math.nan, []
    # Ignore first few points if the release transient is unusually large, and
    # ignore tiny late-time extrema near the measurement noise floor.
    amp = data[:, 1]
    keep = amp > np.percentile(amp, 25)
    data = data[keep]
    if len(data) < 8:
        return math.nan, math.nan, data.tolist()
    slope, intercept = np.polyfit(data[:, 0], np.log(data[:, 1]), 1)
    beta = -float(slope)
    return beta, float(intercept), data.tolist()


def map_pt(x, y, box, xlim, ylim):
    l, t, r, b = box
    px = l + (x - xlim[0]) / (xlim[1] - xlim[0]) * (r - l)
    py = b - (y - ylim[0]) / (ylim[1] - ylim[0]) * (b - t)
    return int(px), int(py)


def plot_time_frequency(t, theta, freq, amp, peak_f, beta, path):
    img = Image.new("RGB", (1400, 820), (248, 247, 242))
    d = ImageDraw.Draw(img)
    title = font(26)
    small = font(15)
    d.text((70, 35), "Single pendulum calibration from Tracker data", fill=(30, 30, 30), font=title)
    box1 = (80, 110, 650, 690)
    box2 = (760, 110, 1320, 690)
    d.rectangle(box1, outline=(40, 40, 40))
    d.rectangle(box2, outline=(40, 40, 40))
    xlim1 = (0, min(30.0, float(t[-1])))
    mask1 = t <= xlim1[1]
    ylim1 = (float(np.percentile(theta[mask1], 1)) * 1.15, float(np.percentile(theta[mask1], 99)) * 1.15)
    for gx in np.linspace(xlim1[0], xlim1[1], 7):
        p = map_pt(gx, ylim1[0], box1, xlim1, ylim1)[0]
        d.line((p, box1[1], p, box1[3]), fill=(225, 222, 215))
        d.text((p - 15, box1[3] + 10), f"{gx:.0f}", fill=(80, 80, 80), font=small)
    pts = [map_pt(xv, yv, box1, xlim1, ylim1) for xv, yv in zip(t[mask1], theta[mask1])]
    d.line(pts, fill=(40, 112, 185), width=2)
    d.text((80, 78), "Angle time series", fill=(70, 70, 70), font=small)

    xlim2 = (0, 4.0)
    mask2 = freq <= xlim2[1]
    ylim2 = (0, float(np.max(amp[mask2])) * 1.15)
    for gx in np.linspace(0, 4, 5):
        p = map_pt(gx, 0, box2, xlim2, ylim2)[0]
        d.line((p, box2[1], p, box2[3]), fill=(225, 222, 215))
        d.text((p - 12, box2[3] + 10), f"{gx:.0f}", fill=(80, 80, 80), font=small)
    pts = [map_pt(xv, yv, box2, xlim2, ylim2) for xv, yv in zip(freq[mask2], amp[mask2])]
    d.line(pts, fill=(180, 76, 64), width=2)
    px = map_pt(peak_f, 0, box2, xlim2, ylim2)[0]
    d.line((px, box2[1], px, box2[3]), fill=(180, 76, 64), width=1)
    d.text((760, 78), "Frequency spectrum", fill=(70, 70, 70), font=small)
    d.text((930, 720), f"dominant f = {peak_f:.4f} Hz    beta = {beta:.5f} 1/s", fill=(40, 40, 40), font=small)
    img.save(path)


def main():
    t, x, y = load_tracker_xlsx(SOURCE)
    xc, yc, radius_tracker, residual = circle_fit(x, y)
    theta = np.unwrap(np.arctan2(x - xc, -(y - yc)))
    t_u, theta_u, fs = uniform(t, theta)
    freq, amp = spectrum(t_u, theta_u)
    peak_f, peak_amp = dominant_peak(freq, amp)
    period = 1.0 / peak_f
    length_from_frequency = G / (2 * math.pi * peak_f) ** 2
    peaks, troughs = find_peaks(t_u, theta_u)
    beta_p, intercept_p, used_peaks = fit_damping(peaks)
    beta_t, intercept_t, used_troughs = fit_damping(troughs)
    betas = [b for b in [beta_p, beta_t] if np.isfinite(b) and b > 0]
    beta = float(np.mean(betas)) if betas else math.nan
    damping_c = 2 * beta * MASS_KG * length_from_frequency ** 2 if np.isfinite(beta) else math.nan
    omega0 = 2 * math.pi * peak_f
    quality_factor = omega0 / (2 * beta) if np.isfinite(beta) and beta > 0 else math.nan

    theta_csv = OUT_DIR / "single_pendulum_theta.csv"
    with theta_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "theta_rad"])
        for row in zip(t_u, theta_u):
            w.writerow([f"{row[0]:.8f}", f"{row[1]:.10g}"])

    spectrum_csv = OUT_DIR / "single_pendulum_frequency_spectrum.csv"
    with spectrum_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["frequency_Hz", "amp_rad"])
        for row in zip(freq, amp):
            w.writerow([f"{row[0]:.8f}", f"{row[1]:.10g}"])

    fig = FIG_DIR / "single_pendulum_calibration_time_frequency.png"
    plot_time_frequency(t_u, theta_u, freq, amp, peak_f, beta, fig)

    summary = {
        "source": str(SOURCE),
        "sample_count": int(len(t)),
        "duration_s": float(t_u[-1]),
        "sample_rate_Hz": float(fs),
        "circle_center_tracker_units": [float(xc), float(yc)],
        "circle_radius_tracker_units": float(radius_tracker),
        "circle_residual_rms_tracker_units": float(np.sqrt(np.mean(residual ** 2))),
        "dominant_frequency_Hz": peak_f,
        "period_s": period,
        "length_from_frequency_m": length_from_frequency,
        "length_from_frequency_cm": length_from_frequency * 100,
        "beta_peak_1_per_s": beta_p,
        "beta_trough_1_per_s": beta_t,
        "beta_mean_1_per_s": beta,
        "mass_kg_for_damping": MASS_KG,
        "damping_torque_coefficient_N_m_s": damping_c,
        "quality_factor": quality_factor,
        "theta_csv": str(theta_csv),
        "spectrum_csv": str(spectrum_csv),
        "figure": str(fig),
    }
    (OUT_DIR / "single_pendulum_calibration_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
