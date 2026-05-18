from pathlib import Path
import os, subprocess, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(r'C:\Users\66\Desktop\cupt\IYPT2026_Research\15_Magnetic_Newtons_cradle\handoff_for_next_window')
CODE = ROOT / '05_code'
MODEL = CODE / 'analyze_realistic_field_model.py'
FORCE_TABLE = ROOT / '04_data_outputs' / 'force_table_measured_70mT_disk_2d.csv'
OUT = ROOT / '04_data_outputs' / 'release_angle_frequency_sweep'
FIG = ROOT / '03_key_figures' / 'release_angle_frequency_sweep'
OUT.mkdir(parents=True, exist_ok=True)
FIG.mkdir(parents=True, exist_ok=True)

angles = [10, 20, 30, 40, 50, 60]
cases = {
    '5cm': {'spacing': 0.050, 'weights': '1:1'},
    '3cm': {'spacing': 0.030, 'weights': '1:1,2:1'},
}

base_env = {
    'MNC_OUTPUT_DIR': str(OUT),
    'MNC_FORCE_TABLE': str(FORCE_TABLE),
    'MNC_LENGTH_M': '0.12359',
    'MNC_MASS_KG': '0.070',
    'MNC_DISK_RADIUS_M': '0.015',
    'MNC_MAG_FORCE_SCALE': '0.5',
    'MNC_USE_NONLINEAR_DAMPING': '1',
    'MNC_DAMPING_C1_NMS': '2.833954997868876e-05',
    'MNC_DAMPING_C2_NMS2': '6.541910366771381e-06',
    'MNC_MIN_GAP_M': '0.002',
    'MNC_NEAR_CONTACT_GAP_M': '0.004',
    'MNC_HARD_WALL_K_N_PER_M2': '1000000',
    'MNC_HARD_WALL_POWER': '2',
    'MNC_STOP_ON_CONTACT': '1',
    'MNC_CONDITIONAL_RELEASE_EQUILIBRIUM': '1',
    'MNC_RELEASE_INDEX': '0',
    'MNC_DURATION_S': '20',
    'MNC_SAMPLE_HZ': '360',
    'MNC_SKIP_LYAPUNOV': '1',
    'MNC_SKIP_PLOTS': '1',
}

def run_case(case, cfg, angle):
    prefix = f'{case}_release_{angle:02d}deg_scale0p5'
    fft = OUT / f'{prefix}_frequency_spectrum.csv'
    if fft.exists():
        return fft
    env = os.environ.copy()
    env.update(base_env)
    env.update({
        'MNC_CASE_PREFIX': prefix,
        'MNC_PIVOT_SPACING_M': str(cfg['spacing']),
        'MNC_PAIR_WEIGHTS': cfg['weights'],
        'MNC_RELEASE_DELTA_RAD': str(-np.deg2rad(angle)),
    })
    res = subprocess.run([sys.executable, str(MODEL)], cwd=str(CODE), env=env, text=True, capture_output=True)
    (OUT / f'{prefix}.log').write_text(res.stdout + '\n' + res.stderr, encoding='utf-8')
    if res.returncode != 0:
        print(f'skip invalid case: {prefix}; see {OUT / (prefix + ".log")}')
        return None
    return fft

def load_norm_spectrum(path, bob='amp_theta1_rad'):
    df = pd.read_csv(path)
    f = df['frequency_Hz'].to_numpy(float)
    amp_cols = [c for c in df.columns if c.startswith('amp_theta')]
    if bob == 'average':
        a = df[amp_cols].to_numpy(float).mean(axis=1)
    else:
        a = df[bob].to_numpy(float)
    mask = (f >= 0.05) & (f <= 6.0)
    f, a = f[mask], a[mask]
    if np.nanmax(a) > 0:
        a = a / np.nanmax(a)
    return f, a

def plot_case(case, spectra_paths):
    fig, axes = plt.subplots(2, 1, figsize=(11.5, 8.0), dpi=180, sharex=True)
    colors = plt.cm.viridis(np.linspace(0.1, 0.92, len(angles)))
    for angle, color in zip(angles, colors):
        if angle not in spectra_paths:
            continue
        path = spectra_paths[angle]
        f, a1 = load_norm_spectrum(path, 'amp_theta1_rad')
        _, avg = load_norm_spectrum(path, 'average')
        axes[0].plot(f, a1, lw=1.8, color=color, label=f'{angle} deg')
        axes[1].plot(f, avg, lw=1.8, color=color, label=f'{angle} deg')
    axes[0].set_title(f'{case}: simulated spectra under different release angles, edge bob 1')
    axes[1].set_title(f'{case}: simulated spectra under different release angles, five-bob average')
    for ax in axes:
        ax.set_xlim(0, 6)
        ax.set_ylim(0, 1.06)
        ax.set_ylabel('normalized FFT amplitude')
        ax.grid(alpha=0.28, lw=0.6)
        ax.legend(ncol=6, fontsize=8, frameon=False, loc='upper right')
    axes[1].set_xlabel('frequency / Hz')
    fig.tight_layout()
    out = FIG / f'{case}_release_angle_frequency_sweep_0_6Hz.png'
    fig.savefig(out, bbox_inches='tight')
    plt.close(fig)
    return out

def peak_table(case, spectra_paths):
    from scipy.signal import find_peaks
    rows = []
    for angle in angles:
        if angle not in spectra_paths:
            rows.append({'case': case, 'release_angle_deg': angle, 'series': 'invalid', 'rank': 0, 'frequency_Hz': np.nan, 'normalized_amp': np.nan})
            continue
        for role, col in [('edge_bob1', 'amp_theta1_rad'), ('average', 'average')]:
            f, a = load_norm_spectrum(spectra_paths[angle], col)
            peaks, props = find_peaks(a, prominence=0.04, distance=3)
            order = sorted(peaks, key=lambda k: a[k], reverse=True)[:8]
            for rank, idx in enumerate(order, 1):
                rows.append({'case': case, 'release_angle_deg': angle, 'series': role, 'rank': rank, 'frequency_Hz': f[idx], 'normalized_amp': a[idx]})
    return pd.DataFrame(rows)

all_peak = []
figs = []
for case, cfg in cases.items():
    raw_paths = {angle: run_case(case, cfg, angle) for angle in angles}
    paths = {angle: path for angle, path in raw_paths.items() if path is not None}
    figs.append(plot_case(case, paths))
    all_peak.append(peak_table(case, paths))

peaks = pd.concat(all_peak, ignore_index=True)
peaks.to_csv(OUT / 'release_angle_frequency_peak_table.csv', index=False, encoding='utf-8-sig')
print('\n'.join(str(p) for p in figs))
print(OUT / 'release_angle_frequency_peak_table.csv')
