import csv
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "05_code"
DATA_DIR = ROOT / "04_data_outputs"
FIG_DIR = ROOT / "03_key_figures"
THEORY_DIR = ROOT / "01_theory"
SWEEP_DIR = DATA_DIR / "effective_length_sweep"

TRACKER_SUMMARY = DATA_DIR / "tracker_vs_4cm_220mT_release50deg_model_summary.json"
FORCE_TABLE = DATA_DIR / "force_table_5cm_220mT_disk_2d.csv"

OUT_CSV = SWEEP_DIR / "effective_length_sweep_summary.csv"
OUT_JSON = SWEEP_DIR / "effective_length_sweep_summary.json"
OUT_PNG = FIG_DIR / "effective_length_sweep_frequency_error.png"
OUT_MD = THEORY_DIR / "Effective_Length_Inferred_From_Frequency.md"


def font(size):
    for name in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/arial.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def target_frequencies():
    low_candidates = []
    high_candidates = []
    if TRACKER_SUMMARY.exists():
        data = json.loads(TRACKER_SUMMARY.read_text(encoding="utf-8"))
        for track in data.get("tracker_peaks_Hz_amp", []):
            for freq, _amp in track:
                if 1.0 <= freq <= 1.6:
                    low_candidates.append(float(freq))
                if 2.0 <= freq <= 2.6:
                    high_candidates.append(float(freq))
    low = float(np.median(low_candidates)) if low_candidates else 1.3756
    high = float(np.median(high_candidates)) if high_candidates else 2.2768
    return low, high


def local_peak(freq, amp, lo, hi):
    freq = np.asarray(freq, dtype=float)
    amp = np.asarray(amp, dtype=float)
    best_freq = math.nan
    best_amp = -1.0
    for col in range(amp.shape[1]):
        y = amp[:, col]
        mask = (freq >= lo) & (freq <= hi)
        idxs = np.where(mask)[0]
        for i in idxs:
            if i == 0 or i == len(freq) - 1:
                continue
            if y[i] >= y[i - 1] and y[i] >= y[i + 1] and y[i] > best_amp:
                best_amp = float(y[i])
                best_freq = float(freq[i])
    return best_freq, best_amp


def read_model_spectrum(path):
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    freq = np.array([float(r["frequency_Hz"]) for r in rows], dtype=float)
    columns = [c for c in rows[0].keys() if c != "frequency_Hz"]
    amp = np.array([[float(r[c]) for c in columns] for r in rows], dtype=float)
    return freq, amp


def read_equilibrium(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return [float(r["theta_equilibrium_deg"]) for r in csv.DictReader(f)]


def run_case(length_m):
    prefix = f"len_{length_m * 100:.1f}cm".replace(".", "p")
    out_dir = SWEEP_DIR / prefix
    out_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({
        "MNC_CASE_PREFIX": prefix,
        "MNC_OUTPUT_DIR": str(out_dir),
        "MNC_FORCE_TABLE": str(FORCE_TABLE),
        "MNC_MASS_KG": "0.070",
        "MNC_PIVOT_SPACING_M": "0.040",
        "MNC_DISK_RADIUS_M": "0.015",
        "MNC_MIN_GAP_M": "0.0020",
        "MNC_DURATION_S": os.environ.get("MNC_SWEEP_DURATION_S", "12"),
        "MNC_SAMPLE_HZ": os.environ.get("MNC_SWEEP_SAMPLE_HZ", "240"),
        "MNC_USE_SOLVED_EQUILIBRIUM": "1",
        "MNC_RELEASE_INDEX": "0",
        "MNC_RELEASE_DELTA_RAD": "-0.872664626",
        "MNC_LENGTH_M": f"{length_m:.6f}",
        "MNC_SKIP_LYAPUNOV": "1",
        "MNC_SKIP_PLOTS": "1",
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
    spectrum_path = out_dir / f"{prefix}_frequency_spectrum.csv"
    equilibrium_path = out_dir / f"{prefix}_equilibrium.csv"
    freq, amp = read_model_spectrum(spectrum_path)
    model_low, model_low_amp = local_peak(freq, amp, 0.7, 1.8)
    model_high, model_high_amp = local_peak(freq, amp, 1.8, 3.0)
    return {
        "length_m": length_m,
        "length_cm": length_m * 100,
        "prefix": prefix,
        "model_low_Hz": model_low,
        "model_low_amp": model_low_amp,
        "model_high_Hz": model_high,
        "model_high_amp": model_high_amp,
        "equilibrium_deg": read_equilibrium(equilibrium_path),
        "spectrum_csv": str(spectrum_path),
    }


def plot_summary(rows, target_low, target_high):
    width, height = 1280, 760
    img = Image.new("RGB", (width, height), (248, 247, 242))
    d = ImageDraw.Draw(img)
    title_font = font(26)
    small = font(16)
    box = (105, 90, 1200, 625)
    d.text((105, 38), "Effective length inferred from Tracker frequency peaks", fill=(28, 28, 28), font=title_font)
    d.rectangle(box, outline=(35, 35, 35))
    xs = np.array([r["length_cm"] for r in rows])
    err = np.array([r["combined_error_Hz"] for r in rows])
    low = np.array([r["model_low_Hz"] for r in rows])
    high = np.array([r["model_high_Hz"] for r in rows])
    xlim = (float(xs.min()) - 0.3, float(xs.max()) + 0.3)
    ylim = (0.0, max(0.3, float(np.nanmax(err)) * 1.2))

    def pt(x, y):
        left, top, right, bottom = box
        px = left + (x - xlim[0]) / (xlim[1] - xlim[0]) * (right - left)
        py = bottom - (y - ylim[0]) / (ylim[1] - ylim[0]) * (bottom - top)
        return int(px), int(py)

    for gx in np.linspace(math.ceil(xlim[0]), math.floor(xlim[1]), 6):
        px, _ = pt(gx, 0)
        d.line((px, box[1], px, box[3]), fill=(225, 222, 215))
        d.text((px - 18, box[3] + 12), f"{gx:.1f}", fill=(70, 70, 70), font=small)
    for gy in np.linspace(ylim[0], ylim[1], 6):
        _, py = pt(xlim[0], gy)
        d.line((box[0], py, box[2], py), fill=(225, 222, 215))
        d.text((35, py - 8), f"{gy:.2f}", fill=(70, 70, 70), font=small)

    pts = [pt(x, y) for x, y in zip(xs, err)]
    if len(pts) > 1:
        d.line(pts, fill=(40, 112, 185), width=3)
    for p in pts:
        d.ellipse((p[0] - 5, p[1] - 5, p[0] + 5, p[1] + 5), fill=(40, 112, 185))

    best = min(rows, key=lambda r: r["combined_error_Hz"])
    bx, by = pt(best["length_cm"], best["combined_error_Hz"])
    d.ellipse((bx - 8, by - 8, bx + 8, by + 8), outline=(214, 72, 60), width=4)
    d.text((760, 115), f"Best L_eff = {best['length_cm']:.1f} cm", fill=(214, 72, 60), font=font(22))
    d.text((760, 150), f"Tracker targets: {target_low:.3f} Hz, {target_high:.3f} Hz", fill=(50, 50, 50), font=small)
    d.text((760, 178), f"Model peaks: {best['model_low_Hz']:.3f} Hz, {best['model_high_Hz']:.3f} Hz", fill=(50, 50, 50), font=small)
    d.text((480, 690), "effective pendulum length / cm", fill=(60, 60, 60), font=small)
    d.text((28, 70), "frequency error / Hz", fill=(60, 60, 60), font=small)
    img.save(OUT_PNG)


def write_outputs(rows, target_low, target_high):
    SWEEP_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    THEORY_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        "length_cm", "target_low_Hz", "model_low_Hz", "low_error_Hz",
        "target_high_Hz", "model_high_Hz", "high_error_Hz", "combined_error_Hz",
        "equilibrium_deg", "spectrum_csv",
    ]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({
                "length_cm": f"{r['length_cm']:.3f}",
                "target_low_Hz": f"{target_low:.6f}",
                "model_low_Hz": f"{r['model_low_Hz']:.6f}",
                "low_error_Hz": f"{r['low_error_Hz']:.6f}",
                "target_high_Hz": f"{target_high:.6f}",
                "model_high_Hz": f"{r['model_high_Hz']:.6f}",
                "high_error_Hz": f"{r['high_error_Hz']:.6f}",
                "combined_error_Hz": f"{r['combined_error_Hz']:.6f}",
                "equilibrium_deg": ";".join(f"{v:.3f}" for v in r["equilibrium_deg"]),
                "spectrum_csv": r["spectrum_csv"],
            })
    OUT_JSON.write_text(json.dumps({
        "target_low_Hz": target_low,
        "target_high_Hz": target_high,
        "rows": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    best = min(rows, key=lambda r: r["combined_error_Hz"])
    OUT_MD.write_text(f"""# Effective Length Inferred From Frequency

This note records the frequency-based calibration of the effective pendulum length.

## Method

The model is run repeatedly with a common effective length for all five bobs:

```text
L_1 = L_2 = L_3 = L_4 = L_5 = L_eff
```

For each trial length, the script:

```text
1. solves the magnetic static equilibrium,
2. releases the left bob by 50 deg from equilibrium,
3. simulates the angular time series,
4. extracts the model frequency peaks,
5. compares them with Tracker peaks.
```

The Tracker target frequencies used here are:

```text
low-frequency peak  = {target_low:.4f} Hz
high-frequency peak = {target_high:.4f} Hz
```

The error metric is:

```text
error = sqrt((f_low,model - f_low,Tracker)^2
           + (f_high,model - f_high,Tracker)^2)
```

## Result

Best scanned effective length:

```text
L_eff = {best['length_cm']:.2f} cm
```

At this length, the model peaks are:

```text
low-frequency peak  = {best['model_low_Hz']:.4f} Hz
high-frequency peak = {best['model_high_Hz']:.4f} Hz
combined error      = {best['combined_error_Hz']:.4f} Hz
```

This supports using the experimental spectrum to constrain `L_eff`, instead of treating the pendulum length as an arbitrary tuning parameter.

## Output Files

```text
{OUT_CSV}
{OUT_PNG}
```
""", encoding="utf-8")


def main():
    SWEEP_DIR.mkdir(parents=True, exist_ok=True)
    target_low, target_high = target_frequencies()
    if "MNC_SWEEP_LENGTHS_CM" in os.environ:
        lengths = [float(v) / 100 for v in os.environ["MNC_SWEEP_LENGTHS_CM"].split(",")]
    else:
        lengths = [v / 1000 for v in range(55, 131, 5)]
    rows = []
    for length_m in lengths:
        row = run_case(length_m)
        row["target_low_Hz"] = target_low
        row["target_high_Hz"] = target_high
        row["low_error_Hz"] = abs(row["model_low_Hz"] - target_low)
        row["high_error_Hz"] = abs(row["model_high_Hz"] - target_high)
        row["combined_error_Hz"] = math.sqrt(row["low_error_Hz"] ** 2 + row["high_error_Hz"] ** 2)
        rows.append(row)
        print(f"L={row['length_cm']:.1f} cm low={row['model_low_Hz']:.3f} high={row['model_high_Hz']:.3f} error={row['combined_error_Hz']:.3f}")
    write_outputs(rows, target_low, target_high)
    plot_summary(rows, target_low, target_high)
    best = min(rows, key=lambda r: r["combined_error_Hz"])
    print(json.dumps({
        "best_length_cm": best["length_cm"],
        "target_low_Hz": target_low,
        "target_high_Hz": target_high,
        "model_low_Hz": best["model_low_Hz"],
        "model_high_Hz": best["model_high_Hz"],
        "combined_error_Hz": best["combined_error_Hz"],
        "summary_csv": str(OUT_CSV),
        "figure": str(OUT_PNG),
        "note": str(OUT_MD),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
