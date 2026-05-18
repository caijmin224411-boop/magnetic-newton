import csv
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from scipy.signal import correlate, find_peaks, savgol_filter


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "06_sources" / "spacing_5cm"
OUT_DIR = ROOT / "04_data_outputs" / "time_frequency_spacing_5cm"
FIG_DIR = ROOT / "03_key_figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

BOB_LABELS = ["bob1", "bob2", "bob3", "bob4", "bob5"]
L_EFF = 0.11878
G = 9.81


def font(size):
    for name in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/arial.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def read_txt_track(path, label):
    df = pd.read_csv(path, sep="\t", header=None, engine="python")
    num = df.iloc[2:, 0:3].apply(pd.to_numeric, errors="coerce")
    num.columns = ["t", "x", "y"]
    num = num.dropna(how="any")
    return {
        "label": label,
        "t": num["t"].to_numpy(float),
        "x": num["x"].to_numpy(float),
        "y": num["y"].to_numpy(float),
    }


def read_xlsx_tracks(path):
    df = pd.read_excel(path, sheet_name="Sheet1", header=1)
    num = df.apply(pd.to_numeric, errors="coerce")
    tracks = []
    for label, start in zip(["bob3", "bob4", "bob5"], [0, 5, 9]):
        block = num.iloc[:, start:start + 3].copy()
        block.columns = ["t", "x", "y"]
        block = block.dropna(how="any")
        tracks.append({
            "label": label,
            "t": block["t"].to_numpy(float),
            "x": block["x"].to_numpy(float),
            "y": block["y"].to_numpy(float),
        })
    return tracks


def load_tracks():
    tracks = [
        read_txt_track(SOURCE_DIR / "spacing5cm_bob1.txt", "bob1"),
        read_txt_track(SOURCE_DIR / "spacing5cm_bob2.txt", "bob2"),
    ]
    tracks.extend(read_xlsx_tracks(SOURCE_DIR / "spacing5cm_all.xlsx"))
    ordered = []
    for label in BOB_LABELS:
        track = next(t for t in tracks if t["label"] == label)
        order = np.argsort(track["t"])
        ordered.append({
            "label": label,
            "t": track["t"][order],
            "x": track["x"][order],
            "y": track["y"][order],
        })
    return ordered


def detrend_signal(t, s, strength_s=30.0):
    dt = float(np.median(np.diff(t)))
    win = int(round(strength_s / dt))
    if win % 2 == 0:
        win += 1
    win = min(win, len(s) // 2 * 2 - 1)
    if win < 51:
        return s, np.zeros_like(s)
    trend = savgol_filter(s, win, 2)
    return s - trend, trend


def clean_track(track):
    t, x, y = track["t"], track["x"], track["y"]
    t, idx = np.unique(t, return_index=True)
    x, y = x[idx], y[idx]
    x0 = np.nanmedian(x)
    y0 = np.nanmedian(y)
    radius = np.nanpercentile(np.sqrt((x - x0) ** 2 + (y - y0) ** 2), 95)
    if not np.isfinite(radius) or radius < 1e-9:
        radius = max(np.nanstd(x) * 3, 1.0)
    signal = (x - x0) / radius
    diff = np.diff(signal, prepend=signal[0])
    med = np.median(diff)
    mad = np.median(np.abs(diff - med)) + 1e-12
    spike = np.abs(diff - med) > 12 * 1.4826 * mad
    if spike.any():
        good = ~spike
        signal[spike] = np.interp(t[spike], t[good], signal[good])
    dt = float(np.median(np.diff(t)))
    smooth_win = max(7, int(round(0.10 / dt)) | 1)
    if smooth_win < len(signal):
        signal = savgol_filter(signal, smooth_win, 3)
    signal_detrended, drift = detrend_signal(t, signal)
    return {
        **track,
        "t": t,
        "signal": signal_detrended,
        "raw_proxy": signal,
        "drift": drift,
        "radius_proxy": float(radius),
        "spike_count": int(spike.sum()),
        "drift_range": float(np.max(drift) - np.min(drift)),
    }


def common_time(cleaned):
    start = max(float(c["t"][0]) for c in cleaned)
    end = min(float(c["t"][-1]) for c in cleaned)
    dt = float(np.median([np.median(np.diff(c["t"])) for c in cleaned]))
    t = np.arange(start, end, dt)
    data = np.column_stack([np.interp(t, c["t"], c["signal"]) for c in cleaned])
    raw = np.column_stack([np.interp(t, c["t"], c["raw_proxy"]) for c in cleaned])
    return t - t[0], data, raw, 1.0 / dt


def spectrum(t, data):
    dt = float(np.median(np.diff(t)))
    sig = data - np.mean(data, axis=0, keepdims=True)
    w = np.hanning(len(sig))[:, None]
    freq = np.fft.rfftfreq(len(sig), dt)
    amp = 2 * np.abs(np.fft.rfft(sig * w, axis=0)) / np.sum(w)
    return freq, amp


def moving_rms(t, data, window_s=1.0):
    dt = float(np.median(np.diff(t)))
    n = max(3, int(round(window_s / dt)))
    kernel = np.ones(n) / n
    return np.column_stack([np.sqrt(np.convolve(data[:, i] ** 2, kernel, mode="same")) for i in range(data.shape[1])])


def dominant_peaks(freq, amp, n=6):
    out = {}
    mask = (freq >= 0.1) & (freq <= 8.0)
    fv = freq[mask]
    for i, label in enumerate(BOB_LABELS):
        av = amp[mask, i]
        idx = np.argsort(av)[-n:][::-1]
        out[label] = [{"f_Hz": float(fv[j]), "amp": float(av[j])} for j in idx]
    return out


def response_metrics(t, data):
    rms = moving_rms(t, data, 1.0)
    metrics = []
    for i, label in enumerate(BOB_LABELS):
        early = np.mean(rms[t <= 5, i])
        mid = np.mean(rms[(t >= 30) & (t <= 60), i])
        late = np.mean(rms[(t >= 90) & (t <= 120), i])
        metrics.append({
            "label": label,
            "max_rms": float(np.max(rms[:, i])),
            "time_of_max_rms_s": float(t[np.argmax(rms[:, i])]),
            "rms_first_5s_mean": float(early),
            "rms_30_60s_mean": float(mid),
            "rms_90_120s_mean": float(late),
            "rms_30_60_over_first_5": float(mid / early) if early else None,
            "rms_90_120_over_first_5": float(late / early) if early else None,
        })
    return rms, metrics


def peak_intervals(t, data):
    out = []
    dt = float(np.median(np.diff(t)))
    min_dist = int(round(0.25 / dt))
    for i, label in enumerate(BOB_LABELS):
        sig = data[:, i] - np.mean(data[:, i])
        idx, _ = find_peaks(np.abs(sig), distance=min_dist, prominence=max(0.015, np.std(sig) * 0.25))
        intervals = np.diff(t[idx])
        out.append({
            "label": label,
            "peak_count_abs": int(len(idx)),
            "mean_peak_interval_s": float(np.mean(intervals)) if len(intervals) else None,
            "std_peak_interval_s": float(np.std(intervals)) if len(intervals) else None,
            "cv_peak_interval": float(np.std(intervals) / np.mean(intervals)) if len(intervals) and np.mean(intervals) else None,
        })
    return out


def autocorr_metrics(t, data):
    out = []
    dt = float(np.median(np.diff(t)))
    max_lag = min(int(round(20 / dt)), len(t) // 2)
    for i, label in enumerate(BOB_LABELS):
        sig = data[:, i] - np.mean(data[:, i])
        ac = np.correlate(sig, sig, mode="full")[len(sig) - 1:len(sig) - 1 + max_lag]
        ac = ac / (ac[0] + 1e-12)
        below = np.where(np.abs(ac) < 1 / math.e)[0]
        out.append({
            "label": label,
            "autocorr_1e_decay_time_s": float(below[0] * dt) if len(below) else None,
            "autocorr_abs_at_10s": float(abs(ac[min(int(10 / dt), len(ac) - 1)])),
        })
    return out


def lag_metrics(t, data):
    out = []
    dt = float(np.median(np.diff(t)))
    ref = data[:, 0] - np.mean(data[:, 0])
    max_lag = int(round(3 / dt))
    for i, label in enumerate(BOB_LABELS[1:], start=1):
        sig = data[:, i] - np.mean(data[:, i])
        c = correlate(sig, ref, mode="full")
        lags = np.arange(-len(ref) + 1, len(ref))
        mask = np.abs(lags) <= max_lag
        j = np.argmax(np.abs(c[mask]))
        lag_samples = lags[mask][j]
        out.append({
            "pair": f"bob1_to_{label}",
            "best_lag_s": float(lag_samples * dt),
            "max_abs_crosscorr": float(c[mask][j] / (np.linalg.norm(sig) * np.linalg.norm(ref) + 1e-12)),
        })
    return out


def energy_proxy(data, t):
    dt = float(np.median(np.diff(t)))
    omega = np.gradient(data, dt, axis=0)
    e = 0.5 * L_EFF ** 2 * omega ** 2 + G * L_EFF * (1 - np.cos(np.clip(data, -1.2, 1.2)))
    return e / (np.sum(e, axis=1, keepdims=True) + 1e-12)


def map_pt(x, y, box, xlim, ylim):
    l, top, r, b = box
    return int(l + (x - xlim[0]) / (xlim[1] - xlim[0]) * (r - l)), int(b - (y - ylim[0]) / (ylim[1] - ylim[0]) * (b - top))


def plot(t, data, rms, frac, freq, amp, fig):
    img = Image.new("RGB", (1700, 1180), (248, 247, 242))
    d = ImageDraw.Draw(img)
    d.text((70, 34), "5 cm spacing: five-bob time and frequency analysis", fill=(30, 30, 30), font=font(28))
    colors = [(214, 72, 60), (40, 112, 185), (48, 150, 102), (222, 154, 40), (110, 80, 165)]
    boxes = [(75, 115, 800, 450), (900, 115, 1625, 450), (75, 600, 800, 935), (900, 600, 1625, 935)]
    titles = ["Detrended time series proxy", "1 s moving RMS envelope", "Energy proxy fraction", "Frequency spectrum"]
    for box, title in zip(boxes, titles):
        d.rectangle(box, outline=(40, 40, 40))
        d.text((box[0], box[1] - 28), title, fill=(70, 70, 70), font=font(15))
    xmax = min(25.0, float(t[-1]))
    mask = t <= xmax
    ylim = (float(np.percentile(data[mask], 1)) * 1.1, float(np.percentile(data[mask], 99)) * 1.1)
    for i in range(5):
        pts = [map_pt(x, y, boxes[0], (0, xmax), ylim) for x, y in zip(t[mask], data[mask, i])]
        d.line(pts, fill=colors[i], width=2)
    ylim_r = (0, float(np.percentile(rms[mask], 99)) * 1.15)
    for i in range(5):
        pts = [map_pt(x, y, boxes[1], (0, xmax), ylim_r) for x, y in zip(t[mask], rms[mask, i])]
        d.line(pts, fill=colors[i], width=2)
    for i in range(5):
        pts = [map_pt(x, y, boxes[2], (0, xmax), (0, 1)) for x, y in zip(t[mask], frac[mask, i])]
        d.line(pts, fill=colors[i], width=2)
    fmask = freq <= 6
    ymax = float(np.max(amp[fmask])) * 1.1
    for i in range(5):
        pts = [map_pt(x, y, boxes[3], (0, 6), (0, ymax)) for x, y in zip(freq[fmask], amp[fmask, i])]
        d.line(pts, fill=colors[i], width=2)
    for i, label in enumerate(BOB_LABELS):
        d.rectangle((1280, 975 + 28 * i, 1300, 990 + 28 * i), fill=colors[i])
        d.text((1310, 970 + 28 * i), label, fill=(50, 50, 50), font=font(15))
    img.save(fig)


def save_csv(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def main():
    cleaned = [clean_track(t) for t in load_tracks()]
    t, data, raw, fs = common_time(cleaned)
    freq, amp = spectrum(t, data)
    rms, resp = response_metrics(t, data)
    frac = energy_proxy(data, t)
    peaks = dominant_peaks(freq, amp)
    peak_stats = peak_intervals(t, data)
    autocorr = autocorr_metrics(t, data)
    lags = lag_metrics(t, data)

    save_csv(
        OUT_DIR / "spacing_5cm_cleaned_detrended_proxy.csv",
        ["t_s", *BOB_LABELS],
        [[float(ti), *[float(v) for v in row]] for ti, row in zip(t, data)],
    )
    save_csv(
        OUT_DIR / "spacing_5cm_frequency_spectrum.csv",
        ["f_Hz", *BOB_LABELS],
        [[float(fi), *[float(v) for v in row]] for fi, row in zip(freq, amp)],
    )
    save_csv(
        OUT_DIR / "spacing_5cm_energy_proxy_fraction.csv",
        ["t_s", *BOB_LABELS],
        [[float(ti), *[float(v) for v in row]] for ti, row in zip(t, frac)],
    )

    fig = FIG_DIR / "spacing_5cm_time_frequency_analysis.png"
    plot(t, data, rms, frac, freq, amp, fig)

    summary = {
        "spacing_cm": 5.0,
        "duration_s": float(t[-1] - t[0]),
        "sample_rate_Hz": float(fs),
        "source_mapping": {
            "bob1": "spacing5cm_bob1.txt",
            "bob2": "spacing5cm_bob2.txt",
            "bob3": "spacing5cm_all.xlsx Sheet1 A",
            "bob4": "spacing5cm_all.xlsx Sheet1 B",
            "bob5": "spacing5cm_all.xlsx Sheet1 C",
        },
        "cleaning": [{
            "label": c["label"],
            "radius_proxy": c["radius_proxy"],
            "spike_count": c["spike_count"],
            "drift_range": c["drift_range"],
        } for c in cleaned],
        "dominant_frequency_peaks": peaks,
        "response_metrics": resp,
        "peak_interval_metrics": peak_stats,
        "autocorrelation_metrics": autocorr,
        "cross_correlation_lags_vs_bob1": lags,
        "summary": str(OUT_DIR / "spacing_5cm_time_frequency_summary.json"),
        "figure": str(fig),
    }
    (OUT_DIR / "spacing_5cm_time_frequency_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
