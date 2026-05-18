from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "03_key_figures" / "experiment_time_series_gallery"
OUT.mkdir(parents=True, exist_ok=True)

COLORS = [
    (42, 105, 180),
    (223, 135, 44),
    (60, 145, 92),
    (198, 72, 62),
    (126, 92, 168),
]


def font(size, bold=False):
    candidates = [
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            pass
    return ImageFont.load_default()


def map_pt(x, y, box, xlim, ylim):
    l, t, r, b = box
    xx = l + (x - xlim[0]) / max(1e-12, xlim[1] - xlim[0]) * (r - l)
    yy = b - (y - ylim[0]) / max(1e-12, ylim[1] - ylim[0]) * (b - t)
    return xx, yy


def draw_timeseries(path, title, subtitle, t, series, labels, ylabel, max_duration=None):
    t = np.asarray(t, dtype=float)
    series = np.asarray(series, dtype=float)
    if max_duration is not None:
        mask = t <= min(float(t[-1]), max_duration)
        t = t[mask]
        series = series[mask]

    # Remove the static offset for readability but preserve amplitude units.
    y = series - np.nanmedian(series, axis=0, keepdims=True)
    finite = np.isfinite(y)
    lo, hi = np.nanpercentile(y[finite], [1, 99])
    pad = max(1e-9, 0.12 * (hi - lo))
    ylim = (lo - pad, hi + pad)
    xlim = (float(t[0]), float(t[-1]))

    W, H = 1500, 820
    img = Image.new("RGB", (W, H), (248, 248, 246))
    d = ImageDraw.Draw(img)
    d.text((58, 34), title, fill=(24, 30, 38), font=font(30, True))
    d.text((60, 74), subtitle, fill=(86, 90, 98), font=font(17))

    box = (90, 130, 1360, 690)
    d.rectangle(box, outline=(60, 65, 72), width=1)
    for gx in np.linspace(xlim[0], xlim[1], 7):
        px, _ = map_pt(gx, ylim[0], box, xlim, ylim)
        d.line((px, box[1], px, box[3]), fill=(224, 226, 230))
        d.text((px - 18, box[3] + 12), f"{gx:.0f}", fill=(86, 90, 98), font=font(13))
    for gy in np.linspace(ylim[0], ylim[1], 6):
        _, py = map_pt(xlim[0], gy, box, xlim, ylim)
        d.line((box[0], py, box[2], py), fill=(224, 226, 230))
        d.text((box[0] - 10, py - 8), f"{gy:.2g}", fill=(86, 90, 98), font=font(13), anchor="ra")

    for i in range(y.shape[1]):
        pts = [map_pt(tv, yv, box, xlim, ylim) for tv, yv in zip(t, y[:, i]) if np.isfinite(yv)]
        if len(pts) > 1:
            d.line(pts, fill=COLORS[i % len(COLORS)], width=2)

    d.text(((box[0] + box[2]) / 2 - 35, 742), "time / s", fill=(70, 75, 82), font=font(16))
    d.text((28, 122), ylabel, fill=(70, 75, 82), font=font(15))

    lx, ly = 1030, 105
    for i, lab in enumerate(labels):
        d.rectangle((lx + i * 85, ly, lx + 18 + i * 85, ly + 12), fill=COLORS[i % len(COLORS)])
        d.text((lx + 24 + i * 85, ly - 5), lab, fill=(55, 60, 68), font=font(14))

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def draw_per_bob_panels(path, title, subtitle, t, series, labels, ylabel, max_duration=None):
    t = np.asarray(t, dtype=float)
    series = np.asarray(series, dtype=float)
    if max_duration is not None:
        mask = t <= min(float(t[-1]), max_duration)
        t = t[mask]
        series = series[mask]

    y = series - np.nanmedian(series, axis=0, keepdims=True)
    xlim = (float(t[0]), float(t[-1]))
    W, H = 1500, 1180
    img = Image.new("RGB", (W, H), (248, 248, 246))
    d = ImageDraw.Draw(img)
    d.text((58, 30), title, fill=(24, 30, 38), font=font(30, True))
    d.text((60, 70), subtitle, fill=(86, 90, 98), font=font(17))

    left, right = 105, 1390
    top0, panel_h, gap = 125, 175, 26
    for i in range(y.shape[1]):
        top = top0 + i * (panel_h + gap)
        box = (left, top, right, top + panel_h)
        yy = y[:, i]
        finite = np.isfinite(yy)
        lo, hi = np.nanpercentile(yy[finite], [1, 99])
        pad = max(1e-9, 0.16 * (hi - lo))
        ylim = (lo - pad, hi + pad)
        d.rectangle(box, outline=(60, 65, 72), width=1)
        for gx in np.linspace(xlim[0], xlim[1], 7):
            px, _ = map_pt(gx, ylim[0], box, xlim, ylim)
            d.line((px, box[1], px, box[3]), fill=(226, 228, 232))
            if i == y.shape[1] - 1:
                d.text((px - 18, box[3] + 8), f"{gx:.0f}", fill=(86, 90, 98), font=font(12))
        for gy in np.linspace(ylim[0], ylim[1], 4):
            _, py = map_pt(xlim[0], gy, box, xlim, ylim)
            d.line((box[0], py, box[2], py), fill=(226, 228, 232))
        pts = [map_pt(tv, yv, box, xlim, ylim) for tv, yv in zip(t, yy) if np.isfinite(yv)]
        if len(pts) > 1:
            d.line(pts, fill=COLORS[i % len(COLORS)], width=2)
        d.rectangle((35, top + 63, 56, top + 79), fill=COLORS[i % len(COLORS)])
        d.text((63, top + 55), labels[i], fill=(36, 42, 50), font=font(18, True))
        d.text((left - 8, top + 5), f"{ylim[1]:.2g}", fill=(86, 90, 98), font=font(12), anchor="ra")
        d.text((left - 8, top + panel_h - 18), f"{ylim[0]:.2g}", fill=(86, 90, 98), font=font(12), anchor="ra")

    d.text((700, H - 42), "time / s", fill=(70, 75, 82), font=font(16))
    d.text((24, 105), ylabel, fill=(70, 75, 82), font=font(15))
    img.save(path)


def main():
    outputs = []

    p = ROOT / "04_data_outputs" / "time_frequency_all_5_bobs" / "all_5_bobs_cleaned_detrended_proxy.csv"
    df = pd.read_csv(p)
    cols = [f"bob{i}_proxy" for i in range(1, 6)]
    out = OUT / "experiment_3cm_all5_time_series.png"
    draw_timeseries(out, "3 cm experiment: all five bobs", "cleaned/detrended horizontal proxy; offset removed for comparison", df["t_s"], df[cols], [f"bob{i}" for i in range(1, 6)], "proxy amplitude", max_duration=30)
    outputs.append(out)
    out = OUT / "experiment_3cm_each_bob_panels.png"
    draw_per_bob_panels(out, "3 cm experiment: each bob separately", "cleaned/detrended horizontal proxy; each panel has its own y-scale", df["t_s"], df[cols], [f"bob{i}" for i in range(1, 6)], "proxy amplitude", max_duration=30)
    outputs.append(out)

    p = ROOT / "04_data_outputs" / "time_frequency_spacing_5cm" / "spacing_5cm_cleaned_detrended_proxy.csv"
    df = pd.read_csv(p)
    cols = [f"bob{i}" for i in range(1, 6)]
    out = OUT / "experiment_5cm_all5_time_series.png"
    draw_timeseries(out, "5 cm experiment: all five bobs", "cleaned/detrended horizontal proxy; offset removed for comparison", df["t_s"], df[cols], [f"bob{i}" for i in range(1, 6)], "proxy amplitude", max_duration=30)
    outputs.append(out)
    out = OUT / "experiment_5cm_each_bob_panels.png"
    draw_per_bob_panels(out, "5 cm experiment: each bob separately", "cleaned/detrended horizontal proxy; each panel has its own y-scale", df["t_s"], df[cols], [f"bob{i}" for i in range(1, 6)], "proxy amplitude", max_duration=30)
    outputs.append(out)

    p = ROOT / "04_data_outputs" / "time_domain_bobs_1_2_3_5" / "bobs_1_2_3_5_cleaned_theta.csv"
    df = pd.read_csv(p)
    cols = ["bob1_theta_rad", "bob2_theta_rad", "bob3_theta_rad", "bob5_theta_rad"]
    out = OUT / "experiment_3cm_bobs_1_2_3_5_theta_time_series.png"
    draw_timeseries(out, "3 cm experiment: bobs 1, 2, 3, 5", "cleaned angular displacement from tracker; static offset removed", df["t_s"], df[cols], ["bob1", "bob2", "bob3", "bob5"], "theta / rad", max_duration=30)
    outputs.append(out)
    out = OUT / "experiment_3cm_bobs_1_2_3_5_each_panel.png"
    draw_per_bob_panels(out, "3 cm experiment: bobs 1, 2, 3, 5 separately", "cleaned angular displacement; each panel has its own y-scale", df["t_s"], df[cols], ["bob1", "bob2", "bob3", "bob5"], "theta / rad", max_duration=30)
    outputs.append(out)

    edge = pd.read_csv(ROOT / "04_data_outputs" / "edge_second_pendulum_new" / "edge_pendulum_B_cleaned.csv")
    second = pd.read_csv(ROOT / "04_data_outputs" / "edge_second_pendulum_new" / "second_pendulum_C_cleaned.csv")
    n = min(len(edge), len(second))
    t = edge["t_s"].to_numpy()[:n]
    y = np.column_stack([
        edge["x_detrended_px"].to_numpy()[:n],
        second["x_detrended_px"].to_numpy()[:n],
    ])
    out = OUT / "experiment_edge_second_time_series.png"
    draw_timeseries(out, "Edge vs second bob experiment", "B=edge bob, C=second bob; smoothed/detrended x-pixel motion", t, y, ["edge B", "second C"], "detrended x / px", max_duration=30)
    outputs.append(out)

    for path in outputs:
        print(path)


if __name__ == "__main__":
    main()
