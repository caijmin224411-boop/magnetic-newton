import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
TRACKER_XLSX = Path(r"C:\Users\66\Desktop\牛顿.xlsx")
MODEL_CSV = ROOT / os.environ.get("MNC_MODEL_CSV", "realfield_left_release_time_domain.csv")
OUT_PREFIX = os.environ.get("MNC_COMPARE_PREFIX", "tracker_vs_model")


def font(size=18):
    for name in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/arial.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def workbook_preview():
    xls = pd.ExcelFile(TRACKER_XLSX)
    out = []
    for s in xls.sheet_names:
        raw = pd.read_excel(TRACKER_XLSX, sheet_name=s, header=None)
        out.append({"sheet": s, "shape": list(raw.shape), "preview": raw.head(8).fillna("").astype(str).values.tolist()})
    (ROOT / "tracker_workbook_inspection.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def find_header_row(raw):
    best = (0, -1)
    for i in range(min(20, len(raw))):
        vals = [str(v).lower().strip() for v in raw.iloc[i].tolist() if pd.notna(v)]
        score = sum(v in {"t", "x", "y"} or "time" in v or v.startswith(("x", "y")) for v in vals)
        if score > best[1]:
            best = (i, score)
    return best[0]


def load_tracker():
    xls = pd.ExcelFile(TRACKER_XLSX)
    best = None
    for s in xls.sheet_names:
        raw = pd.read_excel(TRACKER_XLSX, sheet_name=s, header=None)
        h = find_header_row(raw)
        df = pd.read_excel(TRACKER_XLSX, sheet_name=s, header=h).dropna(axis=1, how="all").dropna(axis=0, how="all")
        num = df.apply(pd.to_numeric, errors="coerce")
        cols = [c for c in num.columns if num[c].notna().sum() > max(8, len(num) * 0.25)]
        if best is None or len(cols) > len(best[2]):
            best = (s, num[cols], cols)
    if best is None:
        raise RuntimeError("未找到足够的数值列")
    sheet, num, cols = best
    names = [str(c).lower().strip() for c in cols]
    t_idx = next((i for i, n in enumerate(names) if n == "t" or "time" in n), 0)
    t_col = cols[t_idx]
    coord = [c for i, c in enumerate(cols) if i != t_idx]
    x_cols = [c for c in coord if str(c).lower().strip().startswith("x") or ".x" in str(c).lower()]
    y_cols = [c for c in coord if str(c).lower().strip().startswith("y") or ".y" in str(c).lower()]
    if not x_cols or not y_cols:
        x_cols, y_cols = coord[0::2], coord[1::2]
    n = min(5, len(x_cols), len(y_cols))
    t = num[t_col].to_numpy(float)
    x = num[x_cols[:n]].to_numpy(float)
    y = num[y_cols[:n]].to_numpy(float)
    return sheet, str(t_col), [str(c) for c in x_cols[:n]], [str(c) for c in y_cols[:n]], t, x, y


def load_tracker_tracks():
    xls = pd.ExcelFile(TRACKER_XLSX)
    best = None
    for s in xls.sheet_names:
        raw = pd.read_excel(TRACKER_XLSX, sheet_name=s, header=None)
        h = find_header_row(raw)
        df = pd.read_excel(TRACKER_XLSX, sheet_name=s, header=h).dropna(axis=1, how="all").dropna(axis=0, how="all")
        num = df.apply(pd.to_numeric, errors="coerce")
        cols = [c for c in num.columns if num[c].notna().sum() > max(8, len(num) * 0.25)]
        if best is None or len(cols) > len(best[2]):
            best = (s, num[cols], cols)
    if best is None:
        raise RuntimeError("未找到足够的数值列")
    sheet, num, cols = best
    tracks = []
    i = 0
    while i + 2 < len(cols):
        names = [str(cols[i + k]).lower().strip() for k in range(3)]
        if names[0].startswith("t") and names[1].startswith("x") and names[2].startswith("y"):
            t = num[cols[i]].to_numpy(float)
            x = num[cols[i + 1]].to_numpy(float)
            y = num[cols[i + 2]].to_numpy(float)
            tracks.append({"t_col": str(cols[i]), "x_col": str(cols[i + 1]), "y_col": str(cols[i + 2]), "t": t, "x": x, "y": y})
            i += 3
        else:
            i += 1
    if tracks:
        return sheet, tracks
    sheet, tcol, xcols, ycols, t, x, y = load_tracker()
    return sheet, [{"t_col": tcol, "x_col": xcols[i], "y_col": ycols[i], "t": t, "x": x[:, i], "y": y[:, i]} for i in range(x.shape[1])]


def infer_theta(x, y):
    th = np.zeros_like(x)
    for i in range(x.shape[1]):
        xi = x[:, i] - np.nanmedian(x[:, i])
        yi = y[:, i] - np.nanmedian(y[:, i])
        length = np.nanpercentile(np.sqrt(xi * xi + yi * yi), 95)
        if not np.isfinite(length) or length <= 1e-9:
            length = max(np.nanstd(xi) * 3, 1.0)
        th[:, i] = np.arcsin(np.clip(xi / length, -0.999, 0.999))
    return th


def infer_theta_1d(x, y):
    xi = x - np.nanmedian(x)
    yi = y - np.nanmedian(y)
    length = np.nanpercentile(np.sqrt(xi * xi + yi * yi), 95)
    if not np.isfinite(length) or length <= 1e-9:
        length = max(np.nanstd(xi) * 3, 1.0)
    return np.arcsin(np.clip(xi / length, -0.999, 0.999))


def uniform_1d(t, data):
    mask = np.isfinite(t) & np.isfinite(data)
    t, data = t[mask], data[mask]
    order = np.argsort(t)
    t, data = t[order], data[order]
    t, idx = np.unique(t, return_index=True)
    data = data[idx]
    dt = np.median(np.diff(t))
    tu = np.arange(t[0], t[-1], dt)
    du = np.interp(tu, t, data)
    return tu - tu[0], du, 1 / dt


def uniform(t, data):
    mask = np.isfinite(t)
    for i in range(data.shape[1]):
        mask &= np.isfinite(data[:, i])
    t, data = t[mask], data[mask]
    order = np.argsort(t)
    t, data = t[order], data[order]
    t, idx = np.unique(t, return_index=True)
    data = data[idx]
    dt = np.median(np.diff(t))
    tu = np.arange(t[0], t[-1], dt)
    du = np.column_stack([np.interp(tu, t, data[:, i]) for i in range(data.shape[1])])
    return tu - tu[0], du, 1 / dt


def spectrum(t, data):
    dt = np.median(np.diff(t))
    sig = data - np.mean(data, axis=0, keepdims=True)
    w = np.hanning(len(sig))[:, None]
    f = np.fft.rfftfreq(len(sig), dt)
    a = 2 * np.abs(np.fft.rfft(sig * w, axis=0)) / np.sum(w)
    return f, a


def peaks(f, a, count=4):
    valid = (f > 0.05) & (f < 10)
    fv = f[valid]
    ans = []
    for i in range(a.shape[1]):
        av = a[valid, i]
        idx = np.argsort(av)[-count:][::-1]
        ans.append([(float(fv[j]), float(av[j])) for j in idx])
    return ans


def save_csv(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(",".join(header) + "\n")
        for row in rows:
            f.write(",".join(str(v) for v in row) + "\n")


def map_pt(x, y, box, xlim, ylim):
    l, t, r, b = box
    px = l + (x - xlim[0]) / (xlim[1] - xlim[0]) * (r - l)
    py = b - (y - ylim[0]) / (ylim[1] - ylim[0]) * (b - t)
    return int(px), int(py)


def plot_time(path, tt, td, mt, md):
    img = Image.new("RGB", (1360, 800), (248, 247, 242))
    d = ImageDraw.Draw(img)
    fnt = font(22)
    small = font(14)
    box = (105, 90, 1265, 675)
    d.text((105, 42), "Time-domain comparison: Tracker thick, model thin", fill=(30, 30, 30), font=fnt)
    d.rectangle(box, outline=(30, 30, 30))
    xmax = min(tt[-1], mt[-1])
    vals = np.r_[td[tt <= xmax].ravel(), md[mt <= xmax].ravel()]
    ylim = (float(np.nanpercentile(vals, 2)) * 1.15, float(np.nanpercentile(vals, 98)) * 1.15)
    colors = [(214,72,60),(40,112,185),(48,150,102),(222,154,40),(110,80,165)]
    for gx in np.linspace(0, xmax, 7):
        p = map_pt(gx, ylim[0], box, (0, xmax), ylim)[0]
        d.line((p, box[1], p, box[3]), fill=(225,222,215))
        d.text((p-12, box[3]+8), f"{gx:.1f}", fill=(70,70,70), font=small)
    for gy in np.linspace(ylim[0], ylim[1], 7):
        p = map_pt(0, gy, box, (0, xmax), ylim)[1]
        d.line((box[0], p, box[2], p), fill=(225,222,215))
        d.text((24, p-8), f"{gy:.2g}", fill=(70,70,70), font=small)
    for i in range(min(5, td.shape[1], md.shape[1])):
        for t, y, width in [(tt, td[:, i], 3), (mt, md[:, i], 1)]:
            mask = t <= xmax
            pts = [map_pt(xv, yv, box, (0, xmax), ylim) for xv, yv in zip(t[mask], y[mask])]
            if len(pts) > 1:
                d.line(pts, fill=colors[i], width=width)
        d.text((990, 120 + i*28), f"bob {i+1}", fill=colors[i], font=small)
    img.save(path)


def plot_freq(path, tf, ta, mf, ma):
    img = Image.new("RGB", (1360, 800), (248, 247, 242))
    d = ImageDraw.Draw(img)
    box = (105, 90, 1265, 675)
    d.text((105, 42), "Frequency comparison: Tracker thick, model thin", fill=(30,30,30), font=font(22))
    d.rectangle(box, outline=(30,30,30))
    ymax = max(np.max(ta[tf <= 10]), np.max(ma[mf <= 10])) * 1.15
    colors = [(214,72,60),(40,112,185),(48,150,102),(222,154,40),(110,80,165)]
    small = font(14)
    for gx in np.linspace(0,10,6):
        p = map_pt(gx, 0, box, (0,10), (0,ymax))[0]
        d.line((p, box[1], p, box[3]), fill=(225,222,215))
        d.text((p-8, box[3]+8), f"{gx:.0f}", fill=(70,70,70), font=small)
    for i in range(min(5, ta.shape[1], ma.shape[1])):
        for f, a, width in [(tf, ta[:,i], 3), (mf, ma[:,i], 1)]:
            mask = f <= 10
            pts = [map_pt(xv, yv, box, (0,10), (0,ymax)) for xv, yv in zip(f[mask], a[mask])]
            if len(pts) > 1:
                d.line(pts, fill=colors[i], width=width)
    img.save(path)


def main():
    workbook_preview()
    sheet, tracks = load_tracker_tracks()
    track_series = []
    for tr in tracks[:5]:
        th = infer_theta_1d(tr["x"], tr["y"])
        tu, du, fs_i = uniform_1d(tr["t"], th)
        track_series.append((tu, du, fs_i, tr))
    common_end = min(s[0][-1] for s in track_series)
    common_dt = np.median([np.median(np.diff(s[0])) for s in track_series])
    tt = np.arange(0, common_end, common_dt)
    ttheta = np.column_stack([np.interp(tt, s[0], s[1]) for s in track_series])
    fs = 1 / common_dt
    tf, ta = spectrum(tt, ttheta)
    model = pd.read_csv(MODEL_CSV)
    mt = model["t_s"].to_numpy(float)
    mtheta = model[[f"theta{i}" for i in range(1, 6)]].to_numpy(float)
    mf, ma = spectrum(mt, mtheta)
    save_csv(ROOT / "tracker_extracted_theta.csv", ["t_s", *[f"theta{i}" for i in range(1, ttheta.shape[1]+1)]],
             [[f"{tt[i]:.8f}", *[f"{v:.10g}" for v in ttheta[i]]] for i in range(len(tt))])
    save_csv(ROOT / "tracker_extracted_frequency_spectrum.csv", ["frequency_Hz", *[f"amp_theta{i}" for i in range(1, ta.shape[1]+1)]],
             [[f"{tf[i]:.8f}", *[f"{v:.10g}" for v in ta[i]]] for i in range(len(tf))])
    plot_time(ROOT / f"{OUT_PREFIX}_time_domain.png", tt, ttheta, mt, mtheta)
    plot_freq(ROOT / f"{OUT_PREFIX}_frequency.png", tf, ta, mf, ma)
    summary = {
        "used_sheet": sheet,
        "tracks": [{"time_column": tr["t_col"], "x_column": tr["x_col"], "y_column": tr["y_col"]} for _, _, _, tr in track_series],
        "tracker_duration_s": float(tt[-1]), "tracker_sample_rate_Hz_est": float(fs),
        "tracker_peaks_Hz_amp": peaks(tf, ta), "model_peaks_Hz_amp": peaks(mf, ma)
    }
    (ROOT / f"{OUT_PREFIX}_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(ROOT / f"{OUT_PREFIX}_time_domain.png")
    print(ROOT / f"{OUT_PREFIX}_frequency.png")


if __name__ == "__main__":
    main()
