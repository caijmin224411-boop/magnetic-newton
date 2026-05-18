import csv
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from scipy.signal import savgol_filter, find_peaks
from scipy.optimize import curve_fit, lsq_linear


ROOT = Path(__file__).resolve().parents[1]
IN_THETA = ROOT / "04_data_outputs" / "single_pendulum_calibration" / "single_pendulum_theta.csv"
OUT_DIR = ROOT / "04_data_outputs" / "single_pendulum_calibration"
FIG_DIR = ROOT / "03_key_figures"
SUMMARY = OUT_DIR / "single_pendulum_nonlinear_damping_summary.json"
TABLE = OUT_DIR / "single_pendulum_nonlinear_damping_extrema.csv"
FIG = FIG_DIR / "single_pendulum_nonlinear_damping_fit.png"

G = 9.81
MASS_KG = 0.070
L_M = 0.11878  # large-amplitude-corrected single-pendulum effective length
I = MASS_KG * L_M ** 2


def font(size):
    for name in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/arial.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def load_theta():
    df = pd.read_csv(IN_THETA)
    t = df["t_s"].to_numpy(float)
    theta = df["theta_rad"].to_numpy(float)
    theta = theta - np.mean(theta[-500:])
    return t, theta


def fit_envelope_models(t_ext, amp):
    # Use extrema above a conservative noise floor.
    keep = amp > max(0.015, np.percentile(amp, 15))
    t = t_ext[keep] - t_ext[keep][0]
    a = amp[keep]

    def linear(t, A0, beta):
        return A0 * np.exp(-beta * t)

    def coulomb(t, A0, s):
        return np.maximum(A0 - s * t, 0.0)

    def quadratic(t, A0, q):
        return A0 / (1.0 + q * A0 * t)

    def mixed_lq(t, A0, beta, q):
        # dA/dt = -beta A - q A^2.
        return A0 * np.exp(-beta * t) / (1.0 + (q * A0 / beta) * (1.0 - np.exp(-beta * t)))

    models = {}
    for name, fn, p0, bounds in [
        ("linear_viscous", linear, [a[0], 0.02], ([0, 0], [10, 2])),
        ("coulomb_constant_torque", coulomb, [a[0], 0.002], ([0, 0], [10, 2])),
        ("quadratic_drag_envelope", quadratic, [a[0], 0.05], ([0, 0], [10, 10])),
        ("mixed_linear_quadratic", mixed_lq, [a[0], 0.01, 0.02], ([0, 0, 0], [10, 2, 10])),
    ]:
        popt, _ = curve_fit(fn, t, a, p0=p0, bounds=bounds, maxfev=20000)
        pred = fn(t, *popt)
        rmse = float(np.sqrt(np.mean((pred - a) ** 2)))
        ss_res = float(np.sum((pred - a) ** 2))
        ss_tot = float(np.sum((a - np.mean(a)) ** 2))
        r2 = 1.0 - ss_res / ss_tot
        models[name] = {
            "params": [float(v) for v in popt],
            "rmse_rad": rmse,
            "r2": r2,
            "t_fit_s": t.tolist(),
            "amp_fit_rad": a.tolist(),
            "pred_rad": pred.tolist(),
        }

    # Local amplitude decay rate: dA/dt = -a0 - beta A - q A^2.
    t_mid = 0.5 * (t[1:] + t[:-1])
    a_mid = 0.5 * (a[1:] + a[:-1])
    dadt = np.diff(a) / np.diff(t)
    X = np.column_stack([np.ones_like(a_mid), a_mid, a_mid ** 2])
    # Solve -dA/dt = a0 + beta A + q A^2 with nonnegative terms.
    res = lsq_linear(X, -dadt, bounds=(0, np.inf))
    pred_decay = X @ res.x
    models["local_decay_law"] = {
        "a0_rad_per_s": float(res.x[0]),
        "beta_1_per_s": float(res.x[1]),
        "q_1_per_rad_s": float(res.x[2]),
        "rmse_rad_per_s": float(np.sqrt(np.mean((pred_decay + dadt) ** 2))),
        "t_mid_s": t_mid.tolist(),
        "amp_mid_rad": a_mid.tolist(),
        "observed_minus_dA_dt_rad_per_s": (-dadt).tolist(),
        "pred_minus_dA_dt_rad_per_s": pred_decay.tolist(),
    }
    return models


def fit_force_law(t, theta):
    dt = float(np.median(np.diff(t)))
    # Smooth over about 0.4 s, enough to suppress tracking noise while keeping a few samples per period.
    window = int(round(0.41 / dt))
    if window % 2 == 0:
        window += 1
    window = max(21, min(window, len(theta) // 4 * 2 - 1))
    th = savgol_filter(theta, window, polyorder=3)
    omega = savgol_filter(theta, window, polyorder=3, deriv=1, delta=dt)
    alpha = savgol_filter(theta, window, polyorder=3, deriv=2, delta=dt)

    # Equation: alpha + g/L sin(theta) = -b1 omega - b2 omega|omega| - ac sign(omega)
    y = -(alpha + (G / L_M) * np.sin(th))
    X = np.column_stack([omega, omega * np.abs(omega), np.sign(omega)])
    mask = np.isfinite(y) & np.all(np.isfinite(X), axis=1) & (np.abs(omega) > 0.08)
    # Remove first/last smoothing margins.
    margin = window
    mask[:margin] = False
    mask[-margin:] = False
    # Nonnegative damping coefficients.
    res = lsq_linear(X[mask], y[mask], bounds=(0, np.inf))
    pred = X @ res.x
    rmse = float(np.sqrt(np.mean((pred[mask] - y[mask]) ** 2)))
    b1, b2, ac = [float(v) for v in res.x]
    return {
        "savgol_window_samples": int(window),
        "linear_angular_damping_b1_1_per_s": b1,
        "quadratic_angular_damping_b2_1_per_rad": b2,
        "coulomb_angular_accel_ac_rad_per_s2": ac,
        "linear_torque_c_N_m_s": b1 * I,
        "quadratic_torque_k_N_m_s2": b2 * I,
        "coulomb_torque_tau0_N_m": ac * I,
        "rmse_rad_per_s2": rmse,
        "used_points": int(mask.sum()),
    }


def write_extrema(t, theta):
    sig = theta - np.mean(theta)
    min_dist = int(0.25 / np.median(np.diff(t)))
    p_idx, _ = find_peaks(sig, distance=min_dist)
    n_idx, _ = find_peaks(-sig, distance=min_dist)
    idx = np.sort(np.r_[p_idx, n_idx])
    rows = []
    for i in idx:
        rows.append((float(t[i]), float(theta[i]), float(abs(sig[i])), "peak" if i in set(p_idx) else "trough"))
    with TABLE.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "theta_rad", "amplitude_rad", "kind"])
        w.writerows(rows)
    return np.array([r[0] for r in rows]), np.array([r[2] for r in rows]), rows


def plot(t, theta, envelope_models, path):
    img = Image.new("RGB", (1400, 820), (248, 247, 242))
    d = ImageDraw.Draw(img)
    d.text((70, 34), "Nonlinear damping fit from single-pendulum envelope", fill=(30, 30, 30), font=font(25))
    box = (90, 110, 1320, 650)
    d.rectangle(box, outline=(40, 40, 40))
    data = envelope_models["linear_viscous"]
    tf = np.array(data["t_fit_s"])
    af = np.array(data["amp_fit_rad"])
    xlim = (0, float(tf[-1]))
    ylim = (0, float(np.max(af) * 1.15))

    def pt(x, y):
        l, tt, r, b = box
        return (
            int(l + (x - xlim[0]) / (xlim[1] - xlim[0]) * (r - l)),
            int(b - (y - ylim[0]) / (ylim[1] - ylim[0]) * (b - tt)),
        )

    for gx in np.linspace(0, xlim[1], 8):
        px, _ = pt(gx, 0)
        d.line((px, box[1], px, box[3]), fill=(225, 222, 215))
        d.text((px - 16, box[3] + 10), f"{gx:.0f}", fill=(80, 80, 80), font=font(14))
    for gy in np.linspace(0, ylim[1], 6):
        _, py = pt(0, gy)
        d.line((box[0], py, box[2], py), fill=(225, 222, 215))
        d.text((35, py - 7), f"{gy:.2f}", fill=(80, 80, 80), font=font(14))

    obs = [pt(x, y) for x, y in zip(tf, af)]
    for p in obs:
        d.ellipse((p[0] - 2, p[1] - 2, p[0] + 2, p[1] + 2), fill=(40, 40, 40))
    colors = {
        "linear_viscous": (40, 112, 185),
        "coulomb_constant_torque": (214, 72, 60),
        "quadratic_drag_envelope": (48, 150, 102),
        "mixed_linear_quadratic": (190, 132, 35),
    }
    labels = {
        "linear_viscous": "linear",
        "coulomb_constant_torque": "constant torque",
        "quadratic_drag_envelope": "quadratic",
        "mixed_linear_quadratic": "linear + quadratic",
    }
    y_legend = 690
    for k, col in colors.items():
        model = envelope_models[k]
        pts = [pt(x, y) for x, y in zip(model["t_fit_s"], model["pred_rad"])]
        d.line(pts, fill=col, width=3)
        d.rectangle((100, y_legend, 118, y_legend + 10), fill=col)
        d.text((126, y_legend - 4), f"{labels[k]}  RMSE={model['rmse_rad']:.4f} rad", fill=(50, 50, 50), font=font(14))
        y_legend += 25
    d.text((620, 760), "time / s", fill=(70, 70, 70), font=font(15))
    d.text((22, 96), "amplitude / rad", fill=(70, 70, 70), font=font(15))
    img.save(path)


def main():
    t, theta = load_theta()
    t_ext, amp_ext, rows = write_extrema(t, theta)
    envelope_models = fit_envelope_models(t_ext, amp_ext)
    force_model = fit_force_law(t, theta)
    plot(t, theta, envelope_models, FIG)
    best = min(
        [k for k in envelope_models if k != "local_decay_law"],
        key=lambda k: envelope_models[k]["rmse_rad"],
    )
    summary = {
        "input_theta_csv": str(IN_THETA),
        "length_m_used": L_M,
        "mass_kg_used": MASS_KG,
        "inertia_kg_m2": I,
        "best_envelope_model": best,
        "envelope_models": envelope_models,
        "direct_force_law_fit": force_model,
        "extrema_csv": str(TABLE),
        "figure": str(FIG),
        "model_forms": {
            "linear_viscous": "A(t)=A0 exp(-beta t)",
            "coulomb_constant_torque": "A(t)=max(A0-s t,0)",
            "quadratic_drag_envelope": "A(t)=A0/(1+q A0 t)",
            "mixed_linear_quadratic": "dA/dt=-beta A-q A^2",
            "direct_force_law": "theta'' + g/L sin(theta) = -b1 theta' - b2 theta'|theta'| - ac sign(theta')",
        },
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "best_envelope_model": best,
        "linear_beta_1_per_s": envelope_models["linear_viscous"]["params"][1],
        "mixed_beta_1_per_s": envelope_models["mixed_linear_quadratic"]["params"][1],
        "mixed_q_1_per_rad_s": envelope_models["mixed_linear_quadratic"]["params"][2],
        "local_decay_law": envelope_models["local_decay_law"],
        "direct_force_law_fit": force_model,
        "summary": str(SUMMARY),
        "figure": str(FIG),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
