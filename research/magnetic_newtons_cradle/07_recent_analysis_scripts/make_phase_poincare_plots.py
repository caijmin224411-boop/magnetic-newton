import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import savgol_filter


ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = ROOT / "03_key_figures"
OUT_DIR = ROOT / "04_data_outputs" / "phase_poincare_analysis"
FIG_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

DATASETS = {
    "3 cm": ROOT / "04_data_outputs" / "time_frequency_all_5_bobs" / "all_5_bobs_cleaned_detrended_proxy.csv",
    "5 cm": ROOT / "04_data_outputs" / "time_frequency_spacing_5cm" / "spacing_5cm_cleaned_detrended_proxy.csv",
}


def load_cleaned(path):
    df = pd.read_csv(path)
    t = df["t_s"].to_numpy(float)
    cols = [c for c in df.columns if c != "t_s"][:5]
    x = df[cols].to_numpy(float)
    return t, x


def smooth_and_velocity(t, x):
    dt = float(np.median(np.diff(t)))
    win = max(9, int(round(0.12 / dt)) | 1)
    if win >= len(t):
        win = len(t) // 2 * 2 - 1
    if win < 7:
        xs = x.copy()
    else:
        xs = np.column_stack([savgol_filter(x[:, i], win, 3) for i in range(x.shape[1])])
    v = np.gradient(xs, dt, axis=0)
    return xs, v


def poincare_points(t, x, v, section_index=2):
    """Use bob3 x=0, positive crossing. Record all bobs at each crossing."""
    s = x[:, section_index]
    vs = v[:, section_index]
    rows = []
    for k in range(len(t) - 1):
        if s[k] <= 0 < s[k + 1] and vs[k] > 0:
            denom = s[k + 1] - s[k]
            alpha = 0.0 if abs(denom) < 1e-12 else -s[k] / denom
            tc = t[k] + alpha * (t[k + 1] - t[k])
            xc = x[k] + alpha * (x[k + 1] - x[k])
            vc = v[k] + alpha * (v[k + 1] - v[k])
            rows.append([tc, *xc.tolist(), *vc.tolist()])
    return np.array(rows, dtype=float) if rows else np.zeros((0, 11))


def save_poincare_csv(name, pts):
    stem = name.replace(" ", "")
    path = OUT_DIR / f"poincare_{stem}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["t_s", *[f"bob{i}_x" for i in range(1, 6)], *[f"bob{i}_v" for i in range(1, 6)]])
        writer.writerows(pts.tolist())
    return path


def main():
    fig, axes = plt.subplots(2, 3, figsize=(15, 9), dpi=160)
    summary_rows = []

    for row, (name, path) in enumerate(DATASETS.items()):
        t, raw = load_cleaned(path)
        x, v = smooth_and_velocity(t, raw)
        pts = poincare_points(t, x, v, section_index=2)
        csv_path = save_poincare_csv(name, pts)

        # Phase portraits for bob1, bob3, bob5.
        ax = axes[row, 0]
        for i, color in zip([0, 2, 4], ["#d6483c", "#309666", "#6e50a5"]):
            ax.plot(x[:, i], v[:, i], lw=0.55, alpha=0.65, color=color, label=f"bob{i+1}")
        ax.set_title(f"{name}: phase portraits")
        ax.set_xlabel("normalized displacement proxy")
        ax.set_ylabel("proxy velocity / s")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8)

        # Time-colored phase portrait for bob3, showing dissipative contraction.
        ax = axes[row, 1]
        sc = ax.scatter(x[:, 2], v[:, 2], c=t, s=2, cmap="viridis", alpha=0.75)
        ax.set_title(f"{name}: bob3 phase portrait, time colored")
        ax.set_xlabel("bob3 proxy")
        ax.set_ylabel("bob3 velocity / s")
        ax.grid(alpha=0.25)
        cb = fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.04)
        cb.set_label("time / s")

        # Poincare section: bob3 crosses zero upward; record bob1 and bob2 states.
        ax = axes[row, 2]
        if len(pts):
            ax.scatter(pts[:, 1], pts[:, 6], s=16, alpha=0.75, label="bob1 state")
            ax.scatter(pts[:, 2], pts[:, 7], s=16, alpha=0.55, label="bob2 state")
            ax.scatter(pts[:, 5], pts[:, 10], s=16, alpha=0.55, label="bob5 state")
        ax.set_title(f"{name}: Poincare section\nbob3 proxy=0, upward")
        ax.set_xlabel("displacement proxy at crossing")
        ax.set_ylabel("velocity proxy/s at crossing")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8)

        if len(pts):
            spread_bob1 = float(np.sqrt(np.var(pts[:, 1]) + np.var(pts[:, 6])))
            spread_bob2 = float(np.sqrt(np.var(pts[:, 2]) + np.var(pts[:, 7])))
            spread_bob5 = float(np.sqrt(np.var(pts[:, 5]) + np.var(pts[:, 10])))
        else:
            spread_bob1 = spread_bob2 = spread_bob5 = 0.0
        summary_rows.append({
            "dataset": name,
            "poincare_point_count": int(len(pts)),
            "poincare_csv": str(csv_path),
            "bob1_section_spread": spread_bob1,
            "bob2_section_spread": spread_bob2,
            "bob5_section_spread": spread_bob5,
        })

    fig.suptitle("Magnetic Newtons cradle: phase portraits and Poincare sections", fontsize=15)
    fig.tight_layout()
    out_fig = FIG_DIR / "phase_poincare_3cm_5cm.png"
    fig.savefig(out_fig)

    summary_path = OUT_DIR / "phase_poincare_summary.csv"
    pd.DataFrame(summary_rows).to_csv(summary_path, index=False, encoding="utf-8-sig")

    print(out_fig)
    print(summary_path)
    print(pd.DataFrame(summary_rows).to_string(index=False))


if __name__ == "__main__":
    main()
