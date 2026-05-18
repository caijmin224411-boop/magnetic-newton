import os
import subprocess
import sys
from pathlib import Path

import cv2
import matplotlib
import numpy as np
import pandas as pd
from scipy.signal import hilbert

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.transforms import Affine2D


ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "05_code"
MODEL = CODE / "analyze_realistic_field_model.py"
FORCE_TABLE = ROOT / "04_data_outputs" / "force_table_measured_70mT_disk_2d.csv"
OUT_FIG = ROOT / "03_key_figures" / "motion_phase_analysis_video"
OUT_DATA = ROOT / "04_data_outputs" / "motion_phase_analysis_video"
OUT_FIG.mkdir(parents=True, exist_ok=True)
OUT_DATA.mkdir(parents=True, exist_ok=True)

N = 5
COLORS = ["#2f6fb6", "#e58a2b", "#3b9160", "#d55545", "#7457a8"]
L = 0.12359
MASS = 0.070


CASES = {
    "physical_3cm_release50_scale0p5_w12_20s": {
        "label": "3 cm strong coupling, scale=0.5, release=50 deg",
        "spacing": 0.030,
        "pair_weights": "1:1,2:1",
        "release_delta_deg": -50.0,
    },
    "physical_5cm_release50_scale0p5_w1_20s": {
        "label": "5 cm weak coupling, scale=0.5, release=50 deg",
        "spacing": 0.050,
        "pair_weights": "1:1",
        "release_delta_deg": -50.0,
    },
}


def run_model(case_name, cfg):
    env = os.environ.copy()
    env.update(
        {
            "MNC_OUTPUT_DIR": str(OUT_DATA),
            "MNC_FORCE_TABLE": str(FORCE_TABLE),
            "MNC_CASE_PREFIX": case_name,
            "MNC_LENGTH_M": str(L),
            "MNC_MASS_KG": str(MASS),
            "MNC_DISK_RADIUS_M": "0.015",
            "MNC_MAG_FORCE_SCALE": "0.5",
            "MNC_USE_NONLINEAR_DAMPING": "1",
            "MNC_DAMPING_C1_NMS": "2.833954997868876e-05",
            "MNC_DAMPING_C2_NMS2": "6.541910366771381e-06",
            "MNC_MIN_GAP_M": "0.002",
            "MNC_NEAR_CONTACT_GAP_M": "0.004",
            "MNC_HARD_WALL_K_N_PER_M2": "1000000",
            "MNC_HARD_WALL_POWER": "2",
            "MNC_STOP_ON_CONTACT": "1",
            "MNC_CONDITIONAL_RELEASE_EQUILIBRIUM": "1",
            "MNC_RELEASE_INDEX": "0",
            "MNC_RELEASE_DELTA_RAD": str(np.deg2rad(cfg["release_delta_deg"])),
            "MNC_PIVOT_SPACING_M": str(cfg["spacing"]),
            "MNC_PAIR_WEIGHTS": cfg["pair_weights"],
            "MNC_DURATION_S": "20",
            "MNC_SAMPLE_HZ": "360",
            "MNC_SKIP_LYAPUNOV": "1",
            "MNC_SKIP_PLOTS": "1",
        }
    )
    result = subprocess.run(
        [sys.executable, str(MODEL)],
        cwd=str(CODE),
        env=env,
        text=True,
        capture_output=True,
    )
    (OUT_DATA / f"{case_name}.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"{case_name} failed. See {OUT_DATA / (case_name + '.log')}")
    return OUT_DATA / f"{case_name}_time_domain.csv"


def centers(theta, spacing):
    pivot_x = (np.arange(1, N + 1) - (N + 1) / 2.0) * spacing
    return pivot_x + L * np.sin(theta), -L * np.cos(theta), pivot_x


def phase_from_theta(theta, omega):
    theta0 = theta - np.mean(theta, axis=0, keepdims=True)
    phase_hilbert = np.unwrap(np.angle(hilbert(theta0, axis=0)), axis=0)
    omega_scale = np.std(omega, axis=0, keepdims=True)
    omega_scale[omega_scale < 1e-9] = 1.0
    theta_scale = np.std(theta0, axis=0, keepdims=True)
    theta_scale[theta_scale < 1e-9] = 1.0
    phase_plane = np.unwrap(np.arctan2(omega / omega_scale, theta0 / theta_scale), axis=0)
    phase = 0.65 * phase_hilbert + 0.35 * phase_plane
    return phase


def add_cylinder(ax, x, y, theta, idx):
    width = 0.018
    height = 0.033
    trans = Affine2D().rotate_deg_around(x * 100, y * 100, np.rad2deg(theta) * 0.25) + ax.transData
    patch = FancyBboxPatch(
        (x * 100 - width * 50, y * 100 - height * 50),
        width * 100,
        height * 100,
        boxstyle="round,pad=0.12,rounding_size=0.45",
        facecolor="#15191f",
        edgecolor=COLORS[idx],
        linewidth=2.0,
        transform=trans,
        zorder=8,
    )
    ax.add_patch(patch)
    ax.plot(
        [x * 100 - width * 30, x * 100 + width * 30],
        [y * 100, y * 100],
        color="#f1d24a",
        lw=2.2,
        transform=trans,
        zorder=9,
    )
    ax.text(x * 100, y * 100 - 0.08, str(idx + 1), color="white", ha="center", va="center", fontsize=8, zorder=10)


def render_frame(case_label, t, theta_now, theta_hist, omega_hist, phase_hist, spacing, frame_i, total_frames):
    x, y, pivot_x = centers(theta_now, spacing)
    fig = plt.figure(figsize=(13.4, 7.2), dpi=120)
    fig.patch.set_facecolor("#f5f6f2")
    gs = fig.add_gridspec(2, 2, width_ratios=[1.38, 1.0], height_ratios=[1.0, 0.82], wspace=0.23, hspace=0.30)

    ax_motion = fig.add_subplot(gs[:, 0])
    ax_phase = fig.add_subplot(gs[0, 1])
    ax_diff = fig.add_subplot(gs[1, 1])

    ax_motion.set_facecolor("#f8f8f4")
    beam_y = 0
    xmin = (pivot_x.min() - L * 1.08) * 100
    xmax = (pivot_x.max() + L * 1.08) * 100
    ax_motion.plot([xmin, xmax], [beam_y, beam_y], color="#b88d47", lw=7, solid_capstyle="round", zorder=3)
    for i in range(N):
        ax_motion.plot([pivot_x[i] * 100, x[i] * 100], [0, y[i] * 100], color="#33383d", lw=1.8, zorder=5)
        ax_motion.plot(pivot_x[i] * 100, 0, "o", color="#22252a", ms=5, zorder=6)
        add_cylinder(ax_motion, x[i], y[i], theta_now[i], i)
    ax_motion.set_aspect("equal", adjustable="box")
    ax_motion.set_xlim(xmin, xmax)
    ax_motion.set_ylim(-15.5, 1.8)
    ax_motion.set_xlabel("x / cm")
    ax_motion.set_ylabel("y / cm")
    ax_motion.grid(color="#c7c7c7", alpha=0.42, lw=0.5)
    ax_motion.set_title(f"{case_label}\nt = {t:05.2f} s", loc="left", fontsize=13, weight="bold")

    ax_phase.set_facecolor("white")
    tail = min(len(theta_hist), 360)
    th_tail = theta_hist[-tail:]
    om_tail = omega_hist[-tail:]
    for i in range(N):
        ax_phase.plot(th_tail[:, i], om_tail[:, i], color=COLORS[i], lw=1.4, alpha=0.85)
        ax_phase.scatter(th_tail[-1, i], om_tail[-1, i], color=COLORS[i], s=20, label=f"bob {i+1}", zorder=5)
    ax_phase.axhline(0, color="#999999", lw=0.6)
    ax_phase.axvline(0, color="#999999", lw=0.6)
    ax_phase.set_title("phase plane: theta - omega")
    ax_phase.set_xlabel("theta / rad")
    ax_phase.set_ylabel("omega / rad s$^{-1}$")
    ax_phase.grid(color="#dddddd", lw=0.5, alpha=0.8)
    ax_phase.legend(ncol=5, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, 1.02), frameon=False)

    phase_ref = phase_hist[:, 2:3]
    phase_diff = np.angle(np.exp(1j * (phase_hist - phase_ref)))
    t_axis = np.linspace(max(0, t - (len(phase_diff) - 1) * 0.1), t, len(phase_diff))
    visible = min(len(phase_diff), 260)
    for i in range(N):
        if i == 2:
            continue
        ax_diff.plot(t_axis[-visible:], phase_diff[-visible:, i], color=COLORS[i], lw=1.4, label=f"{i+1}-3")
    ax_diff.axhline(0, color="#777777", lw=0.65)
    ax_diff.set_ylim(-np.pi, np.pi)
    ax_diff.set_yticks([-np.pi, 0, np.pi])
    ax_diff.set_yticklabels(["-pi", "0", "pi"])
    ax_diff.set_title("relative phase to middle bob")
    ax_diff.set_xlabel("time / s")
    ax_diff.set_ylabel("phase difference / rad")
    ax_diff.grid(color="#dddddd", lw=0.5, alpha=0.8)
    ax_diff.legend(ncol=4, fontsize=8, frameon=False, loc="upper right")

    fig.text(
        0.985,
        0.018,
        f"frame {frame_i + 1}/{total_frames} | cylindrical magnets, rigid rods, real-field force table + nonlinear damping",
        ha="right",
        va="bottom",
        fontsize=8.5,
        color="#404448",
    )
    fig.canvas.draw()
    frame = cv2.cvtColor(np.asarray(fig.canvas.buffer_rgba()), cv2.COLOR_RGBA2BGR)
    plt.close(fig)
    return frame


def export_video(case_name, cfg, csv_path):
    df = pd.read_csv(csv_path)
    theta_cols = [f"theta{i}" for i in range(1, 6)]
    omega_cols = [f"omega{i}" for i in range(1, 6)]
    t_raw = df["t_s"].to_numpy(dtype=float)
    theta_raw = df[theta_cols].to_numpy(dtype=float)
    omega_raw = df[omega_cols].to_numpy(dtype=float)

    fps = 12
    duration = min(20.0, float(t_raw[-1]))
    out_times = np.arange(0, duration, 1.0 / fps)
    theta = np.column_stack([np.interp(out_times, t_raw, theta_raw[:, i]) for i in range(N)])
    omega = np.column_stack([np.interp(out_times, t_raw, omega_raw[:, i]) for i in range(N)])
    phase = phase_from_theta(theta, omega)

    phase_df = pd.DataFrame(
        {
            "t_s": out_times,
            **{f"theta{i+1}_rad": theta[:, i] for i in range(N)},
            **{f"omega{i+1}_rad_s": omega[:, i] for i in range(N)},
            **{f"phase{i+1}_rad": phase[:, i] for i in range(N)},
            **{f"phase_diff_{i+1}_minus_3_rad": np.angle(np.exp(1j * (phase[:, i] - phase[:, 2]))) for i in range(N) if i != 2},
        }
    )
    phase_df.to_csv(OUT_DATA / f"{case_name}_video_phase_samples.csv", index=False, encoding="utf-8-sig")

    first = render_frame(cfg["label"], out_times[0], theta[0], theta[:1], omega[:1], phase[:1], cfg["spacing"], 0, len(out_times))
    video_path = OUT_FIG / f"{case_name}_motion_phase_analysis.mp4"
    snapshot_path = OUT_FIG / f"{case_name}_snapshot.png"
    cv2.imwrite(str(snapshot_path), first)
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (first.shape[1], first.shape[0]))
    writer.write(first)
    for k in range(1, len(out_times)):
        frame = render_frame(cfg["label"], out_times[k], theta[k], theta[: k + 1], omega[: k + 1], phase[: k + 1], cfg["spacing"], k, len(out_times))
        writer.write(frame)
    writer.release()
    return video_path, snapshot_path


def main():
    outputs = []
    for case_name, cfg in CASES.items():
        csv_path = run_model(case_name, cfg)
        outputs.append((case_name, *export_video(case_name, cfg, csv_path)))
    for case_name, video_path, snapshot_path in outputs:
        print(case_name)
        print(video_path)
        print(snapshot_path)


if __name__ == "__main__":
    main()
