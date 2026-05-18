from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "04_data_outputs" / "time_frequency_all_5_bobs" / "all_5_bobs_frequency_spectrum.csv"
OUT = ROOT / "03_key_figures" / "experiment_3cm_each_bob_frequency_panels.png"


def main():
    df = pd.read_csv(CSV)
    f = df["frequency_Hz"]
    cols = [c for c in df.columns if c != "frequency_Hz"]

    fig, axes = plt.subplots(len(cols), 1, figsize=(10, 12), sharex=True)
    colors = ["#3566b8", "#d37a2c", "#5b9a5b", "#c45757", "#8b6fb8"]

    for i, (ax, col) in enumerate(zip(axes, cols)):
        ax.plot(f, df[col], color=colors[i % len(colors)], lw=1.8)
        ax.set_xlim(0, 8)
        ax.set_ylabel(f"bob{i+1}")
        ax.grid(True, alpha=0.25)
        peak_idx = df[col].idxmax()
        peak_f = f.iloc[peak_idx]
        peak_a = df[col].iloc[peak_idx]
        ax.scatter([peak_f], [peak_a], color=colors[i % len(colors)], s=18, zorder=3)
        ax.text(0.98, 0.88, f"main peak {peak_f:.3f} Hz", transform=ax.transAxes,
                ha="right", va="top", fontsize=10, color="#333333")

    axes[0].set_title("3 cm experiment: frequency spectrum of each bob", fontsize=16)
    axes[-1].set_xlabel("frequency / Hz")
    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=180, bbox_inches="tight")
    print(OUT)


if __name__ == "__main__":
    main()
