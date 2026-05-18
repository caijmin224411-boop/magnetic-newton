import csv
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from scipy.signal import savgol_filter, find_peaks, correlate


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "06_sources" / "new_swing_bobs_1_2_3_5.xlsx"
OUT_DIR = ROOT / "04_data_outputs" / "time_domain_bobs_1_2_3_5"
FIG_DIR = ROOT / "03_key_figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

BOB_LABELS = ["bob1", "bob2", "bob3", "bob5"]
TRACK_STARTS = [0, 6, 12, 24]
L_EFF = 0.11878
G = 9.81


def font(size):
    for name in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/arial.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def load_tracks():
    df = pd.read_excel(SOURCE, sheet_name="Sheet1", header=1)
    num = df.apply(pd.to_numeric, errors="coerce")
    tracks = []
    for label, start in zip(BOB_LABELS, TRACK_STARTS):
        cols = num.columns[start:start + 3]
        block = num.loc[:, cols].copy()
        block.columns = ["t", "x", "y"]
        block = block.dropna(how="any")
        t = block["t"].to_numpy(float)
        x = block["x"].to_numpy(float)
        y = block["y"].to_numpy(float)
        order = np.argsort(t)
        tracks.append({"label": label, "t": t[order], "x": x[order], "y": y[order]})
    return tracks


def clean_track(track):
    t, x, y = track["t"], track["x"], track["y"]
    t, idx = np.unique(t, return_index=True)
    x, y = x[idx], y[idx]
    x0 = np.nanmedian(x)
    y0 = np.nanmedian(y)
    radius = np.nanpercentile(np.sqrt((x - x0) ** 2 + (y - y0) ** 2), 95)
    if not np.isfinite(radius) or radius < 1e-9:
        radius = max(np.nanstd(x) * 3, 1.0)
    # Use normalized horizontal displacement as the time-domain coordinate.
    # For these videos it is more robust than arcsin(...): large arcs and
    # perspective error can otherwise create artificial clipping.
    theta = (x - x0) / radius
    diff = np.diff(theta, prepend=theta[0])
    med = np.median(diff)
    mad = np.median(np.abs(diff - med)) + 1e-12
    spike = np.abs(diff - med) > 12 * 1.4826 * mad
    if spike.any():
        good = ~spike
        theta[spike] = np.interp(t[spike], t[good], theta[good])
    dt = float(np.median(np.diff(t)))
    win = max(7, int(round(0.12 / dt)) | 1)
    if win < len(theta):
        theta = savgol_filter(theta, win, 3)
    return {**track, "t": t, "theta": theta, "radius_proxy": float(radius), "spike_count": int(spike.sum())}


def common_time(cleaned):
    start = max(float(c["t"][0]) for c in cleaned)
    end = min(float(c["t"][-1]) for c in cleaned)
    dt = float(np.median([np.median(np.diff(c["t"])) for c in cleaned]))
    t = np.arange(start, end, dt)
    theta = np.column_stack([np.interp(t, c["t"], c["theta"]) for c in cleaned])
    theta = theta - np.mean(theta[-min(500, len(theta)):, :], axis=0, keepdims=True)
    return t - t[0], theta, 1.0 / dt


def spectrum(t, theta):
    dt = float(np.median(np.diff(t)))
    sig = theta - np.mean(theta, axis=0, keepdims=True)
    w = np.hanning(len(sig))[:, None]
    freq = np.fft.rfftfreq(len(sig), dt)
    amp = 2 * np.abs(np.fft.rfft(sig * w, axis=0)) / np.sum(w)
    return freq, amp


def dominant_peaks(freq, amp, lo=0.1, hi=8.0, n=5):
    out = {}
    mask = (freq >= lo) & (freq <= hi)
    fv = freq[mask]
    for i, label in enumerate(BOB_LABELS):
        av = amp[mask, i]
        idx = np.argsort(av)[-n:][::-1]
        out[label] = [{"f_Hz": float(fv[j]), "amp_rad": float(av[j])} for j in idx]
    return out


def moving_rms(t, theta, window_s=1.0):
    dt = float(np.median(np.diff(t)))
    n = max(3, int(round(window_s / dt)))
    kernel = np.ones(n) / n
    return np.column_stack([np.sqrt(np.convolve(theta[:, i] ** 2, kernel, mode="same")) for i in range(theta.shape[1])])


def response_metrics(t, theta):
    rms = moving_rms(t, theta, 1.0)
    max_rms = rms.max(axis=0)
    t_max = np.array([t[np.argmax(rms[:, i])] for i in range(rms.shape[1])])
    threshold_metrics = []
    for i, label in enumerate(BOB_LABELS):
        th = max(0.15 * max_rms[i], np.percentile(rms[:, i], 80) * 0.35)
        idx = np.where(rms[:, i] >= th)[0]
        threshold_metrics.append({
            "label": label,
            "threshold_rms_rad": float(th),
            "first_response_time_s": float(t[idx[0]]) if len(idx) else None,
            "max_rms_rad": float(max_rms[i]),
            "time_of_max_rms_s": float(t_max[i]),
        })
    return rms, threshold_metrics


def peak_interval_metrics(t, theta):
    out = []
    dt = float(np.median(np.diff(t)))
    min_dist = max(3, int(round(0.25 / dt)))
    for i, label in enumerate(BOB_LABELS):
        sig = theta[:, i] - np.mean(theta[:, i])
        idx, props = find_peaks(np.abs(sig), distance=min_dist, prominence=max(0.02, np.std(sig) * 0.25))
        times = t[idx]
        intervals = np.diff(times)
        out.append({
            "label": label,
            "peak_count_abs": int(len(idx)),
            "mean_peak_interval_s": float(np.mean(intervals)) if len(intervals) else None,
            "std_peak_interval_s": float(np.std(intervals)) if len(intervals) else None,
            "cv_peak_interval": float(np.std(intervals) / np.mean(intervals)) if len(intervals) and np.mean(intervals) > 0 else None,
        })
    return out


def autocorr_metrics(t, theta):
    out = []
    dt = float(np.median(np.diff(t)))
    max_lag_s = 20.0
    max_lag = min(int(max_lag_s / dt), len(t) // 2)
    for i, label in enumerate(BOB_LABELS):
        sig = theta[:, i] - np.mean(theta[:, i])
        ac = np.correlate(sig, sig, mode="full")[len(sig) - 1:len(sig) - 1 + max_lag]
        ac = ac / (ac[0] + 1e-12)
        below = np.where(np.abs(ac) < 1 / math.e)[0]
        out.append({
            "label": label,
            "autocorr_1e_decay_time_s": float(below[0] * dt) if len(below) else None,
            "autocorr_abs_at_10s": float(abs(ac[min(int(10 / dt), len(ac) - 1)])),
        })
    return out


def lag_metrics(t, theta):
    out = []
    dt = float(np.median(np.diff(t)))
    ref = theta[:, 0] - np.mean(theta[:, 0])
    max_lag = int(round(3.0 / dt))
    for i, label in enumerate(BOB_LABELS[1:], start=1):
        sig = theta[:, i] - np.mean(theta[:, i])
        c = correlate(sig, ref, mode="full")
        lags = np.arange(-len(ref) + 1, len(ref))
        mask = np.abs(lags) <= max_lag
        j = np.argmax(np.abs(c[mask]))
        lag_samples = lags[mask][j]
        norm = np.linalg.norm(sig) * np.linalg.norm(ref) + 1e-12
        out.append({
            "pair": f"bob1_to_{label}",
            "best_lag_s_positive_means_target_after_bob1": float(lag_samples * dt),
            "max_abs_crosscorr": float(c[mask][j] / norm),
        })
    return out


def energy_proxy(t, theta):
    dt = float(np.median(np.diff(t)))
    omega = np.gradient(theta, dt, axis=0)
    # Mechanical-energy proxy without magnetic potential. Good for transfer timing, not absolute energy.
    e = 0.5 * (L_EFF ** 2) * omega ** 2 + G * L_EFF * (1 - np.cos(theta))
    frac = e / (np.sum(e, axis=1, keepdims=True) + 1e-12)
    return e, frac


def map_pt(x, y, box, xlim, ylim):
    l, t, r, b = box
    return (
        int(l + (x - xlim[0]) / (xlim[1] - xlim[0]) * (r - l)),
        int(b - (y - ylim[0]) / (ylim[1] - ylim[0]) * (b - t)),
    )


def plot_summary(t, theta, rms, frac, freq, amp, out):
    img = Image.new("RGB", (1600, 1100), (248, 247, 242))
    d = ImageDraw.Draw(img)
    d.text((70, 35), "Time-domain analysis: bobs 1, 2, 3, and 5", fill=(30, 30, 30), font=font(28))
    colors = [(214, 72, 60), (40, 112, 185), (48, 150, 102), (110, 80, 165)]
    boxes = [(80, 115, 735, 445), (850, 115, 1510, 445), (80, 585, 735, 915), (850, 585, 1510, 915)]
    titles = ["Cleaned angle time series", "1 s moving RMS envelope", "Energy proxy fraction", "Frequency spectrum"]
    for box, title in zip(boxes, titles):
        d.rectangle(box, outline=(40, 40, 40))
        d.text((box[0], box[1] - 28), title, fill=(70, 70, 70), font=font(15))

    xmax = min(25.0, float(t[-1]))
    mask = t <= xmax
    ylim = (float(np.percentile(theta[mask], 1)) * 1.1, float(np.percentile(theta[mask], 99)) * 1.1)
    for i in range(theta.shape[1]):
        pts = [map_pt(x, y, boxes[0], (0, xmax), ylim) for x, y in zip(t[mask], theta[mask, i])]
        d.line(pts, fill=colors[i], width=2)
    ylim_r = (0, float(np.percentile(rms[mask], 99)) * 1.15)
    for i in range(theta.shape[1]):
        pts = [map_pt(x, y, boxes[1], (0, xmax), ylim_r) for x, y in zip(t[mask], rms[mask, i])]
        d.line(pts, fill=colors[i], width=2)
    for i in range(theta.shape[1]):
        pts = [map_pt(x, y, boxes[2], (0, xmax), (0, 1)) for x, y in zip(t[mask], frac[mask, i])]
        d.line(pts, fill=colors[i], width=2)
    fmask = freq <= 6
    ymax = float(np.max(amp[fmask])) * 1.1
    for i in range(theta.shape[1]):
        pts = [map_pt(x, y, boxes[3], (0, 6), (0, ymax)) for x, y in zip(freq[fmask], amp[fmask, i])]
        d.line(pts, fill=colors[i], width=2)
    for i, label in enumerate(BOB_LABELS):
        d.rectangle((1180, 955 + 28 * i, 1200, 970 + 28 * i), fill=colors[i])
        d.text((1210, 950 + 28 * i), label, fill=(50, 50, 50), font=font(15))
    img.save(out)


def save_csv(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main():
    cleaned = [clean_track(t) for t in load_tracks()]
    t, theta, fs = common_time(cleaned)
    freq, amp = spectrum(t, theta)
    rms, response = response_metrics(t, theta)
    peaks = peak_interval_metrics(t, theta)
    autocorr = autocorr_metrics(t, theta)
    lags = lag_metrics(t, theta)
    e, frac = energy_proxy(t, theta)

    clean_csv = OUT_DIR / "bobs_1_2_3_5_cleaned_horizontal_proxy.csv"
    save_csv(clean_csv, ["t_s", *[f"{b}_horizontal_proxy" for b in BOB_LABELS]],
             [[f"{t[i]:.8f}", *[f"{v:.10g}" for v in theta[i]]] for i in range(len(t))])
    frac_csv = OUT_DIR / "bobs_1_2_3_5_energy_proxy_fraction.csv"
    save_csv(frac_csv, ["t_s", *[f"{b}_energy_proxy_fraction" for b in BOB_LABELS]],
             [[f"{t[i]:.8f}", *[f"{v:.10g}" for v in frac[i]]] for i in range(len(t))])
    fig = FIG_DIR / "time_domain_bobs_1_2_3_5_analysis.png"
    plot_summary(t, theta, rms, frac, freq, amp, fig)

    summary = {
        "source": str(SOURCE),
        "tracked_bobs": BOB_LABELS,
        "duration_s": float(t[-1]),
        "sample_rate_Hz": float(fs),
        "cleaning": [
            {
                "label": c["label"],
                "samples": int(len(c["t"])),
                "radius_proxy_tracker_units": c["radius_proxy"],
                "spike_count": c["spike_count"],
                "theta_min_rad": float(np.min(c["theta"])),
                "theta_max_rad": float(np.max(c["theta"])),
            }
            for c in cleaned
        ],
        "dominant_frequency_peaks": dominant_peaks(freq, amp),
        "response_metrics": response,
        "peak_interval_metrics": peaks,
        "autocorrelation_metrics": autocorr,
        "cross_correlation_lags": lags,
        "time_domain_interpretation": {
            "main_points": [
                "Use moving RMS envelope to identify response order and energy transfer timing.",
                "Use peak-interval CV to quantify time-domain irregularity.",
                "Use autocorrelation decay to quantify loss of periodic memory.",
                "Use cross-correlation lags to estimate propagation delay from bob1 to other tracked bobs.",
                "Energy proxy excludes magnetic potential, so it is useful for timing and relative response, not absolute conservation."
            ]
        },
        "outputs": {
            "cleaned_horizontal_proxy_csv": str(clean_csv),
            "energy_proxy_fraction_csv": str(frac_csv),
            "figure": str(fig),
        }
    }
    out_json = OUT_DIR / "time_domain_bobs_1_2_3_5_summary.json"
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "duration_s": summary["duration_s"],
        "sample_rate_Hz": summary["sample_rate_Hz"],
        "dominant_frequency_peaks": summary["dominant_frequency_peaks"],
        "response_metrics": summary["response_metrics"],
        "peak_interval_metrics": summary["peak_interval_metrics"],
        "autocorrelation_metrics": summary["autocorrelation_metrics"],
        "cross_correlation_lags": summary["cross_correlation_lags"],
        "summary": str(out_json),
        "figure": str(fig),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
