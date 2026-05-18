import csv
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from scipy.signal import savgol_filter


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "05_code"
SOURCE = ROOT / "06_sources" / "new_swing_3cm_70mT.xlsx"
DATA_DIR = ROOT / "04_data_outputs" / "new_swing_3cm_70mT"
FIG_DIR = ROOT / "03_key_figures"
FORCE_TABLE = ROOT / "04_data_outputs" / "force_table_measured_70mT_disk_2d.csv"

DATA_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

L_EFF = 0.11878
MASS_KG = 0.070
C1 = 2.833954997868876e-05
C2 = 6.541910366771381e-06
MAG_FORCE_SCALE = float(os.environ.get("MNC_COMPARE_FORCE_SCALE", "1.0"))
RELEASE_IMAGE_ANGLES_DEG = [125.0, 104.0, 93.5, 85.0, 72.4]
RELEASE_INITIAL_THETA_RAD = [math.radians(90.0 - a) for a in RELEASE_IMAGE_ANGLES_DEG]


def font(size):
    for name in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/arial.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def find_tracks(path):
    raw = pd.read_excel(path, sheet_name="Sheet1", header=None)
    header_row = 1
    df = pd.read_excel(path, sheet_name="Sheet1", header=header_row)
    num = df.apply(pd.to_numeric, errors="coerce")
    tracks = []
    # Tracker export appears as repeated t,x,y,v blocks separated by blank columns.
    for start in [0, 6, 12]:
        cols = num.columns[start:start + 4]
        if len(cols) < 3:
            continue
        block = num.loc[:, cols[:3]].copy()
        block.columns = ["t", "x", "y"]
        block = block.dropna(how="any")
        if len(block) > 20:
            tracks.append({
                "name": f"track_{len(tracks) + 1}",
                "t": block["t"].to_numpy(float),
                "x": block["x"].to_numpy(float),
                "y": block["y"].to_numpy(float),
            })
    return tracks


def circle_fit(x, y):
    A = np.column_stack([x, y, np.ones_like(x)])
    b = -(x * x + y * y)
    a, bcoef, c = np.linalg.lstsq(A, b, rcond=None)[0]
    xc = -a / 2.0
    yc = -bcoef / 2.0
    r = math.sqrt(max(0.0, (a * a + bcoef * bcoef) / 4.0 - c))
    residual = np.sqrt((x - xc) ** 2 + (y - yc) ** 2) - r
    return xc, yc, r, residual


def clean_track(track):
    t, x, y = track["t"], track["x"], track["y"]
    order = np.argsort(t)
    t, x, y = t[order], x[order], y[order]
    t, unique_idx = np.unique(t, return_index=True)
    x, y = x[unique_idx], y[unique_idx]
    xc, yc, radius, residual = circle_fit(x, y)
    # Circle fitting becomes unstable for short arcs and weakly moving middle
    # bobs. For Tracker comparison we therefore use the horizontal displacement
    # as the primary angular proxy. This preserves phase and frequency without
    # creating artificial atan2 wrap jumps.
    x0 = np.nanmedian(x)
    y0 = np.nanmedian(y)
    proxy_radius = np.nanpercentile(np.sqrt((x - x0) ** 2 + (y - y0) ** 2), 95)
    if not np.isfinite(proxy_radius) or proxy_radius <= 1e-12:
        proxy_radius = max(np.nanstd(x) * 3.0, 1.0)
    theta = np.arcsin(np.clip((x - x0) / proxy_radius, -0.999, 0.999))
    dt = float(np.median(np.diff(t)))
    fs = 1.0 / dt
    # Hampel-like spike replacement on theta increments.
    diff = np.diff(theta, prepend=theta[0])
    med = np.median(diff)
    mad = np.median(np.abs(diff - med)) + 1e-12
    spike = np.abs(diff - med) > 12 * 1.4826 * mad
    theta_clean = theta.copy()
    bad_idx = np.where(spike)[0]
    good = ~spike
    if bad_idx.size and good.sum() > 5:
        theta_clean[bad_idx] = np.interp(t[bad_idx], t[good], theta[good])
    if len(theta_clean) > 31:
        win = max(7, int(round(0.12 / dt)) | 1)
        win = min(win, len(theta_clean) // 3 * 2 + 1)
        if win >= 7 and win < len(theta_clean):
            theta_smooth = savgol_filter(theta_clean, win, 3)
        else:
            theta_smooth = theta_clean
    else:
        theta_smooth = theta_clean
    return {
        **track,
        "theta_raw": theta,
        "theta": theta_smooth,
        "fs": fs,
        "center": [xc, yc],
        "radius_tracker_units": radius,
        "proxy_radius_tracker_units": float(proxy_radius),
        "circle_residual_rms": float(np.sqrt(np.mean(residual ** 2))),
        "spike_count": int(spike.sum()),
    }


def uniform_common(cleaned):
    common_start = max(float(c["t"][0]) for c in cleaned)
    common_end = min(float(c["t"][-1]) for c in cleaned)
    dt = float(np.median([np.median(np.diff(c["t"])) for c in cleaned]))
    t = np.arange(common_start, common_end, dt)
    theta = np.column_stack([np.interp(t, c["t"], c["theta"]) for c in cleaned])
    return t - t[0], theta, 1.0 / dt


def spectrum(t, theta):
    dt = float(np.median(np.diff(t)))
    sig = theta - np.mean(theta, axis=0, keepdims=True)
    w = np.hanning(len(sig))[:, None]
    freq = np.fft.rfftfreq(len(sig), dt)
    amp = 2 * np.abs(np.fft.rfft(sig * w, axis=0)) / np.sum(w)
    return freq, amp


def peaks(freq, amp, n=5, lo=0.05, hi=8.0):
    out = []
    mask = (freq >= lo) & (freq <= hi)
    fv = freq[mask]
    for col in range(amp.shape[1]):
        av = amp[mask, col]
        idx = np.argsort(av)[-n:][::-1]
        out.append([(float(fv[i]), float(av[i])) for i in idx])
    return out


def run_model(initial_theta=None):
    prefix = f"model_3cm_70mT_L11p878cm_nonlinear_damping_scale_{MAG_FORCE_SCALE:.2f}".replace(".", "p")
    env = os.environ.copy()
    env.update({
        "MNC_CASE_PREFIX": prefix,
        "MNC_OUTPUT_DIR": str(DATA_DIR),
        "MNC_FORCE_TABLE": str(FORCE_TABLE),
        "MNC_MASS_KG": f"{MASS_KG}",
        "MNC_LENGTH_M": f"{L_EFF}",
        "MNC_PIVOT_SPACING_M": "0.030",
        "MNC_DISK_RADIUS_M": "0.015",
        "MNC_MIN_GAP_M": "0.0020",
        "MNC_DURATION_S": "30",
        "MNC_SAMPLE_HZ": "360",
        "MNC_SKIP_LYAPUNOV": "1",
        "MNC_SKIP_PLOTS": "1",
        "MNC_USE_NONLINEAR_DAMPING": "1",
        "MNC_DAMPING_C1_NMS": f"{C1}",
        "MNC_DAMPING_C2_NMS2": f"{C2}",
        "MNC_MAG_FORCE_SCALE": f"{MAG_FORCE_SCALE}",
    })
    if initial_theta is None:
        env.update({
            "MNC_USE_SOLVED_EQUILIBRIUM": "1",
            "MNC_RELEASE_INDEX": "0",
            "MNC_RELEASE_DELTA_RAD": "-0.872664626",
        })
    else:
        env.update({
            "MNC_USE_SOLVED_EQUILIBRIUM": "0",
            "MNC_INITIAL_THETA": ",".join(f"{v:.10g}" for v in initial_theta),
            "MNC_RELEASE_DELTA_RAD": "0",
        })
    subprocess.run(
        [sys.executable, str(CODE_DIR / "analyze_realistic_field_model.py")],
        cwd=str(CODE_DIR),
        env=env,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return DATA_DIR / f"{prefix}_time_domain.csv", DATA_DIR / f"{prefix}_frequency_spectrum.csv", DATA_DIR / f"{prefix}_equilibrium.csv"


def load_model(path):
    df = pd.read_csv(path)
    t = df["t_s"].to_numpy(float)
    theta = df[[f"theta{i}" for i in range(1, 6)]].to_numpy(float)
    return t, theta


def best_track_mapping(tracker_theta, model_theta, tracker_t, model_t):
    # Compare the three tracked curves against all contiguous 3-bob windows and reversed order.
    max_t = min(float(tracker_t[-1]), float(model_t[-1]), 20.0)
    t = tracker_t[tracker_t <= max_t]
    tr = tracker_theta[:len(t)]
    candidates = []
    for start in range(3):
        for rev in [False, True]:
            cols = list(range(start, start + 3))
            if rev:
                cols = cols[::-1]
            md = np.column_stack([np.interp(t, model_t, model_theta[:, c]) for c in cols])
            # Compare zero-mean normalized oscillations so absolute Tracker angle offset does not dominate.
            trn = tr - tr.mean(axis=0, keepdims=True)
            mdn = md - md.mean(axis=0, keepdims=True)
            scale = np.sum(trn * mdn, axis=0) / (np.sum(mdn * mdn, axis=0) + 1e-12)
            pred = mdn * scale
            rmse = float(np.sqrt(np.mean((trn - pred) ** 2)))
            corr = []
            for i in range(3):
                denom = np.std(trn[:, i]) * np.std(mdn[:, i]) + 1e-12
                corr.append(float(np.mean((trn[:, i] - trn[:, i].mean()) * (mdn[:, i] - mdn[:, i].mean())) / denom))
            candidates.append({"cols_0based": cols, "rmse_rad": rmse, "corr": corr, "scale": scale.tolist()})
    return min(candidates, key=lambda x: x["rmse_rad"]), candidates


def save_csv(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def map_pt(x, y, box, xlim, ylim):
    l, t, r, b = box
    px = l + (x - xlim[0]) / (xlim[1] - xlim[0]) * (r - l)
    py = b - (y - ylim[0]) / (ylim[1] - ylim[0]) * (b - t)
    return int(px), int(py)


def plot_compare(tt, tr_theta, mt, md_theta, mapping, tf, ta, mf, ma, out):
    img = Image.new("RGB", (1500, 920), (248, 247, 242))
    d = ImageDraw.Draw(img)
    title = font(25)
    small = font(14)
    d.text((70, 34), "3 cm / 70 mT: cleaned Tracker data vs calibrated model", fill=(30, 30, 30), font=title)
    colors = [(214, 72, 60), (40, 112, 185), (48, 150, 102)]
    box1 = (80, 105, 705, 690)
    box2 = (815, 105, 1420, 690)
    d.rectangle(box1, outline=(40, 40, 40))
    d.rectangle(box2, outline=(40, 40, 40))

    xmax = min(float(tt[-1]), float(mt[-1]), 20.0)
    tr = tr_theta[tt <= xmax]
    t_short = tt[tt <= xmax]
    md = np.column_stack([np.interp(t_short, mt, md_theta[:, c]) for c in mapping["cols_0based"]])
    vals = np.r_[tr.ravel(), md.ravel()]
    ylim = (float(np.percentile(vals, 2)) * 1.1, float(np.percentile(vals, 98)) * 1.1)
    for gx in np.linspace(0, xmax, 6):
        px = map_pt(gx, ylim[0], box1, (0, xmax), ylim)[0]
        d.line((px, box1[1], px, box1[3]), fill=(225, 222, 215))
        d.text((px - 12, box1[3] + 10), f"{gx:.0f}", fill=(80, 80, 80), font=small)
    for i in range(3):
        pts = [map_pt(x, y, box1, (0, xmax), ylim) for x, y in zip(t_short, tr[:, i])]
        d.line(pts, fill=colors[i], width=3)
        pts = [map_pt(x, y, box1, (0, xmax), ylim) for x, y in zip(t_short, md[:, i])]
        d.line(pts, fill=colors[i], width=1)
        d.text((540, 130 + 26 * i), f"track {i+1}", fill=colors[i], font=small)
    d.text((80, 78), "Time domain: Tracker thick, model thin", fill=(80, 80, 80), font=small)

    ymax = max(float(np.max(ta[tf <= 6])), float(np.max(ma[mf <= 6, :]))) * 1.15
    for gx in np.linspace(0, 6, 7):
        px = map_pt(gx, 0, box2, (0, 6), (0, ymax))[0]
        d.line((px, box2[1], px, box2[3]), fill=(225, 222, 215))
        d.text((px - 9, box2[3] + 10), f"{gx:.0f}", fill=(80, 80, 80), font=small)
    for i in range(3):
        pts = [map_pt(x, y, box2, (0, 6), (0, ymax)) for x, y in zip(tf[tf <= 6], ta[tf <= 6, i])]
        d.line(pts, fill=colors[i], width=3)
        mc = mapping["cols_0based"][i]
        pts = [map_pt(x, y, box2, (0, 6), (0, ymax)) for x, y in zip(mf[mf <= 6], ma[mf <= 6, mc])]
        d.line(pts, fill=colors[i], width=1)
    d.text((815, 78), "Frequency spectrum: Tracker thick, model thin", fill=(80, 80, 80), font=small)
    d.text((80, 750), f"Best mapping: tracks -> model bobs {[c+1 for c in mapping['cols_0based']]}; normalized RMSE={mapping['rmse_rad']:.4f} rad", fill=(40, 40, 40), font=font(16))
    d.text((80, 782), f"Model parameters: d=3 cm, Bsurface=70 mT force table, L={L_EFF*100:.2f} cm, m=70 g, nonlinear damping from single pendulum", fill=(60, 60, 60), font=font(14))
    img.save(out)


def main():
    raw_tracks = find_tracks(SOURCE)
    cleaned = [clean_track(t) for t in raw_tracks]
    tt, tracker_theta, fs = uniform_common(cleaned)
    tf, ta = spectrum(tt, tracker_theta)

    clean_csv = DATA_DIR / "new_swing_3cm_70mT_cleaned_theta.csv"
    save_csv(
        clean_csv,
        ["t_s", *[f"theta_track{i+1}_rad" for i in range(tracker_theta.shape[1])]],
        [[f"{tt[i]:.8f}", *[f"{v:.10g}" for v in tracker_theta[i]]] for i in range(len(tt))],
    )
    tracker_fft_csv = DATA_DIR / "new_swing_3cm_70mT_tracker_frequency_spectrum.csv"
    save_csv(
        tracker_fft_csv,
        ["frequency_Hz", *[f"amp_track{i+1}_rad" for i in range(ta.shape[1])]],
        [[f"{tf[i]:.8f}", *[f"{v:.10g}" for v in ta[i]]] for i in range(len(tf))],
    )

    use_measured_release = os.environ.get("MNC_USE_MEASURED_RELEASE_ANGLES", "0") == "1"
    model_ts, model_fft, eq_csv = run_model(RELEASE_INITIAL_THETA_RAD if use_measured_release else None)
    mt, mtheta = load_model(model_ts)
    mf, ma = spectrum(mt, mtheta)
    mapping, candidates = best_track_mapping(tracker_theta, mtheta, tt, mt)

    fig = FIG_DIR / "new_swing_3cm_70mT_tracker_vs_model.png"
    plot_compare(tt, tracker_theta, mt, mtheta, mapping, tf, ta, mf, ma, fig)

    summary = {
        "source": str(SOURCE),
        "cleaning": {
            "track_count": len(cleaned),
            "duration_s": float(tt[-1]),
            "sample_rate_Hz": float(fs),
            "tracks": [
                {
                    "name": c["name"],
                    "samples": int(len(c["t"])),
                    "circle_center": c["center"],
                    "circle_radius_tracker_units": float(c["radius_tracker_units"]),
                    "proxy_radius_tracker_units": float(c["proxy_radius_tracker_units"]),
                    "circle_residual_rms": float(c["circle_residual_rms"]),
                    "spike_count": int(c["spike_count"]),
                    "theta_initial_rad": float(c["theta"][0]),
                    "theta_min_rad": float(np.min(c["theta"])),
                    "theta_max_rad": float(np.max(c["theta"])),
                }
                for c in cleaned
            ],
        },
        "model_parameters": {
            "pivot_spacing_m": 0.030,
            "surface_field_mT": 70,
            "force_table": str(FORCE_TABLE),
            "length_m": L_EFF,
            "mass_kg": MASS_KG,
            "damping_c1_N_m_s": C1,
            "damping_c2_N_m_s2": C2,
            "mag_force_scale": MAG_FORCE_SCALE,
            "initial_condition": (
                "measured release-image angles converted by theta=90deg-image_angle"
                if use_measured_release
                else "solved magnetic equilibrium plus left bob release -50 deg"
            ),
            "release_image_angles_deg": RELEASE_IMAGE_ANGLES_DEG if use_measured_release else None,
            "release_initial_theta_deg": [math.degrees(v) for v in RELEASE_INITIAL_THETA_RAD] if use_measured_release else None,
        },
        "tracker_peaks_Hz_amp": peaks(tf, ta),
        "model_peaks_Hz_amp": peaks(mf, ma),
        "best_mapping": mapping,
        "all_mapping_candidates": candidates,
        "outputs": {
            "cleaned_theta_csv": str(clean_csv),
            "tracker_frequency_csv": str(tracker_fft_csv),
            "model_time_csv": str(model_ts),
            "model_frequency_csv": str(model_fft),
            "model_equilibrium_csv": str(eq_csv),
            "comparison_figure": str(fig),
        },
    }
    out_json = DATA_DIR / "new_swing_3cm_70mT_clean_compare_summary.json"
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "duration_s": summary["cleaning"]["duration_s"],
        "sample_rate_Hz": summary["cleaning"]["sample_rate_Hz"],
        "tracker_peaks_Hz_amp": summary["tracker_peaks_Hz_amp"],
        "model_peaks_Hz_amp": summary["model_peaks_Hz_amp"],
        "best_mapping": summary["best_mapping"],
        "summary": str(out_json),
        "figure": str(fig),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
