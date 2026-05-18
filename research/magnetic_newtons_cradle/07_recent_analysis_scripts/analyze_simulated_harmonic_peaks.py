from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import find_peaks


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "04_data_outputs" / "harmonic_peak_analysis"
FIG_DIR = ROOT / "03_key_figures" / "harmonic_peak_analysis"


CASES = {
    "experiment_3cm": ROOT / "04_data_outputs" / "time_frequency_all_5_bobs" / "all_5_bobs_frequency_spectrum.csv",
    "model_3cm_scale0p5_highres": ROOT / "04_data_outputs" / "model_experiment_coupling_check" / "model_d3cm_scale0p50_frequency_spectrum.csv",
    "model_3cm_physical_preset": ROOT / "04_data_outputs" / "physical_presets" / "physical_3cm_release50_scale0p5_w12_frequency_spectrum.csv",
}


def load_mean_spectrum(path):
    df = pd.read_csv(path)
    fcol = "frequency_Hz" if "frequency_Hz" in df.columns else "f_Hz"
    cols = [c for c in df.columns if c != fcol]
    f = df[fcol].to_numpy(float)
    amp = np.mean(np.abs(df[cols].to_numpy(float)), axis=1)
    mask = (f >= 0) & (f <= 6)
    f = f[mask]
    amp = amp[mask]
    amp = amp / np.nanmax(amp) if np.nanmax(amp) > 0 else amp
    return f, amp


def peak_table(f, amp, min_prom=0.025):
    df = f[1] - f[0]
    distance = max(2, int(round(0.05 / df)))
    peaks, props = find_peaks(amp, prominence=min_prom, distance=distance)
    rows = []
    for p in peaks:
        if f[p] < 0.15:
            continue
        rows.append({"frequency_Hz": float(f[p]), "relative_amp": float(amp[p])})
    out = pd.DataFrame(rows).sort_values("relative_amp", ascending=False).reset_index(drop=True)
    return out


def candidate_relations(target, bases, tol=0.08):
    relations = []
    for i, fi in enumerate(bases):
        for n in (2, 3, 4):
            val = n * fi
            if abs(target - val) <= tol:
                relations.append((abs(target - val), f"{n}f{i+1}", val))
    for i, fi in enumerate(bases):
        for j, fj in enumerate(bases):
            if j < i:
                continue
            val = fi + fj
            if abs(target - val) <= tol:
                relations.append((abs(target - val), f"f{i+1}+f{j+1}", val))
            val = abs(fi - fj)
            if val > 0.1 and abs(target - val) <= tol:
                relations.append((abs(target - val), f"|f{j+1}-f{i+1}|", val))
    if not relations:
        return "", np.nan, np.nan
    err, expr, val = sorted(relations, key=lambda x: x[0])[0]
    return expr, val, err


def classify_case(name, peaks):
    # Use the strongest low-frequency peaks as fundamental candidates; this is a diagnostic,
    # not a proof that only these are independent modes.
    low = peaks[(peaks["frequency_Hz"] < 2.6)].copy()
    bases = low.sort_values("relative_amp", ascending=False).head(3)["frequency_Hz"].sort_values().to_numpy()
    rows = []
    for _, row in peaks.head(14).iterrows():
        f = float(row["frequency_Hz"])
        expr, predicted, err = candidate_relations(f, bases, tol=0.10)
        role = "candidate primary"
        if len(bases) and np.min(np.abs(bases - f)) < 1e-9:
            role = "base peak used for test"
        elif expr:
            role = "nonlinear derived candidate"
        rows.append({
            "case": name,
            "frequency_Hz": f,
            "relative_amp": float(row["relative_amp"]),
            "role": role,
            "candidate_relation": expr,
            "predicted_Hz": predicted,
            "abs_error_Hz": err,
        })
    return pd.DataFrame(rows), bases


def make_figure(spectra, classified):
    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
    colors = {
        "experiment_3cm": "#333333",
        "model_3cm_scale0p5_highres": "#2d6cdf",
        "model_3cm_physical_preset": "#d14a3a",
    }
    for ax, (name, (f, amp)) in zip(axes, spectra.items()):
        ax.plot(f, amp, lw=1.8, color=colors[name])
        ax.set_ylim(0, 1.08)
        ax.set_ylabel("norm. amp")
        ax.set_title(name.replace("_", " "))
        sub = classified[classified["case"] == name]
        for _, r in sub.head(8).iterrows():
            x = r["frequency_Hz"]
            y = r["relative_amp"]
            txt = f"{x:.2f}"
            if r["role"] == "nonlinear derived candidate" and isinstance(r["candidate_relation"], str):
                txt += f"\n{r['candidate_relation']}"
            ax.annotate(txt, (x, y), xytext=(0, 8), textcoords="offset points",
                        ha="center", fontsize=8, arrowprops=dict(arrowstyle="-", lw=0.6, color="0.35"))
        ax.grid(alpha=0.22)
    axes[-1].set_xlim(0, 6)
    axes[-1].set_xlabel("frequency / Hz")
    fig.suptitle("Extra spectral peaks from nonlinear simulation: harmonics and combination candidates", fontsize=14)
    fig.tight_layout()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / "simulated_harmonic_peak_candidates.png", dpi=190, bbox_inches="tight")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    spectra = {}
    classified_all = []
    bases_rows = []
    for name, path in CASES.items():
        f, amp = load_mean_spectrum(path)
        spectra[name] = (f, amp)
        peaks = peak_table(f, amp, min_prom=0.02 if "model" in name else 0.025)
        peaks.to_csv(OUT_DIR / f"{name}_peaks.csv", index=False, encoding="utf-8-sig")
        classified, bases = classify_case(name, peaks)
        classified_all.append(classified)
        for i, b in enumerate(bases, start=1):
            bases_rows.append({"case": name, "base_index": i, "base_frequency_Hz": b})
    classified_all = pd.concat(classified_all, ignore_index=True)
    classified_all.to_csv(OUT_DIR / "harmonic_combination_peak_candidates.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(bases_rows).to_csv(OUT_DIR / "base_peaks_used_for_relation_test.csv", index=False, encoding="utf-8-sig")
    make_figure(spectra, classified_all)
    print(classified_all.to_string(index=False, float_format=lambda v: f"{v:.4f}"))


if __name__ == "__main__":
    main()
