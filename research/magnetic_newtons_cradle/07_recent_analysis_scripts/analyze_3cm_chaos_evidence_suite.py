from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "04_data_outputs" / "time_frequency_all_5_bobs" / "all_5_bobs_cleaned_detrended_proxy.csv"
OUT_DIR = ROOT / "04_data_outputs" / "chaos_evidence_3cm"
FIG_DIR = ROOT / "03_key_figures" / "chaos_evidence_3cm"


def zscore(x):
    x = np.asarray(x, dtype=float)
    s = np.std(x)
    return (x - np.mean(x)) / s if s > 0 else x - np.mean(x)


def derivative(t, x):
    return np.gradient(x, t)


def autocorr(x, max_lag):
    x = zscore(x)
    out = []
    for lag in range(max_lag + 1):
        if lag == 0:
            out.append(1.0)
        else:
            a = x[:-lag]
            b = x[lag:]
            out.append(float(np.dot(a, b) / np.sqrt(np.dot(a, a) * np.dot(b, b))))
    return np.array(out)


def choose_delay(ac):
    below = np.where(ac < 1 / np.e)[0]
    if len(below):
        return int(below[0])
    return max(1, int(np.argmax(ac < 0.5)))


def embed(x, dim, tau):
    n = len(x) - (dim - 1) * tau
    return np.column_stack([x[i * tau:i * tau + n] for i in range(dim)])


def rosenstein_lyapunov(t, x, dim=3, tau=None, theiler_s=1.0, fit_s=(0.25, 2.0), max_t_s=5.0):
    dt = float(np.median(np.diff(t)))
    ac = autocorr(x, min(len(x) // 4, int(10 / dt)))
    if tau is None:
        tau = choose_delay(ac)
    y = embed(zscore(x), dim, tau)
    n = len(y)
    theiler = max(1, int(theiler_s / dt))
    max_k = min(int(max_t_s / dt), n // 4)
    nn = np.full(n, -1, dtype=int)
    for i in range(n):
        d = np.linalg.norm(y - y[i], axis=1)
        lo = max(0, i - theiler)
        hi = min(n, i + theiler + 1)
        d[lo:hi] = np.inf
        j = int(np.argmin(d))
        if np.isfinite(d[j]) and d[j] > 1e-12:
            nn[i] = j
    div = []
    ts = []
    for k in range(max_k):
        vals = []
        for i, j in enumerate(nn):
            if j < 0:
                continue
            if i + k < n and j + k < n:
                d = np.linalg.norm(y[i + k] - y[j + k])
                if d > 1e-12:
                    vals.append(np.log(d))
        if vals:
            div.append(float(np.mean(vals)))
            ts.append(k * dt)
    ts = np.array(ts)
    div = np.array(div)
    mask = (ts >= fit_s[0]) & (ts <= fit_s[1])
    if np.sum(mask) >= 3:
        slope, intercept = np.polyfit(ts[mask], div[mask], 1)
    else:
        slope, intercept = np.nan, np.nan
    return {
        "tau_samples": tau,
        "tau_s": tau * dt,
        "lambda_rosenstein_s_inv": float(slope),
        "fit_intercept": float(intercept),
        "curve_t_s": ts,
        "curve_log_div": div,
        "ac_lags": np.arange(len(ac)) * dt,
        "ac": ac,
    }


def zero_crossing_poincare(t, data, ref_col="bob3_proxy"):
    ref = data[ref_col].to_numpy(float)
    rows = []
    cols = [c for c in data.columns if c != "t_s"]
    for i in range(len(ref) - 1):
        if ref[i] < 0 <= ref[i + 1]:
            frac = -ref[i] / (ref[i + 1] - ref[i]) if ref[i + 1] != ref[i] else 0
            row = {"t_s": t[i] + frac * (t[i + 1] - t[i])}
            for c in cols:
                y = data[c].to_numpy(float)
                row[c] = y[i] + frac * (y[i + 1] - y[i])
            rows.append(row)
    return pd.DataFrame(rows)


def zero_one_test(x, n_c=60, seed=42):
    rng = np.random.default_rng(seed)
    x = zscore(x)
    n = len(x)
    j = np.arange(1, n + 1)
    ks = []
    for c in rng.uniform(0.2, np.pi - 0.2, n_c):
        p = np.cumsum(x * np.cos(j * c))
        q = np.cumsum(x * np.sin(j * c))
        max_lag = min(n // 10, 1000)
        msd = np.empty(max_lag)
        for lag in range(1, max_lag + 1):
            dp = p[lag:] - p[:-lag]
            dq = q[lag:] - q[:-lag]
            msd[lag - 1] = np.mean(dp * dp + dq * dq)
        lags = np.arange(1, max_lag + 1)
        if np.std(msd) > 0:
            k = np.corrcoef(lags, msd)[0, 1]
            if np.isfinite(k):
                ks.append(k)
    return float(np.median(ks)), np.array(ks)


def make_phase_and_poincare(df, poincare):
    t = df["t_s"].to_numpy(float)
    cols = [c for c in df.columns if c != "t_s"]
    fig, axes = plt.subplots(2, 3, figsize=(13, 7))
    axes = axes.ravel()
    for ax, col in zip(axes[:5], cols):
        x = zscore(df[col].to_numpy(float))
        v = derivative(t, x)
        ax.plot(x, v, lw=0.55, alpha=0.75)
        ax.set_title(col.replace("_proxy", ""))
        ax.set_xlabel("x / std")
        ax.set_ylabel("dx/dt")
        ax.grid(alpha=0.25)
    axes[5].scatter(poincare["bob1_proxy"], poincare["bob5_proxy"], s=10, alpha=0.75)
    axes[5].set_title("Poincare: bob3 upward zero crossing")
    axes[5].set_xlabel("bob1 proxy")
    axes[5].set_ylabel("bob5 proxy")
    axes[5].grid(alpha=0.25)
    fig.suptitle("3 cm experiment: phase portraits and Poincare section", fontsize=15)
    fig.tight_layout()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / "phase_poincare_3cm_chaos_check.png", dpi=180, bbox_inches="tight")


def make_delay_plot(t, x, lyap):
    tau = lyap["tau_samples"]
    y = embed(zscore(x), 3, tau)
    fig = plt.figure(figsize=(11, 4.5))
    ax1 = fig.add_subplot(1, 2, 1, projection="3d")
    ax1.plot(y[:, 0], y[:, 1], y[:, 2], lw=0.45, alpha=0.75)
    ax1.set_title(f"Delay embedding, tau={lyap['tau_s']:.3f}s")
    ax1.set_xlabel("x(t)")
    ax1.set_ylabel("x(t+tau)")
    ax1.set_zlabel("x(t+2tau)")
    ax2 = fig.add_subplot(1, 2, 2)
    ax2.plot(lyap["ac_lags"], lyap["ac"], lw=1.5)
    ax2.axhline(1 / np.e, color="r", ls="--", lw=1, label="1/e")
    ax2.axvline(lyap["tau_s"], color="k", ls=":", lw=1, label="chosen tau")
    ax2.set_xlim(0, min(10, lyap["ac_lags"][-1]))
    ax2.set_title("Autocorrelation")
    ax2.set_xlabel("lag / s")
    ax2.grid(alpha=0.25)
    ax2.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "delay_embedding_autocorrelation_3cm_bob3.png", dpi=180, bbox_inches="tight")


def make_lyap_plot(lyap):
    t = lyap["curve_t_s"]
    y = lyap["curve_log_div"]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(t, y, lw=1.6)
    fit = (t >= 0.25) & (t <= 2.0)
    if np.sum(fit) >= 3:
        slope = lyap["lambda_rosenstein_s_inv"]
        intercept = lyap["fit_intercept"]
        ax.plot(t[fit], slope * t[fit] + intercept, color="r", lw=1.5,
                label=f"fit lambda={slope:.3f} s^-1")
    ax.set_title("Rosenstein finite-data divergence estimate")
    ax.set_xlabel("time after nearest neighbor / s")
    ax.set_ylabel("mean log separation")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "rosenstein_lyapunov_3cm_bob3.png", dpi=180, bbox_inches="tight")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(DATA)
    t = df["t_s"].to_numpy(float)
    bob3 = df["bob3_proxy"].to_numpy(float)

    poincare = zero_crossing_poincare(t, df, "bob3_proxy")
    poincare.to_csv(OUT_DIR / "poincare_bob3_upcrossing.csv", index=False, encoding="utf-8-sig")

    lyap = rosenstein_lyapunov(t, bob3, dim=3, fit_s=(0.25, 2.0), max_t_s=5.0)
    k01, k_values = zero_one_test(bob3)

    make_phase_and_poincare(df, poincare)
    make_delay_plot(t, bob3, lyap)
    make_lyap_plot(lyap)

    pd.DataFrame({
        "t_s": lyap["curve_t_s"],
        "mean_log_separation": lyap["curve_log_div"],
    }).to_csv(OUT_DIR / "rosenstein_divergence_curve_bob3.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame({"K": k_values}).to_csv(OUT_DIR / "zero_one_test_K_values_bob3.csv", index=False, encoding="utf-8-sig")

    summary = pd.DataFrame([{
        "case": "3cm_experiment",
        "main_signal": "bob3_proxy",
        "poincare_points": len(poincare),
        "delay_tau_s": lyap["tau_s"],
        "rosenstein_lambda_s_inv_fit_0p25_2s": lyap["lambda_rosenstein_s_inv"],
        "zero_one_test_K_median": k01,
        "interpretation": "Auxiliary chaos indicators only; frequency background remains narrow-peak dominated, so do not claim strong sustained chaos."
    }])
    summary.to_csv(OUT_DIR / "chaos_evidence_3cm_summary.csv", index=False, encoding="utf-8-sig")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
