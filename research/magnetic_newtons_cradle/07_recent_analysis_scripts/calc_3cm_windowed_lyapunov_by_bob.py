from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

try:
    from scipy.spatial import cKDTree
except Exception as exc:  # pragma: no cover
    raise SystemExit("This script needs scipy.spatial.cKDTree") from exc


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "04_data_outputs" / "time_frequency_all_5_bobs" / "all_5_bobs_cleaned_detrended_proxy.csv"
OUT_DIR = ROOT / "04_data_outputs" / "chaos_evidence_3cm"
FIG_DIR = ROOT / "03_key_figures" / "chaos_evidence_3cm"


def zscore(x):
    x = np.asarray(x, dtype=float)
    s = np.nanstd(x)
    return (x - np.nanmean(x)) / s if s > 0 else x - np.nanmean(x)


def autocorr(x, max_lag):
    x = zscore(x)
    out = np.empty(max_lag + 1)
    out[0] = 1.0
    for lag in range(1, max_lag + 1):
        a = x[:-lag]
        b = x[lag:]
        den = np.sqrt(np.dot(a, a) * np.dot(b, b))
        out[lag] = np.dot(a, b) / den if den > 0 else np.nan
    return out


def choose_delay_seconds(t, x, min_tau_s=0.08, max_tau_s=0.25):
    dt = float(np.median(np.diff(t)))
    max_lag = max(3, int(2.0 / dt))
    ac = autocorr(x, max_lag)
    below = np.where(ac < 1 / np.e)[0]
    tau = int(below[0]) if len(below) else max(1, int(0.13 / dt))
    tau_s = tau * dt
    tau_s = min(max(tau_s, min_tau_s), max_tau_s)
    return max(1, int(round(tau_s / dt)))


def embed(x, dim, tau):
    n = len(x) - (dim - 1) * tau
    if n <= 10:
        return np.empty((0, dim))
    return np.column_stack([x[i * tau:i * tau + n] for i in range(dim)])


def rosenstein_lambda_fast(t, x, dim=3, tau=None, theiler_s=0.8, fit_s=(0.20, 1.60), max_t_s=3.0):
    dt = float(np.median(np.diff(t)))
    if tau is None:
        tau = choose_delay_seconds(t, x)
    y = embed(zscore(x), dim, tau)
    n = len(y)
    if n < 120:
        return np.nan, tau * dt

    theiler = max(1, int(round(theiler_s / dt)))
    max_k = min(int(round(max_t_s / dt)), n // 4)
    if max_k < 8:
        return np.nan, tau * dt

    tree = cKDTree(y)
    k_query = min(80, n)
    dists, idxs = tree.query(y, k=k_query)
    nn = np.full(n, -1, dtype=int)
    for i in range(n):
        candidates = np.atleast_1d(idxs[i])
        distances = np.atleast_1d(dists[i])
        ok = (np.abs(candidates - i) > theiler) & np.isfinite(distances) & (distances > 1e-12)
        if np.any(ok):
            nn[i] = int(candidates[np.argmax(ok)])

    valid = np.where(nn >= 0)[0]
    div_t = []
    div_y = []
    for k in range(max_k):
        i_ok = valid[(valid + k < n) & (nn[valid] + k < n)]
        if len(i_ok) < 20:
            continue
        sep = np.linalg.norm(y[i_ok + k] - y[nn[i_ok] + k], axis=1)
        sep = sep[sep > 1e-12]
        if len(sep) < 20:
            continue
        div_t.append(k * dt)
        div_y.append(float(np.mean(np.log(sep))))

    div_t = np.asarray(div_t)
    div_y = np.asarray(div_y)
    fit = (div_t >= fit_s[0]) & (div_t <= fit_s[1])
    if np.sum(fit) < 4:
        return np.nan, tau * dt
    slope, _ = np.polyfit(div_t[fit], div_y[fit], 1)
    return float(slope), tau * dt


def windowed_lambda(df, window_s=30.0, step_s=5.0):
    t_all = df["t_s"].to_numpy(float)
    cols = [c for c in df.columns if c != "t_s"]
    start = float(t_all[0])
    stop = float(t_all[-1] - window_s)
    rows = []
    for left in np.arange(start, stop + 1e-9, step_s):
        right = left + window_s
        mask = (t_all >= left) & (t_all < right)
        if np.sum(mask) < 300:
            continue
        t = t_all[mask] - t_all[mask][0]
        row = {
            "window_start_s": left,
            "window_center_s": left + window_s / 2,
            "window_end_s": right,
        }
        for col in cols:
            lam, tau_s = rosenstein_lambda_fast(t, df.loc[mask, col].to_numpy(float))
            row[col.replace("_proxy", "") + "_lambda_s_inv"] = lam
            row[col.replace("_proxy", "") + "_tau_s"] = tau_s
        rows.append(row)
    return pd.DataFrame(rows)


def make_plot(out):
    lambda_cols = [c for c in out.columns if c.endswith("_lambda_s_inv")]
    fig, ax = plt.subplots(figsize=(11, 5.6))
    colors = ["#2d6cdf", "#f28e2b", "#59a14f", "#e15759", "#7b61b8"]
    for col, color in zip(lambda_cols, colors):
        label = col.replace("_lambda_s_inv", "")
        ax.plot(out["window_center_s"], out[col], marker="o", ms=3.5, lw=1.35, label=label, color=color)
    ax.axhline(0, color="black", lw=1.0, alpha=0.75)
    ax.set_title("3 cm experiment: windowed finite-time Lyapunov estimate")
    ax.set_xlabel("window center time / s")
    ax.set_ylabel("lambda / s^-1")
    ax.grid(alpha=0.28)
    ax.legend(ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.12), frameon=False)
    fig.tight_layout()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / "windowed_lyapunov_3cm_all_bobs.png", dpi=190, bbox_inches="tight")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(DATA)
    out = windowed_lambda(df, window_s=30.0, step_s=5.0)
    out_path = OUT_DIR / "windowed_lyapunov_3cm_all_bobs.csv"
    out.to_csv(out_path, index=False, encoding="utf-8-sig")
    make_plot(out)

    lambda_cols = [c for c in out.columns if c.endswith("_lambda_s_inv")]
    summary = []
    for col in lambda_cols:
        vals = out[col].dropna().to_numpy(float)
        summary.append({
            "bob": col.replace("_lambda_s_inv", ""),
            "lambda_mean_s_inv": np.mean(vals),
            "lambda_median_s_inv": np.median(vals),
            "lambda_max_s_inv": np.max(vals),
            "positive_window_fraction": np.mean(vals > 0),
        })
    summary = pd.DataFrame(summary)
    summary_path = OUT_DIR / "windowed_lyapunov_3cm_all_bobs_summary.csv"
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    print(summary.to_string(index=False, float_format=lambda v: f"{v:.5f}"))
    print(out_path)
    print(summary_path)


if __name__ == "__main__":
    main()
