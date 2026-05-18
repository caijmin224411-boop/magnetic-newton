from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "04_data_outputs" / "spectral_background_chaos_check"
FIG_DIR = ROOT / "03_key_figures"

CASES = {
    "3cm": {
        "spectrum": ROOT / "04_data_outputs" / "time_frequency_all_5_bobs" / "all_5_bobs_frequency_spectrum.csv",
        "time": ROOT / "04_data_outputs" / "time_frequency_all_5_bobs" / "all_5_bobs_cleaned_detrended_proxy.csv",
        "freq_col": "frequency_Hz",
    },
    "5cm": {
        "spectrum": ROOT / "04_data_outputs" / "time_frequency_spacing_5cm" / "spacing_5cm_frequency_spectrum.csv",
        "time": ROOT / "04_data_outputs" / "time_frequency_spacing_5cm" / "spacing_5cm_cleaned_detrended_proxy.csv",
        "freq_col": "f_Hz",
    },
}


def local_maxima(y):
    return np.where((y[1:-1] > y[:-2]) & (y[1:-1] >= y[2:]))[0] + 1


def exclude_windows(freq, centers, half_width=0.08):
    mask = np.ones_like(freq, dtype=bool)
    for c in centers:
        mask &= np.abs(freq - c) > half_width
    return mask


def fwhm(freq, amp, idx):
    half = amp[idx] / 2.0
    left = idx
    right = idx
    while left > 0 and amp[left] > half:
        left -= 1
    while right < len(amp) - 1 and amp[right] > half:
        right += 1
    return float(freq[right] - freq[left])


def spectral_entropy(power):
    p = power / np.sum(power) if np.sum(power) > 0 else power
    p = p[p > 0]
    return float(-np.sum(p * np.log(p)) / np.log(len(power))) if len(power) > 1 else 0.0


def analyze_spectrum(case_name, path, freq_col):
    df = pd.read_csv(path)
    freq = df[freq_col].to_numpy(float)
    bob_cols = [c for c in df.columns if c != freq_col]
    use = (freq >= 0.1) & (freq <= 8.0)
    rows = []
    spectra = {}

    for bob in bob_cols:
        amp = df[bob].to_numpy(float)
        f = freq[use]
        a = amp[use]
        peaks = local_maxima(a)
        peaks = peaks[np.argsort(a[peaks])[::-1]] if len(peaks) else np.array([], dtype=int)
        top = peaks[:5]
        top_freqs = f[top]
        top_amps = a[top]
        main_idx = int(np.argmax(a))
        background_mask = exclude_windows(f, top_freqs, half_width=0.08)
        bg = a[background_mask]
        power = a**2
        peak_mask = ~background_mask
        broad_power = np.sum(power[background_mask])
        total_power = np.sum(power)
        median_bg = float(np.median(bg)) if len(bg) else np.nan
        p90_bg = float(np.percentile(bg, 90)) if len(bg) else np.nan
        mad_bg = float(np.median(np.abs(bg - median_bg))) if len(bg) else np.nan
        threshold = median_bg + 3 * mad_bg if np.isfinite(mad_bg) else np.inf
        small_peak_count = int(np.sum((a[peaks] > threshold) & (~np.isin(peaks, top)))) if len(peaks) else 0

        rows.append({
            "case": case_name,
            "bob": bob,
            "main_peak_Hz": float(f[main_idx]),
            "main_peak_amp": float(a[main_idx]),
            "background_median_amp": median_bg,
            "background_p90_amp": p90_bg,
            "background_to_peak_ratio": median_bg / float(a[main_idx]) if a[main_idx] else np.nan,
            "broadband_power_fraction_excluding_top5_windows": float(broad_power / total_power) if total_power else np.nan,
            "spectral_entropy_0p1_8Hz": spectral_entropy(power),
            "main_peak_fwhm_Hz": fwhm(f, a, main_idx),
            "small_peak_count_above_bg_threshold": small_peak_count,
            "top5_peak_Hz": ";".join(f"{x:.3f}" for x in top_freqs),
            "top5_peak_amp": ";".join(f"{x:.5g}" for x in top_amps),
        })
        spectra[bob] = (f, a)
    return pd.DataFrame(rows), spectra


def aggregate_spectrum(path, freq_col):
    df = pd.read_csv(path)
    freq = df[freq_col].to_numpy(float)
    cols = [c for c in df.columns if c != freq_col]
    amp = np.sqrt(np.mean(np.vstack([df[c].to_numpy(float) ** 2 for c in cols]), axis=0))
    return freq, amp


def stft_matrix(time_path, bob_col="bob3", max_freq=8.0, window_s=6.0, step_s=1.5):
    df = pd.read_csv(time_path)
    t = df["t_s"].to_numpy(float)
    if bob_col not in df.columns and f"{bob_col}_proxy" in df.columns:
        bob_col = f"{bob_col}_proxy"
    y = df[bob_col].to_numpy(float)
    dt = float(np.median(np.diff(t)))
    fs = 1.0 / dt
    nwin = max(16, int(round(window_s * fs)))
    nstep = max(1, int(round(step_s * fs)))
    centers = []
    powers = []
    for start in range(0, len(y) - nwin + 1, nstep):
        seg = y[start:start + nwin]
        seg = seg - np.mean(seg)
        win = np.hanning(len(seg))
        spec = np.abs(np.fft.rfft(seg * win))
        freq = np.fft.rfftfreq(len(seg), dt)
        use = freq <= max_freq
        powers.append(spec[use])
        centers.append(float(t[start + nwin // 2]))
    return np.array(centers), freq[use], np.array(powers).T


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_rows = []
    spectra_by_case = {}
    agg = {}
    for name, cfg in CASES.items():
        rows, spectra = analyze_spectrum(name, cfg["spectrum"], cfg["freq_col"])
        all_rows.append(rows)
        spectra_by_case[name] = spectra
        agg[name] = aggregate_spectrum(cfg["spectrum"], cfg["freq_col"])

    summary = pd.concat(all_rows, ignore_index=True)
    summary.to_csv(OUT_DIR / "spectral_background_metrics_by_bob.csv", index=False, encoding="utf-8-sig")
    case_summary = summary.groupby("case").agg({
        "background_to_peak_ratio": "mean",
        "broadband_power_fraction_excluding_top5_windows": "mean",
        "spectral_entropy_0p1_8Hz": "mean",
        "main_peak_fwhm_Hz": "mean",
        "small_peak_count_above_bg_threshold": "mean",
    }).reset_index()
    case_summary.to_csv(OUT_DIR / "spectral_background_case_summary.csv", index=False, encoding="utf-8-sig")

    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    colors = {"3cm": "#b33a3a", "5cm": "#355da8"}
    for ax, (name, (f, a)) in zip(axes, agg.items()):
        use = (f >= 0.1) & (f <= 8)
        ax.plot(f[use], a[use], lw=1.6, color=colors[name])
        ax.set_ylabel(f"{name}\nRMS amp")
        ax.grid(alpha=0.25)
        ax.set_title(f"{name}: aggregate spectrum across five bobs")
    axes[-1].set_xlabel("frequency / Hz")
    fig.suptitle("3 cm vs 5 cm: main peaks and broadband background", fontsize=14)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "spectral_background_3cm_vs_5cm.png", dpi=180, bbox_inches="tight")

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
    for ax, (name, cfg) in zip(axes, CASES.items()):
        centers, freq, mat = stft_matrix(cfg["time"], bob_col="bob3")
        mat_db = 20 * np.log10(mat / (np.max(mat) + 1e-12) + 1e-12)
        im = ax.imshow(mat_db, origin="lower", aspect="auto",
                       extent=[centers.min(), centers.max(), freq.min(), freq.max()],
                       vmin=-45, vmax=0, cmap="magma")
        ax.set_title(f"{name} bob3 short-time spectrum")
        ax.set_xlabel("time / s")
        ax.grid(False)
    axes[0].set_ylabel("frequency / Hz")
    cbar = fig.colorbar(im, ax=axes.ravel().tolist(), shrink=0.88)
    cbar.set_label("relative amplitude / dB")
    fig.savefig(FIG_DIR / "short_time_spectrum_3cm_vs_5cm_bob3.png", dpi=180, bbox_inches="tight")

    print(case_summary.to_string(index=False))


if __name__ == "__main__":
    main()
