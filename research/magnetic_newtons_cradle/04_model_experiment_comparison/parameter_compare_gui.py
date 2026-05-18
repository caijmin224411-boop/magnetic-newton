import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from tkinter import BooleanVar, DoubleVar, IntVar, StringVar, Tk, ttk, messagebox

import numpy as np
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from scipy.signal import find_peaks


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "05_code"
MODEL_SCRIPT = CODE_DIR / "analyze_realistic_field_model.py"
FORCE_TABLE = ROOT / "04_data_outputs" / "force_table_measured_70mT_disk_2d.csv"
OUT_DIR = ROOT / "04_data_outputs" / "parameter_compare_gui"
OUT_DIR.mkdir(parents=True, exist_ok=True)

EXPERIMENTS = {
    "3 cm 实验": {
        "spacing_m": 0.030,
        "time": ROOT / "04_data_outputs" / "time_frequency_all_5_bobs" / "all_5_bobs_cleaned_detrended_proxy.csv",
        "freq": ROOT / "04_data_outputs" / "time_frequency_all_5_bobs" / "all_5_bobs_frequency_spectrum.csv",
    },
    "5 cm 实验": {
        "spacing_m": 0.050,
        "time": ROOT / "04_data_outputs" / "time_frequency_spacing_5cm" / "spacing_5cm_cleaned_detrended_proxy.csv",
        "freq": ROOT / "04_data_outputs" / "time_frequency_spacing_5cm" / "spacing_5cm_frequency_spectrum.csv",
    },
}

BOBS = [f"bob{i}" for i in range(1, 6)]


def read_experiment(name):
    cfg = EXPERIMENTS[name]
    time_df = pd.read_csv(cfg["time"])
    freq_df = pd.read_csv(cfg["freq"])
    t = time_df["t_s"].to_numpy(float)
    x = time_df[BOBS].to_numpy(float)
    f = freq_df["f_Hz"].to_numpy(float)
    a = freq_df[BOBS].to_numpy(float)
    return t, x, f, a


def read_model(prefix):
    ts = pd.read_csv(OUT_DIR / f"{prefix}_time_domain.csv")
    sp = pd.read_csv(OUT_DIR / f"{prefix}_frequency_spectrum.csv")
    t = ts["t_s"].to_numpy(float)
    theta = ts[[f"theta{i}" for i in range(1, 6)]].to_numpy(float)
    f = sp["frequency_Hz"].to_numpy(float)
    amp = sp[[f"amp_theta{i}_rad" for i in range(1, 6)]].to_numpy(float)
    return t, theta, f, amp


def normalize_columns(arr):
    arr = np.asarray(arr, dtype=float)
    out = arr - np.nanmean(arr, axis=0, keepdims=True)
    scale = np.nanpercentile(np.abs(out), 95, axis=0)
    scale[~np.isfinite(scale) | (scale <= 1e-12)] = 1.0
    return out / scale


def moving_rms(t, data, window_s=1.0):
    dt = float(np.median(np.diff(t)))
    n = max(3, int(round(window_s / dt)))
    kernel = np.ones(n) / n
    return np.column_stack([
        np.sqrt(np.convolve(data[:, i] ** 2, kernel, mode="same"))
        for i in range(data.shape[1])
    ])


def top_peaks(freq, amp, lo=0.1, hi=6.0, n=4):
    mask = (freq >= lo) & (freq <= hi)
    fv = freq[mask]
    out = []
    for i in range(amp.shape[1]):
        av = amp[mask, i]
        if len(av) == 0:
            out.append([])
            continue
        prom = max(np.nanmax(av) * 0.05, 1e-12)
        idx, _ = find_peaks(av, prominence=prom)
        if len(idx) == 0:
            idx = np.argsort(av)[-n:]
        idx = idx[np.argsort(av[idx])[-n:]][::-1]
        out.append([(float(fv[j]), float(av[j])) for j in idx])
    return out


def nearest_errors(exp_peaks, model_peaks):
    rows = []
    for i, bob in enumerate(BOBS):
        mf = [p[0] for p in model_peaks[i]]
        for rank, (ef, _) in enumerate(exp_peaks[i][:3], start=1):
            if not mf:
                rows.append((bob, rank, ef, np.nan, np.nan))
            else:
                closest = min(mf, key=lambda x: abs(x - ef))
                rows.append((bob, rank, ef, closest, closest - ef))
    return rows


class CompareApp:
    def __init__(self, root):
        self.root = root
        self.root.title("磁力牛顿摆：实验-模拟参数对比工具")
        self.root.geometry("1420x900")
        self.status = StringVar(value="准备就绪")
        self.last_prefix = None
        self._build_ui()

    def _build_ui(self):
        outer = ttk.PanedWindow(self.root, orient="horizontal")
        outer.pack(fill="both", expand=True)

        controls = ttk.Frame(outer, padding=10)
        outer.add(controls, weight=0)
        plot_frame = ttk.Frame(outer)
        outer.add(plot_frame, weight=1)

        row = 0
        ttk.Label(controls, text="实验数据").grid(row=row, column=0, sticky="w")
        self.exp_name = StringVar(value="5 cm 实验")
        exp_box = ttk.Combobox(controls, textvariable=self.exp_name, values=list(EXPERIMENTS), state="readonly", width=18)
        exp_box.grid(row=row, column=1, sticky="ew", pady=3)
        exp_box.bind("<<ComboboxSelected>>", self._apply_experiment_spacing)

        self.spacing_cm = DoubleVar(value=5.0)
        self.force_scale = DoubleVar(value=0.50)
        self.length_cm = DoubleVar(value=11.878)
        self.mass_g = DoubleVar(value=70.0)
        self.c1 = DoubleVar(value=2.833954997868876e-05)
        self.c2 = DoubleVar(value=6.541910366771381e-06)
        self.duration_s = DoubleVar(value=60.0)
        self.sample_hz = DoubleVar(value=360.0)
        self.release_index = IntVar(value=1)
        self.release_delta_deg = DoubleVar(value=-50.0)
        self.disk_radius_cm = DoubleVar(value=1.5)
        self.min_gap_mm = DoubleVar(value=2.0)
        self.use_equilibrium = BooleanVar(value=True)
        self.initial_theta_deg = StringVar(value="-35,-14,-3.5,5,17.6")

        fields = [
            ("轴间距 cm", self.spacing_cm),
            ("磁力缩放", self.force_scale),
            ("有效摆长 cm", self.length_cm),
            ("质量 g", self.mass_g),
            ("线性阻尼 c1", self.c1),
            ("二次阻尼 c2", self.c2),
            ("仿真时长 s", self.duration_s),
            ("采样 Hz", self.sample_hz),
            ("释放摆编号", self.release_index),
            ("释放增量 deg", self.release_delta_deg),
            ("磁体半径 cm", self.disk_radius_cm),
            ("最小间隙 mm", self.min_gap_mm),
        ]
        for label, var in fields:
            row += 1
            ttk.Label(controls, text=label).grid(row=row, column=0, sticky="w")
            ttk.Entry(controls, textvariable=var, width=18).grid(row=row, column=1, sticky="ew", pady=3)

        row += 1
        ttk.Checkbutton(controls, text="先求静态平衡再释放", variable=self.use_equilibrium).grid(row=row, column=0, columnspan=2, sticky="w", pady=5)

        row += 1
        ttk.Label(controls, text="直接初始角 deg").grid(row=row, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.initial_theta_deg, width=24).grid(row=row, column=1, sticky="ew", pady=3)

        row += 1
        ttk.Button(controls, text="运行模拟并对比", command=self.run_async).grid(row=row, column=0, columnspan=2, sticky="ew", pady=(12, 5))

        row += 1
        ttk.Button(controls, text="仅重画当前实验", command=self.plot_experiment_only).grid(row=row, column=0, columnspan=2, sticky="ew", pady=3)

        row += 1
        ttk.Label(controls, textvariable=self.status, wraplength=260, foreground="#334").grid(row=row, column=0, columnspan=2, sticky="ew", pady=(12, 3))

        row += 1
        ttk.Separator(controls).grid(row=row, column=0, columnspan=2, sticky="ew", pady=8)
        row += 1
        note = (
            "建议用法：\n"
            "1. 磁力缩放先固定 0.5。\n"
            "2. 改轴间距看主峰移动。\n"
            "3. 改阻尼看包络衰减。\n"
            "4. 改初始角/释放摆看时域相位。"
        )
        ttk.Label(controls, text=note, wraplength=260, justify="left").grid(row=row, column=0, columnspan=2, sticky="w")

        self.fig = Figure(figsize=(10.8, 7.4), dpi=100)
        self.axes = self.fig.subplots(2, 2)
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        toolbar = NavigationToolbar2Tk(self.canvas, plot_frame)
        toolbar.update()

        self.table = ttk.Treeview(plot_frame, columns=("bob", "rank", "exp", "model", "err"), show="headings", height=8)
        for col, title, width in [
            ("bob", "摆", 70),
            ("rank", "峰序", 70),
            ("exp", "实验 Hz", 110),
            ("model", "模拟 Hz", 110),
            ("err", "误差 Hz", 110),
        ]:
            self.table.heading(col, text=title)
            self.table.column(col, width=width, anchor="center")
        self.table.pack(fill="x")
        self.plot_experiment_only()

    def _apply_experiment_spacing(self, _event=None):
        self.spacing_cm.set(EXPERIMENTS[self.exp_name.get()]["spacing_m"] * 100)
        self.plot_experiment_only()

    def _env(self, prefix):
        env = os.environ.copy()
        env.update({
            "MNC_CASE_PREFIX": prefix,
            "MNC_OUTPUT_DIR": str(OUT_DIR),
            "MNC_FORCE_TABLE": str(FORCE_TABLE),
            "MNC_MASS_KG": f"{self.mass_g.get() / 1000.0}",
            "MNC_LENGTH_M": f"{self.length_cm.get() / 100.0}",
            "MNC_PIVOT_SPACING_M": f"{self.spacing_cm.get() / 100.0}",
            "MNC_DISK_RADIUS_M": f"{self.disk_radius_cm.get() / 100.0}",
            "MNC_MIN_GAP_M": f"{self.min_gap_mm.get() / 1000.0}",
            "MNC_DURATION_S": f"{self.duration_s.get()}",
            "MNC_SAMPLE_HZ": f"{self.sample_hz.get()}",
            "MNC_SKIP_LYAPUNOV": "1",
            "MNC_SKIP_PLOTS": "1",
            "MNC_USE_NONLINEAR_DAMPING": "1",
            "MNC_DAMPING_C1_NMS": f"{self.c1.get()}",
            "MNC_DAMPING_C2_NMS2": f"{self.c2.get()}",
            "MNC_MAG_FORCE_SCALE": f"{self.force_scale.get()}",
        })
        if self.use_equilibrium.get():
            env.update({
                "MNC_USE_SOLVED_EQUILIBRIUM": "1",
                "MNC_RELEASE_INDEX": f"{max(0, min(4, self.release_index.get() - 1))}",
                "MNC_RELEASE_DELTA_RAD": f"{np.deg2rad(self.release_delta_deg.get())}",
            })
        else:
            vals = [float(v.strip()) for v in self.initial_theta_deg.get().split(",") if v.strip()]
            if len(vals) != 5:
                raise ValueError("直接初始角必须填 5 个角度，用逗号分隔")
            env.update({
                "MNC_USE_SOLVED_EQUILIBRIUM": "0",
                "MNC_INITIAL_THETA": ",".join(f"{np.deg2rad(v):.10g}" for v in vals),
                "MNC_RELEASE_DELTA_RAD": "0",
            })
        return env

    def run_async(self):
        thread = threading.Thread(target=self._run_model, daemon=True)
        thread.start()

    def _run_model(self):
        try:
            prefix = f"gui_{int(time.time())}_d{self.spacing_cm.get():.2f}_s{self.force_scale.get():.3f}".replace(".", "p")
            self.status.set("正在运行模拟，稍等几十秒...")
            result = subprocess.run(
                [sys.executable, str(MODEL_SCRIPT)],
                cwd=str(CODE_DIR),
                env=self._env(prefix),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            self.last_prefix = prefix
            self.root.after(0, lambda: self.plot_compare(prefix, result.stdout))
        except Exception as exc:
            self.root.after(0, lambda: messagebox.showerror("运行失败", str(exc)))
            self.status.set("运行失败，请检查参数")

    def plot_experiment_only(self):
        t_exp, x_exp, f_exp, a_exp = read_experiment(self.exp_name.get())
        self._clear_axes()
        ax = self.axes[0, 0]
        mask = t_exp <= min(25, t_exp[-1])
        for i, bob in enumerate(BOBS):
            ax.plot(t_exp[mask], normalize_columns(x_exp)[mask, i], lw=1, label=bob)
        ax.set_title("实验时域，已清洗去漂移")
        ax.set_xlabel("t / s")
        ax.set_ylabel("归一化位移")
        ax.legend(ncol=5, fontsize=8)

        ax = self.axes[0, 1]
        fmask = f_exp <= 6
        for i, bob in enumerate(BOBS):
            col = a_exp[:, i] / (np.nanmax(a_exp[fmask, i]) + 1e-12)
            ax.plot(f_exp[fmask], col[fmask], lw=1, label=bob)
        ax.set_title("实验频谱")
        ax.set_xlabel("f / Hz")
        ax.set_ylabel("归一化幅值")

        ax = self.axes[1, 0]
        rms = moving_rms(t_exp, normalize_columns(x_exp), 1.0)
        for i, bob in enumerate(BOBS):
            ax.plot(t_exp[mask], rms[mask, i], lw=1, label=bob)
        ax.set_title("实验 1 s RMS 包络")
        ax.set_xlabel("t / s")

        self.axes[1, 1].axis("off")
        self.axes[1, 1].text(0.05, 0.8, "点击“运行模拟并对比”后，这里会显示主峰误差。", fontsize=12)
        self.fig.tight_layout()
        self.canvas.draw()
        self.status.set(f"已载入 {self.exp_name.get()}，可开始调参")

    def plot_compare(self, prefix, stdout):
        t_exp, x_exp, f_exp, a_exp = read_experiment(self.exp_name.get())
        t_mod, x_mod, f_mod, a_mod = read_model(prefix)
        xe = normalize_columns(x_exp)
        xm = normalize_columns(x_mod)

        self._clear_axes()
        tmax = min(25, t_exp[-1], t_mod[-1])
        emask = t_exp <= tmax
        mmask = t_mod <= tmax

        ax = self.axes[0, 0]
        for i, bob in enumerate(BOBS):
            ax.plot(t_exp[emask], xe[emask, i], lw=1.0, alpha=0.75)
            ax.plot(t_mod[mmask], xm[mmask, i], lw=1.0, ls="--", alpha=0.75)
        ax.set_title("时域：实验实线，模拟虚线")
        ax.set_xlabel("t / s")
        ax.set_ylabel("归一化位移/角度")

        ax = self.axes[0, 1]
        fmask_e = f_exp <= 6
        fmask_m = f_mod <= 6
        for i, bob in enumerate(BOBS):
            ae = a_exp[:, i] / (np.nanmax(a_exp[fmask_e, i]) + 1e-12)
            am = a_mod[:, i] / (np.nanmax(a_mod[fmask_m, i]) + 1e-12)
            ax.plot(f_exp[fmask_e], ae[fmask_e], lw=1.0, alpha=0.75)
            ax.plot(f_mod[fmask_m], am[fmask_m], lw=1.0, ls="--", alpha=0.75)
        ax.set_title("频域：实验实线，模拟虚线")
        ax.set_xlabel("f / Hz")
        ax.set_ylabel("归一化幅值")

        ax = self.axes[1, 0]
        rms_e = moving_rms(t_exp, xe, 1.0)
        rms_m = moving_rms(t_mod, xm, 1.0)
        ax.plot(t_exp[emask], np.mean(rms_e[emask], axis=1), lw=2, label="实验平均")
        ax.plot(t_mod[mmask], np.mean(rms_m[mmask], axis=1), lw=2, ls="--", label="模拟平均")
        ax.set_title("平均 RMS 包络")
        ax.set_xlabel("t / s")
        ax.legend()

        exp_peaks = top_peaks(f_exp, a_exp)
        mod_peaks = top_peaks(f_mod, a_mod)
        rows = nearest_errors(exp_peaks, mod_peaks)
        self._fill_table(rows)

        ax = self.axes[1, 1]
        ax.axis("off")
        avg_err = np.nanmean([abs(r[-1]) for r in rows])
        text = (
            f"实验：{self.exp_name.get()}\n"
            f"轴间距：{self.spacing_cm.get():.2f} cm\n"
            f"磁力缩放：{self.force_scale.get():.3f}\n"
            f"有效摆长：{self.length_cm.get():.3f} cm\n"
            f"平均主峰误差：{avg_err:.3f} Hz\n\n"
            "判断口径：\n"
            "频谱主峰接近 = 模态解释较好；\n"
            "RMS 包络接近 = 阻尼解释较好；\n"
            "时域逐点相位通常很难完全重合。"
        )
        ax.text(0.05, 0.95, text, va="top", fontsize=11)

        self.fig.tight_layout()
        self.canvas.draw()
        self.status.set(f"完成：{prefix}，平均主峰误差 {avg_err:.3f} Hz")
        print(stdout)

    def _fill_table(self, rows):
        for item in self.table.get_children():
            self.table.delete(item)
        for bob, rank, exp_f, mod_f, err in rows:
            self.table.insert("", "end", values=(
                bob,
                rank,
                f"{exp_f:.3f}",
                "" if not np.isfinite(mod_f) else f"{mod_f:.3f}",
                "" if not np.isfinite(err) else f"{err:+.3f}",
            ))

    def _clear_axes(self):
        for ax in self.axes.ravel():
            ax.clear()


def main():
    root = Tk()
    ttk.Style().theme_use("clam")
    CompareApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
