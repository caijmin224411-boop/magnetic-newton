import csv
import math
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
FORCE_TABLE = ROOT / "04_data_outputs" / "force_table_measured_70mT_disk_2d.csv"
OUT = ROOT / "04_data_outputs" / "nonlocal_coupling_sweep"
FIG = ROOT / "03_key_figures" / "nonlocal_coupling_sweep_frequency_envelope.png"

N = 5
G = 9.81


def read_force_table(path):
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append((
                float(row["gap_m"]),
                float(row["offset_m"]),
                float(row["force_axial_N"]),
                float(row["force_lateral_N"]),
            ))
    gaps = sorted({r[0] for r in rows})
    offsets = sorted({r[1] for r in rows})
    axial = np.zeros((len(gaps), len(offsets)))
    lateral = np.zeros_like(axial)
    gi = {v: i for i, v in enumerate(gaps)}
    oi = {v: i for i, v in enumerate(offsets)}
    for gap, offset, fax, flat in rows:
        axial[gi[gap], oi[offset]] = fax
        lateral[gi[gap], oi[offset]] = flat
    return np.array(gaps), np.array(offsets), axial, lateral


GAPS, OFFSETS, AXIAL_TABLE, LATERAL_TABLE = read_force_table(FORCE_TABLE)


def interp2(gap, offset, table, min_gap):
    gap = float(np.clip(gap, min_gap, GAPS[-1]))
    offset = float(np.clip(abs(offset), OFFSETS[0], OFFSETS[-1]))
    i = int(np.clip(np.searchsorted(GAPS, gap) - 1, 0, len(GAPS) - 2))
    j = int(np.clip(np.searchsorted(OFFSETS, offset) - 1, 0, len(OFFSETS) - 2))
    gx = (gap - GAPS[i]) / (GAPS[i + 1] - GAPS[i])
    oy = (offset - OFFSETS[j]) / (OFFSETS[j + 1] - OFFSETS[j])
    return (
        (1 - gx) * (1 - oy) * table[i, j]
        + gx * (1 - oy) * table[i + 1, j]
        + (1 - gx) * oy * table[i, j + 1]
        + gx * oy * table[i + 1, j + 1]
    )


def pivot_x(p):
    return (np.arange(1, N + 1) - (N + 1) / 2.0) * p["spacing"]


def centers(theta, p):
    px = pivot_x(p)
    L = p["L"]
    return px + L * np.sin(theta), -L * np.cos(theta)


def acceleration(state, p, weights):
    theta = state[:N]
    omega = state[N:]
    px = pivot_x(p)
    x, y = centers(theta, p)
    a = np.zeros(N, dtype=float)
    m, L = p["m"], p["L"]
    for i in range(N):
        rx = x[i] - px[i]
        ry = y[i]
        tau = (
            -m * G * L * math.sin(theta[i])
            - p["c1"] * omega[i]
            - p["c2"] * omega[i] * abs(omega[i])
        )
        for j in range(N):
            if i == j:
                continue
            order = abs(i - j)
            w = weights.get(order, 0.0)
            if w == 0:
                continue
            dx = x[i] - x[j]
            dy = y[i] - y[j]
            gap = abs(dx) - 2 * p["r"]
            fax = abs(interp2(gap, abs(dy), AXIAL_TABLE, p["min_gap"]))
            flat = abs(interp2(gap, abs(dy), LATERAL_TABLE, p["min_gap"]))
            fx = p["scale"] * w * (math.copysign(fax, dx) if abs(dx) > 1e-12 else 0.0)
            fy = p["scale"] * w * (math.copysign(flat, dy) if abs(dy) > 1e-12 else 0.0)
            tau += rx * fy - ry * fx
        a[i] = tau / (m * L * L)
    return a


def rhs(state, p, weights):
    return np.r_[state[N:], acceleration(state, p, weights)]


def rk4_step(state, dt, p, weights):
    k1 = rhs(state, p, weights)
    k2 = rhs(state + 0.5 * dt * k1, p, weights)
    k3 = rhs(state + 0.5 * dt * k2, p, weights)
    k4 = rhs(state + dt * k3, p, weights)
    return state + dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6.0


def moving_average(a, n):
    n = max(3, int(n))
    if n % 2 == 0:
        n += 1
    pad = n // 2
    return np.convolve(np.pad(a, (pad, pad), mode="edge"), np.ones(n) / n, mode="valid")


def fft_peaks(t, x, fmin=0.2, fmax=8.0, n=8, min_sep=0.12):
    t = np.asarray(t, float)
    x = np.asarray(x, float)
    dt = float(np.median(np.diff(t)))
    z = x - np.mean(x)
    f = np.fft.rfftfreq(len(z), dt)
    a = np.abs(np.fft.rfft(z * np.hanning(len(z))))
    mask = (f >= fmin) & (f <= fmax)
    ff = f[mask]
    aa = a[mask]
    if len(ff) < 3 or aa.max() <= 0:
        return []
    cand = []
    for i in range(1, len(aa) - 1):
        if aa[i] > aa[i - 1] and aa[i] > aa[i + 1] and aa[i] > 0.015 * aa.max():
            cand.append((float(ff[i]), float(aa[i])))
    cand = sorted(cand, key=lambda p: p[1], reverse=True)
    chosen = []
    for fr, amp in cand:
        if all(abs(fr - cf) >= min_sep for cf, _ in chosen):
            chosen.append((fr, amp))
        if len(chosen) >= n:
            break
    if not chosen:
        return []
    maxamp = max(a for _, a in chosen)
    return [{"freq_Hz": fr, "rel_amp": amp / maxamp} for fr, amp in chosen]


def envelope_peaks(t, x, carrier_window_s=0.45, drift_window_s=6.0, n=5):
    dt = float(np.median(np.diff(t)))
    z = x - np.mean(x)
    env = np.sqrt(np.maximum(moving_average(z * z, int(round(carrier_window_s / dt))), 0))
    env = env - moving_average(env, int(round(drift_window_s / dt)))
    return fft_peaks(t, env, fmin=0.05, fmax=2.0, n=n, min_sep=0.08)


def simulate(weights, duration=40.0, sim_hz=160.0, save_time_domain=False, label=""):
    p = {
        "spacing": 0.03,
        "L": 0.11878,
        "m": 0.070,
        "scale": 0.5,
        "c1": 2.833954997868876e-05,
        "c2": 6.541910366771381e-06,
        "r": 0.015,
        "min_gap": 0.002,
    }
    # Same measured-release-like initial condition used by the existing 3 cm comparison model.
    theta0 = np.array([-1.233560308, -0.1611050574, 0.0, 0.1611050574, 0.3608956817])
    state = np.r_[theta0, np.zeros(N)]
    dt = 1.0 / sim_hz
    steps = int(duration * sim_hz)
    stride = max(1, int(round(sim_hz / 60.0)))
    ts = []
    thetas = []
    for step in range(steps + 1):
        if step % stride == 0:
            ts.append(step * dt)
            thetas.append(state[:N].copy())
        state = rk4_step(state, dt, p, weights)
    t = np.array(ts)
    theta = np.array(thetas)
    if save_time_domain:
        cols = {"t_s": t}
        for i in range(N):
            cols[f"theta{i+1}"] = theta[:, i]
        pd.DataFrame(cols).to_csv(OUT / f"{label}_time_domain.csv", index=False)
    return t, theta


EXP_TARGETS = {
    "edge": {"bob": 1, "freqs": [2.208, 1.389, 3.292], "env": 0.818},
    "second": {"bob": 2, "freqs": [1.396, 2.216, 4.599], "env": 0.819},
    "middle": {"bob": 3, "freqs": [3.234, 1.366, 5.903], "env": 0.299},
}


def nearest_error(model_freqs, exp_freqs):
    errs = []
    for ef in exp_freqs:
        if not model_freqs:
            continue
        nearest = min(model_freqs, key=lambda f: abs(f - ef))
        errs.append(abs(nearest - ef))
    return float(np.mean(errs)) if errs else float("nan")


def analyze_variant(name, weights, save_time_domain=False):
    t, theta = simulate(weights, save_time_domain=save_time_domain, label=name)
    rows = []
    score_parts = []
    for role, target in EXP_TARGETS.items():
        sig = theta[:, target["bob"] - 1]
        fp = fft_peaks(t, sig)
        ep = envelope_peaks(t, sig)
        model_freqs = [p["freq_Hz"] for p in fp[:8]]
        model_envs = [p["freq_Hz"] for p in ep[:5]]
        freq_err = nearest_error(model_freqs, target["freqs"])
        env_err = abs(model_envs[0] - target["env"]) if model_envs else float("nan")
        score_parts.append(freq_err)
        if math.isfinite(env_err):
            score_parts.append(0.5 * env_err)
        rows.append({
            "variant": name,
            "role": role,
            "w1": weights.get(1, 0.0),
            "w2": weights.get(2, 0.0),
            "w3": weights.get(3, 0.0),
            "w4": weights.get(4, 0.0),
            "model_main_freqs_Hz": "; ".join(f"{f:.3f}" for f in model_freqs[:6]),
            "model_envelope_Hz": "; ".join(f"{f:.3f}" for f in model_envs[:5]),
            "experiment_target_freqs_Hz": "; ".join(f"{f:.3f}" for f in target["freqs"]),
            "experiment_target_env_Hz": target["env"],
            "mean_freq_error_Hz": freq_err,
            "dominant_env_error_Hz": env_err,
        })
    score = float(np.nanmean(score_parts))
    return rows, score


def font(size, bold=False):
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            pass
    return ImageFont.load_default()


def make_figure(summary, best_rows):
    W, H = 1600, 980
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    title = font(34, True)
    head = font(22, True)
    body = font(17)
    small = font(14)
    d.text((50, 35), "Non-neighbor magnetic coupling sweep, 3 cm, scale=0.5", fill=(20, 30, 40), font=title)
    d.text((52, 82), "w2 opens next-neighbor coupling; w3 opens third-neighbor coupling. Distance decay is still handled by the force table.", fill=(80, 80, 80), font=body)

    x0, y0 = 55, 130
    cols = [("variant", 210), ("w2", 70), ("w3", 70), ("score", 90), ("edge env", 120), ("second env", 130), ("middle env", 130), ("edge freq err", 140), ("second freq err", 150), ("middle freq err", 150)]
    x = x0
    for name, w in cols:
        d.rectangle((x, y0, x + w, y0 + 42), fill=(235, 239, 244), outline=(180, 185, 195))
        d.text((x + 7, y0 + 10), name, fill=(25, 30, 40), font=small)
        x += w
    for i, row in enumerate(summary):
        y = y0 + 42 + i * 42
        fill = (250, 250, 250) if i % 2 == 0 else (244, 247, 250)
        values = [
            row["variant"], f'{row["w2"]:.2f}', f'{row["w3"]:.2f}', f'{row["score"]:.3f}',
            f'{row["edge_env"]:.3f}', f'{row["second_env"]:.3f}', f'{row["middle_env"]:.3f}',
            f'{row["edge_freq_err"]:.3f}', f'{row["second_freq_err"]:.3f}', f'{row["middle_freq_err"]:.3f}',
        ]
        x = x0
        for value, (_, w) in zip(values, cols):
            d.rectangle((x, y, x + w, y + 42), fill=fill, outline=(212, 216, 222))
            d.text((x + 7, y + 11), value, fill=(30, 35, 45), font=small)
            x += w

    by_role = {r["role"]: r for r in best_rows}
    d.text((60, 640), "Best variant detailed frequencies", fill=(20, 30, 40), font=head)
    detail_cols = [("role", 120), ("experiment target Hz", 260), ("model main Hz", 360), ("experiment env Hz", 170), ("model envelope Hz", 360)]
    x, y = 60, 690
    for name, w in detail_cols:
        d.rectangle((x, y, x + w, y + 38), fill=(235, 239, 244), outline=(180, 185, 195))
        d.text((x + 8, y + 9), name, fill=(25, 30, 40), font=small)
        x += w
    for i, role in enumerate(["edge", "second", "middle"]):
        row = by_role[role]
        vals = [
            role,
            row["experiment_target_freqs_Hz"],
            row["model_main_freqs_Hz"],
            f'{row["experiment_target_env_Hz"]:.3f}',
            row["model_envelope_Hz"],
        ]
        x = 60
        yy = 728 + i * 58
        for val, (_, w) in zip(vals, detail_cols):
            d.rectangle((x, yy, x + w, yy + 58), fill=(250, 250, 250), outline=(212, 216, 222))
            d.text((x + 8, yy + 10), str(val)[:52], fill=(30, 35, 45), font=small)
            x += w

    d.text((60, 925), "Lower score is better. The sweep tests whether non-neighbor coupling moves beat/envelope structure toward experiment without changing scale=0.5.", fill=(70, 70, 70), font=body)
    img.save(FIG)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.parent.mkdir(parents=True, exist_ok=True)
    variants = [
        ("nearest_only", {1: 1.0, 2: 0.0, 3: 0.0, 4: 0.0}),
        ("next_0p50", {1: 1.0, 2: 0.50, 3: 0.0, 4: 0.0}),
        ("next_1p00", {1: 1.0, 2: 1.00, 3: 0.0, 4: 0.0}),
        ("next_1p00_third_0p50", {1: 1.0, 2: 1.00, 3: 0.50, 4: 0.0}),
        ("all_physical", {1: 1.0, 2: 1.00, 3: 1.00, 4: 1.00}),
    ]
    all_rows = []
    scores = []
    for name, weights in variants:
        rows, score = analyze_variant(name, weights, save_time_domain=(name == "next_1p00"))
        all_rows.extend(rows)
        scores.append({"variant": name, "score": score, "w2": weights.get(2, 0.0), "w3": weights.get(3, 0.0), "w4": weights.get(4, 0.0)})
    df = pd.DataFrame(all_rows)
    df.to_csv(OUT / "nonlocal_coupling_sweep_by_role.csv", index=False, encoding="utf-8-sig")
    summary = []
    for item in scores:
        sub = df[df["variant"] == item["variant"]]
        role_map = {r["role"]: r for r in sub.to_dict("records")}
        summary.append({
            **item,
            "edge_env": float(role_map["edge"]["model_envelope_Hz"].split("; ")[0]),
            "second_env": float(role_map["second"]["model_envelope_Hz"].split("; ")[0]),
            "middle_env": float(role_map["middle"]["model_envelope_Hz"].split("; ")[0]),
            "edge_freq_err": role_map["edge"]["mean_freq_error_Hz"],
            "second_freq_err": role_map["second"]["mean_freq_error_Hz"],
            "middle_freq_err": role_map["middle"]["mean_freq_error_Hz"],
        })
    summary_df = pd.DataFrame(summary).sort_values("score")
    summary_df.to_csv(OUT / "nonlocal_coupling_sweep_summary.csv", index=False, encoding="utf-8-sig")
    best = summary_df.iloc[0]["variant"]
    best_rows = df[df["variant"] == best].to_dict("records")
    make_figure(summary_df.to_dict("records"), best_rows)
    print("best", best)
    print(summary_df.to_string(index=False))
    print(OUT / "nonlocal_coupling_sweep_summary.csv")
    print(OUT / "nonlocal_coupling_sweep_by_role.csv")
    print(FIG)


if __name__ == "__main__":
    main()
