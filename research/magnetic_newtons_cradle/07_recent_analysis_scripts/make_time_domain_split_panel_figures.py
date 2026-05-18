from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "03_key_figures" / "origin_time_domain_exports"
OUT.mkdir(parents=True, exist_ok=True)


def plot_split_panels(csv_path, columns, labels, title, out_name, tmax=60.0):
    df = pd.read_csv(csv_path)
    t_col = "t_s" if "t_s" in df.columns else "time_s"
    df = df[df[t_col] <= tmax].copy()

    colors = ["#4d4d4d", "#e43d30", "#176bdc", "#2fa866", "#9a62d8"]
    fig, axes = plt.subplots(
        len(columns),
        1,
        figsize=(12.5, 8.2),
        sharex=True,
        gridspec_kw={"hspace": 0.08},
    )

    for ax, col, label, color in zip(axes, columns, labels, colors):
        ax.plot(df[t_col], df[col], lw=1.25, color=color)
        ax.axhline(0, color="0.55", lw=0.6, alpha=0.55)
        ax.set_ylabel(label, rotation=0, labelpad=32, va="center", fontsize=11)
        ax.grid(True, axis="x", alpha=0.18)
        ax.grid(True, axis="y", alpha=0.12)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(axis="both", labelsize=9)

    axes[-1].set_xlabel("time / s", fontsize=12)
    axes[-1].set_xlim(0, tmax)
    fig.suptitle(title, fontsize=15, y=0.985)
    fig.text(0.012, 0.5, "cleaned proxy displacement", rotation=90, va="center", fontsize=12)
    fig.tight_layout(rect=(0.035, 0.02, 1, 0.965))
    fig.savefig(OUT / out_name, dpi=220, bbox_inches="tight")
    return OUT / out_name


def main():
    exp3 = ROOT / "04_data_outputs" / "time_frequency_all_5_bobs" / "all_5_bobs_cleaned_detrended_proxy.csv"
    exp5 = ROOT / "04_data_outputs" / "time_frequency_spacing_5cm" / "spacing_5cm_cleaned_detrended_proxy.csv"

    p1 = plot_split_panels(
        exp3,
        [f"bob{i}_proxy" for i in range(1, 6)],
        [f"bob{i}" for i in range(1, 6)],
        "3 cm experiment: separated time-domain traces",
        "time_domain_3cm_five_bobs_split_panels.png",
        tmax=60.0,
    )
    p2 = plot_split_panels(
        exp5,
        [f"bob{i}" for i in range(1, 6)],
        [f"bob{i}" for i in range(1, 6)],
        "5 cm experiment: separated time-domain traces",
        "time_domain_5cm_five_bobs_split_panels.png",
        tmax=60.0,
    )
    print(p1)
    print(p2)


if __name__ == "__main__":
    main()
