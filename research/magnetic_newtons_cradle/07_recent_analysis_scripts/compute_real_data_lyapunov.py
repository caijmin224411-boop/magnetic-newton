from pathlib import Path

import numpy as np
import pandas as pd

try:
    from scipy import signal
    from scipy.spatial import cKDTree
except Exception as exc:  # pragma: no cover
    raise SystemExit("This script needs scipy") from exc


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "04_data_outputs" / "real_data_lyapunov_recheck"


def zscore(x):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    s = np.nanstd(x)
    if s <= 0:
        return x - np.nanmean(x)
    return (x - np.nanmean(x)) / s


def autocorr(x, max_lag):
    x = zscore(x)
    max_lag = min(max_lag, len(x) - 2)
    out = np.empty(max_lag + 1)
    out[0] = 1.0
    for lag in range(1, max_lag + 1):
        a = x[:-lag]
        b = x[lag:]
        den = np.sqrt(np.dot(a, a) * np.dot(b, b))
        out[lag] = np.dot(a, b) / den if den > 0 else np.nan
    return out


def dominant_period_s(t, x, fmin=0.25, fmax=6.0):
    dt = float(np.median(np.diff(t)))
    y = signal.detrend(np.asarray(x, dtype=float), type="linear")
    y = y - np.mean(y)
    win = np.hanning(len(y))
    freq = np.fft.rfftfreq(len(y), dt)
    amp = np.abs(np.fft.rfft(y * win))
    mask = (freq >= fmin) & (freq <= fmax)
    if not np.any(mask):
        return 1.0, np.nan
    f0 = float(freq[mask][np.argmax(amp[mask])])
    return 1.0 / f0, f0


def choose_delay(t, x, min_tau_s=0.06, max_tau_s=0.25):
    dt = float(np.median(np.diff(t)))
    ac = autocorr(x, max(4, int(round(2.0 / dt))))
    below = np.where(ac < 1 / np.e)[0]
    tau = int(below[0]) if len(below) else max(1, int(round(0.12 / dt)))
    tau_s = np.clip(tau * dt, min_tau_s, max_tau_s)
    return max(1, int(round(tau_s / dt)))


def embed(x, dim, tau):
    x = zscore(x)
    n = len(x) - (dim - 1) * tau
    if n <= 10:
        return np.empty((0, dim))
    return np.column_stack([x[i * tau:i * tau + n] for i in range(dim)])


def rosenstein_curve(t, x, dim=3, tau=None, theiler_s=None, max_t_s=3.0):
    t = np.asarray(t, dtype=float)
    x = np.asarray(x, dtype=float)
    ok = np.isfinite(t) & np.isfinite(x)
    t = t[ok]
    x = x[ok]
    order = np.argsort(t)
    t = t[order]
    x = x[order]
    dt = float(np.median(np.diff(t)))
    if tau is None:
        tau = choose_delay(t, x)
    if theiler_s is None:
        period_s, _ = dominant_period_s(t, x)
        theiler_s = float(np.clip(0.8 * period_s, 0.35, 1.2))

    y = embed(x, dim, tau)
    n = len(y)
    if n < 200:
        return None

    theiler = max(1, int(round(theiler_s / dt)))
    max_k = min(int(round(max_t_s / dt)), n // 4)
    tree = cKDTree(y)
    k_query = min(100, n)
    dists, idxs = tree.query(y, k=k_query)
    nn = np.full(n, -1, dtype=int)
    for i in range(n):
        candidates = np.atleast_1d(idxs[i])
        distances = np.atleast_1d(dists[i])
        valid = (np.abs(candidates - i) > theiler) & np.isfinite(distances) & (distances > 1e-12)
        if np.any(valid):
            nn[i] = int(candidates[np.where(valid)[0][0]])

    base = np.where(nn >= 0)[0]
    div_t = []
    div_y = []
    n_pairs = []
    for k in range(max_k):
        ii = base[(base + k < n) & (nn[base] + k < n)]
        if len(ii) < 50:
            continue
        sep = np.linalg.norm(y[ii + k] - y[nn[ii] + k], axis=1)
        sep = sep[sep > 1e-12]
        if len(sep) < 50:
            continue
        div_t.append(k * dt)
        div_y.append(float(np.mean(np.log(sep))))
        n_pairs.append(len(sep))

    return {
        "dt_s": dt,
        "tau_samples": tau,
        "tau_s": tau * dt,
        "theiler_s": theiler_s,
        "curve_t_s": np.asarray(div_t),
        "curve_log_div": np.asarray(div_y),
        "n_pairs": np.asarray(n_pairs),
    }


def fit_lambda(curve, fit_s):
    tt = curve["curve_t_s"]
    yy = curve["curve_log_div"]
    mask = (tt >= fit_s[0]) & (tt <= fit_s[1]) & np.isfinite(yy)
    if np.sum(mask) < 6:
        return np.nan, np.nan, np.nan
    slope, intercept = np.polyfit(tt[mask], yy[mask], 1)
    pred = slope * tt[mask] + intercept
    ss_res = float(np.sum((yy[mask] - pred) ** 2))
    ss_tot = float(np.sum((yy[mask] - np.mean(yy[mask])) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return float(slope), float(intercept), float(r2)


def analyze_series(case, signal_name, t, x, fit_s=(0.20, 1.50), dim=3):
    curve = rosenstein_curve(t, x, dim=dim)
    if curve is None:
        return None, None
    lam, intercept, r2 = fit_lambda(curve, fit_s)
    period_s, f0 = dominant_period_s(t, x)
    row = {
        "case": case,
        "signal": signal_name,
        "n_samples": int(len(t)),
        "duration_s": float(np.max(t) - np.min(t)),
        "dominant_frequency_Hz": f0,
        "dominant_period_s": period_s,
        "embedding_dim": dim,
        "tau_s": curve["tau_s"],
        "theiler_s": curve["theiler_s"],
        "fit_start_s": fit_s[0],
        "fit_end_s": fit_s[1],
        "lambda_s_inv": lam,
        "fit_r2": r2,
    }
    curve_df = pd.DataFrame({
        "t_s": curve["curve_t_s"],
        "mean_log_separation": curve["curve_log_div"],
        "n_pairs": curve["n_pairs"],
    })
    return row, curve_df


def load_cases():
    cases = []

    p3 = ROOT / "04_data_outputs" / "time_frequency_all_5_bobs" / "all_5_bobs_cleaned_detrended_proxy.csv"
    if p3.exists():
        df = pd.read_csv(p3)
        cols = [c for c in df.columns if c != "t_s"]
        cases.append(("3cm_real_all_bobs", df, cols))

    p5 = ROOT / "04_data_outputs" / "time_frequency_spacing_5cm" / "spacing_5cm_cleaned_detrended_proxy.csv"
    if p5.exists():
        df = pd.read_csv(p5)
        cols = [c for c in df.columns if c != "t_s"]
        cases.append(("5cm_70mT_real_all_bobs", df, cols))

    p_edge = ROOT / "04_data_outputs" / "edge_bob_70mT_5cm" / "70mT_5cm_edge_bob5_cleaned_proxy.csv"
    if p_edge.exists():
        df = pd.read_csv(p_edge)
        cases.append(("5cm_70mT_real_edge_bob5", df.rename(columns={"edge_bob5_proxy_displacement": "bob5_edge"}), ["bob5_edge"]))

    p120 = ROOT / "04_data_outputs" / "fourier_120mT_A_only" / "120mT_A_only_cleaned_pca_signal.csv"
    if p120.exists():
        df = pd.read_csv(p120).rename(columns={"time_s": "t_s", "pca_displacement_clean": "A_pca"})
        cases.append(("120mT_real_A_bob", df, ["A_pca"]))

    return cases


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for case, df, cols in load_cases():
        t = df["t_s"].to_numpy(float)
        for col in cols:
            row, curve_df = analyze_series(case, col, t - t[0], df[col].to_numpy(float))
            if row is None:
                continue
            rows.append(row)
            safe = f"{case}_{col}".replace("/", "_").replace("\\", "_").replace(" ", "_")
            curve_df.to_csv(OUT_DIR / f"{safe}_rosenstein_curve.csv", index=False, encoding="utf-8-sig")

    summary = pd.DataFrame(rows)
    summary.to_csv(OUT_DIR / "real_data_rosenstein_lyapunov_summary.csv", index=False, encoding="utf-8-sig")

    # Compact table for reporting.
    compact_cols = [
        "case", "signal", "duration_s", "dominant_frequency_Hz", "tau_s",
        "theiler_s", "lambda_s_inv", "fit_r2",
    ]
    compact = summary[compact_cols].copy()
    compact.to_csv(OUT_DIR / "real_data_lyapunov_compact_table.csv", index=False, encoding="utf-8-sig")
    print(compact.to_string(index=False, float_format=lambda v: f"{v:.5f}"))
    print(OUT_DIR)


if __name__ == "__main__":
    main()
