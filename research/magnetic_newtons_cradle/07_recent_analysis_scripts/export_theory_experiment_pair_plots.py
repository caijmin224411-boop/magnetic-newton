from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import signal
from scipy.signal import find_peaks


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "03_key_figures" / "theory_experiment_pair_comparisons"
DATA_ROOT = ROOT / "04_data_outputs" / "theory_experiment_pair_comparisons"
OUT_ROOT.mkdir(parents=True, exist_ok=True)
DATA_ROOT.mkdir(parents=True, exist_ok=True)


CASES = [
    {
        "case": "3cm",
        "experiment": ROOT / "04_data_outputs" / "time_frequency_all_5_bobs" / "all_5_bobs_cleaned_detrended_proxy.csv",
        "model": ROOT / "04_data_outputs" / "model_experiment_coupling_check" / "model_d3cm_scale0p50_time_domain.csv",
        "exp_cols": [f"bob{i}_proxy" for i in range(1, 6)],
        "model_cols": [f"theta{i}" for i in range(1, 6)],
    },
    {
        "case": "5cm",
        "experiment": ROOT / "04_data_outputs" / "time_frequency_spacing_5cm" / "spacing_5cm_cleaned_detrended_proxy.csv",
        "model": ROOT / "04_data_outputs" / "model_experiment_coupling_check" / "model_d5cm_scale0p50_time_domain.csv",
        "exp_cols": [f"bob{i}" for i in range(1, 6)],
        "model_cols": [f"theta{i}" for i in range(1, 6)],
    },
]


def zscore(x):
    x = np.asarray(x, dtype=float)
    x = signal.detrend(x, type="linear")
    s = np.std(x)
    return (x - np.mean(x)) / s if s > 0 else x - np.mean(x)


def fft_amp(t, x):
    t = np.asarray(t, dtype=float)
    x = np.asarray(x, dtype=float)
    order = np.argsort(t)
    t, x = t[order], x[order]
    ok = np.isfinite(t) & np.isfinite(x)
    t, x = t[ok], x[ok]
    dt = float(np.median(np.diff(t)))
    tu = np.arange(t[0], t[-1], dt)
    xu = np.interp(tu, t, x)
    xu = zscore(xu)
    win = np.hanning(len(xu))
    freq = np.fft.rfftfreq(len(xu), dt)
    amp = 2 * np.abs(np.fft.rfft(xu * win)) / np.sum(win)
    return tu, xu, freq, amp


def top_peaks(freq, amp, max_f=6.0, n=8):
    band = (freq >= 0.05) & (freq <= max_f)
    f, a = freq[band], amp[band]
    if len(f) < 3:
        return []
    prom = max(np.max(a) * 0.035, np.median(a) * 5)
    peaks, props = find_peaks(a, prominence=prom, distance=max(1, int(0.08 / (f[1] - f[0]))))
    order = np.argsort(a[peaks])[::-1]
    rows = []
    for rank, idx in enumerate(order[:n], start=1):
        pi = peaks[idx]
        rows.append({
            "rank": rank,
            "frequency_Hz": float(f[pi]),
            "amplitude": float(a[pi]),
            "prominence": float(props["prominences"][idx]),
        })
    return rows


def nearest_peak_error(exp_peaks, model_peaks):
    if not exp_peaks or not model_peaks:
        return np.nan
    mf = np.array([p["frequency_Hz"] for p in model_peaks], dtype=float)
    errs = []
    for p in exp_peaks[:5]:
        errs.append(float(np.min(np.abs(mf - p["frequency_Hz"]))))
    return float(np.mean(errs)) if errs else np.nan


def plot_pair(case, bob_index, exp_t, exp_y, model_t, model_y):
    pair_name = f"{case}_bob{bob_index}"
    fig_dir = OUT_ROOT / pair_name
    data_dir = DATA_ROOT / pair_name
    fig_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    et, ey, ef, ea = fft_amp(exp_t, exp_y)
    mt, my, mf, ma = fft_amp(model_t, model_y)

    exp_peaks = top_peaks(ef, ea)
    model_peaks = top_peaks(mf, ma)
    peak_rows = []
    for source, rows in [("experiment", exp_peaks), ("theory_model", model_peaks)]:
        for row in rows:
            peak_rows.append({"source": source, **row})
    pd.DataFrame(peak_rows).to_csv(data_dir / "peak_table.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame({"t_s": et, "experiment_z": ey}).to_csv(data_dir / "experiment_normalized_time.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame({"t_s": mt, "theory_z": my}).to_csv(data_dir / "theory_normalized_time.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame({"frequency_Hz": ef, "experiment_amplitude": ea}).to_csv(data_dir / "experiment_fft.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame({"frequency_Hz": mf, "theory_amplitude": ma}).to_csv(data_dir / "theory_fft.csv", index=False, encoding="utf-8-sig")

    tmax = min(30.0, et[-1] - et[0], mt[-1] - mt[0])
    fig, ax = plt.subplots(figsize=(10.5, 4.8), constrained_layout=True)
    ax.plot(et - et[0], ey, lw=1.25, label="experiment, normalized", color="#1f77b4")
    ax.plot(mt - mt[0], my, lw=1.25, label="theory model, normalized", color="#d62728", alpha=0.85)
    ax.set_xlim(0, tmax)
    ax.set_xlabel("time / s")
    ax.set_ylabel("normalized displacement / angle")
    ax.set_title(f"{case} bob{bob_index}: theory vs experiment, time domain")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    fig.savefig(fig_dir / "time_domain_theory_vs_experiment.png", dpi=240, bbox_inches="tight")
    plt.close(fig)

    ea_norm = ea / np.max(ea[(ef >= 0.05) & (ef <= 6.0)])
    ma_norm = ma / np.max(ma[(mf >= 0.05) & (mf <= 6.0)])
    fig, ax = plt.subplots(figsize=(10.5, 4.8), constrained_layout=True)
    mask_e = (ef >= 0) & (ef <= 6.0)
    mask_m = (mf >= 0) & (mf <= 6.0)
    ax.plot(ef[mask_e], ea_norm[mask_e], lw=1.8, label="experiment FFT", color="#1f77b4")
    ax.plot(mf[mask_m], ma_norm[mask_m], lw=1.8, label="theory FFT", color="#d62728", alpha=0.82)
    for p in exp_peaks[:4]:
        ax.axvline(p["frequency_Hz"], color="#1f77b4", alpha=0.13, lw=1)
    for p in model_peaks[:4]:
        ax.axvline(p["frequency_Hz"], color="#d62728", alpha=0.13, lw=1)
    ax.set_xlim(0, 6.0)
    ax.set_xlabel("frequency / Hz")
    ax.set_ylabel("normalized FFT amplitude")
    ax.set_title(f"{case} bob{bob_index}: theory vs experiment, frequency domain")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    fig.savefig(fig_dir / "frequency_domain_theory_vs_experiment.png", dpi=240, bbox_inches="tight")
    plt.close(fig)

    # A compact two-panel figure for insertion into slides.
    fig, axes = plt.subplots(1, 2, figsize=(13.0, 4.6), constrained_layout=True)
    axes[0].plot(et - et[0], ey, lw=1.15, color="#1f77b4", label="exp")
    axes[0].plot(mt - mt[0], my, lw=1.15, color="#d62728", label="theory")
    axes[0].set_xlim(0, tmax)
    axes[0].set_title("time")
    axes[0].set_xlabel("s")
    axes[0].set_ylabel("normalized")
    axes[0].grid(alpha=0.25)
    axes[0].legend(frameon=False)
    axes[1].plot(ef[mask_e], ea_norm[mask_e], lw=1.6, color="#1f77b4", label="exp")
    axes[1].plot(mf[mask_m], ma_norm[mask_m], lw=1.6, color="#d62728", label="theory")
    axes[1].set_xlim(0, 6.0)
    axes[1].set_title("FFT")
    axes[1].set_xlabel("Hz")
    axes[1].set_ylabel("normalized amp.")
    axes[1].grid(alpha=0.25)
    axes[1].legend(frameon=False)
    fig.suptitle(f"{case} bob{bob_index}: paired theory-experiment comparison", fontsize=14)
    fig.savefig(fig_dir / "paired_summary.png", dpi=240, bbox_inches="tight")
    plt.close(fig)

    return {
        "pair": pair_name,
        "case": case,
        "bob": bob_index,
        "mean_nearest_peak_error_Hz": nearest_peak_error(exp_peaks, model_peaks),
        "experiment_top_peaks_Hz": ", ".join(f"{p['frequency_Hz']:.3f}" for p in exp_peaks[:5]),
        "theory_top_peaks_Hz": ", ".join(f"{p['frequency_Hz']:.3f}" for p in model_peaks[:5]),
        "folder": str(fig_dir),
    }


def main():
    plt.rcParams.update({
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "font.size": 11,
        "axes.linewidth": 1.1,
    })
    summary = []
    for cfg in CASES:
        exp = pd.read_csv(cfg["experiment"])
        model = pd.read_csv(cfg["model"])
        exp_t = exp["t_s"].to_numpy(float)
        model_t = model["t_s"].to_numpy(float)
        for i, (ec, mc) in enumerate(zip(cfg["exp_cols"], cfg["model_cols"]), start=1):
            summary.append(plot_pair(cfg["case"], i, exp_t, exp[ec].to_numpy(float), model_t, model[mc].to_numpy(float)))

    summary_df = pd.DataFrame(summary)
    summary_df.to_csv(DATA_ROOT / "theory_experiment_pair_summary.csv", index=False, encoding="utf-8-sig")
    print(OUT_ROOT)
    print(DATA_ROOT)
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
