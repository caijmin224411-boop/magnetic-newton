import csv
import math
import time
from pathlib import Path
from tkinter import BooleanVar, DoubleVar, StringVar, Tk, Canvas, ttk, messagebox

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
FORCE_TABLE = ROOT / "04_data_outputs" / "force_table_measured_70mT_disk_2d.csv"

N = 5
G = 9.81
COLORS = ["#d6483c", "#2870b9", "#309666", "#de9a28", "#6e50a5"]


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


class RealtimeSimulator:
    def __init__(self, root):
        self.root = root
        self.root.title("磁力牛顿摆实时运动模拟器")
        self.root.geometry("1360x820")

        self.running = False
        self.t = 0.0
        self.state = np.zeros(2 * N, dtype=float)
        self.history_t = []
        self.history_theta = []
        self.last_wall = None

        self.spacing_cm = DoubleVar(value=5.0)
        self.length_cm = DoubleVar(value=11.878)
        self.mass_g = DoubleVar(value=70.0)
        self.force_scale = DoubleVar(value=0.50)
        self.c1 = DoubleVar(value=2.833954997868876e-05)
        self.c2 = DoubleVar(value=6.541910366771381e-06)
        self.disk_radius_cm = DoubleVar(value=1.5)
        self.min_gap_mm = DoubleVar(value=2.0)
        self.speed = DoubleVar(value=1.0)
        self.sim_hz = DoubleVar(value=720.0)
        self.initial_angles = StringVar(value="-35,-14,-3.5,5,17.6")
        self.initial_omegas = StringVar(value="0,0,0,0,0")
        self.all_pairs = BooleanVar(value=False)
        self.status = StringVar(value="准备就绪")

        self._build_ui()
        self.reset()
        self._loop()

    def _build_ui(self):
        outer = ttk.PanedWindow(self.root, orient="horizontal")
        outer.pack(fill="both", expand=True)

        controls = ttk.Frame(outer, padding=10)
        outer.add(controls, weight=0)

        view = ttk.Frame(outer)
        outer.add(view, weight=1)

        row = 0
        ttk.Label(controls, text="参数", font=("Microsoft YaHei", 12, "bold")).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 8))

        fields = [
            ("轴间距 cm", self.spacing_cm),
            ("有效摆长 cm", self.length_cm),
            ("质量 g", self.mass_g),
            ("磁力缩放", self.force_scale),
            ("线性阻尼 c1", self.c1),
            ("二次阻尼 c2", self.c2),
            ("磁体半径 cm", self.disk_radius_cm),
            ("最小间隙 mm", self.min_gap_mm),
            ("播放速度", self.speed),
            ("积分频率 Hz", self.sim_hz),
        ]
        for label, var in fields:
            row += 1
            ttk.Label(controls, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(controls, textvariable=var, width=18).grid(row=row, column=1, sticky="ew", pady=3)

        row += 1
        ttk.Label(controls, text="初始角 deg").grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(controls, textvariable=self.initial_angles, width=24).grid(row=row, column=1, sticky="ew", pady=3)

        row += 1
        ttk.Label(controls, text="初始角速度 deg/s").grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(controls, textvariable=self.initial_omegas, width=24).grid(row=row, column=1, sticky="ew", pady=3)

        row += 1
        ttk.Checkbutton(controls, text="计算非相邻磁耦合", variable=self.all_pairs).grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 4))

        row += 1
        ttk.Button(controls, text="开始 / 暂停", command=self.toggle).grid(row=row, column=0, columnspan=2, sticky="ew", pady=(12, 4))
        row += 1
        ttk.Button(controls, text="重置并应用参数", command=self.reset).grid(row=row, column=0, columnspan=2, sticky="ew", pady=4)
        row += 1
        ttk.Button(controls, text="设为 3 cm 默认", command=lambda: self.set_spacing_default(3.0)).grid(row=row, column=0, columnspan=2, sticky="ew", pady=4)
        row += 1
        ttk.Button(controls, text="设为 5 cm 默认", command=lambda: self.set_spacing_default(5.0)).grid(row=row, column=0, columnspan=2, sticky="ew", pady=4)

        row += 1
        ttk.Label(controls, textvariable=self.status, wraplength=280, foreground="#334").grid(row=row, column=0, columnspan=2, sticky="ew", pady=(14, 4))

        row += 1
        note = (
            "说明：每帧实时积分运动方程。\n"
            "上图是杆摆和磁体位置，下图是五个摆的角度历史。\n"
            "默认只算相邻磁耦合，与当前主模型一致。"
        )
        ttk.Label(controls, text=note, wraplength=280, justify="left").grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.canvas = Canvas(view, bg="#f8f7f2", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

    def set_spacing_default(self, spacing):
        self.spacing_cm.set(spacing)
        self.force_scale.set(0.5)
        if spacing == 3.0:
            self.initial_angles.set("-35,-14,-3.5,5,17.6")
        else:
            self.initial_angles.set("-35,-14,-3.5,5,17.6")
        self.reset()

    def parse_five(self, text, scale):
        vals = [float(v.strip()) for v in text.split(",") if v.strip()]
        if len(vals) != N:
            raise ValueError("需要输入 5 个数，用逗号分隔。")
        return np.array(vals, dtype=float) * scale

    def params(self):
        return {
            "spacing": self.spacing_cm.get() / 100.0,
            "L": self.length_cm.get() / 100.0,
            "m": self.mass_g.get() / 1000.0,
            "scale": self.force_scale.get(),
            "c1": self.c1.get(),
            "c2": self.c2.get(),
            "r": self.disk_radius_cm.get() / 100.0,
            "min_gap": self.min_gap_mm.get() / 1000.0,
        }

    def reset(self):
        try:
            theta = self.parse_five(self.initial_angles.get(), math.pi / 180.0)
            omega = self.parse_five(self.initial_omegas.get(), math.pi / 180.0)
            self.state = np.r_[theta, omega]
            self.t = 0.0
            self.history_t = [self.t]
            self.history_theta = [theta.copy()]
            self.status.set("已重置。")
            self.draw()
        except Exception as exc:
            messagebox.showerror("参数错误", str(exc))

    def toggle(self):
        self.running = not self.running
        self.last_wall = time.perf_counter()
        self.status.set("运行中" if self.running else "已暂停")

    def pivot_x(self, p):
        return (np.arange(1, N + 1) - (N + 1) / 2.0) * p["spacing"]

    def centers(self, theta, p):
        px = self.pivot_x(p)
        L = p["L"]
        return px + L * np.sin(theta), -L * np.cos(theta)

    def acceleration(self, theta, omega, p):
        px = self.pivot_x(p)
        x, y = self.centers(theta, p)
        a = np.zeros(N, dtype=float)
        m, L = p["m"], p["L"]
        for i in range(N):
            rx = x[i] - px[i]
            ry = y[i]
            tau = (
                -m * G * L * math.sin(theta[i])
                -p["c1"] * omega[i]
                -p["c2"] * omega[i] * abs(omega[i])
            )
            if self.all_pairs.get():
                js = [j for j in range(N) if j != i]
            else:
                js = [j for j in (i - 1, i + 1) if 0 <= j < N]
            for j in js:
                dx = x[i] - x[j]
                dy = y[i] - y[j]
                gap = abs(dx) - 2 * p["r"]
                fax = abs(interp2(gap, abs(dy), AXIAL_TABLE, p["min_gap"]))
                flat = abs(interp2(gap, abs(dy), LATERAL_TABLE, p["min_gap"]))
                fx = p["scale"] * (math.copysign(fax, dx) if abs(dx) > 1e-12 else 0.0)
                fy = p["scale"] * (math.copysign(flat, dy) if abs(dy) > 1e-12 else 0.0)
                tau += rx * fy - ry * fx
            a[i] = tau / (m * L * L)
        return a

    def rhs(self, state, p):
        theta = state[:N]
        omega = state[N:]
        return np.r_[omega, self.acceleration(theta, omega, p)]

    def rk4_step(self, state, dt, p):
        k1 = self.rhs(state, p)
        k2 = self.rhs(state + 0.5 * dt * k1, p)
        k3 = self.rhs(state + 0.5 * dt * k2, p)
        k4 = self.rhs(state + dt * k3, p)
        return state + dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6.0

    def step(self, elapsed_wall):
        p = self.params()
        hz = max(60.0, self.sim_hz.get())
        dt = 1.0 / hz
        sim_elapsed = max(0.0, elapsed_wall * max(0.0, self.speed.get()))
        steps = max(1, min(80, int(round(sim_elapsed / dt))))
        for _ in range(steps):
            self.state = self.rk4_step(self.state, dt, p)
            self.t += dt
        self.history_t.append(self.t)
        self.history_theta.append(self.state[:N].copy())
        while self.history_t and self.history_t[0] < self.t - 20.0:
            self.history_t.pop(0)
            self.history_theta.pop(0)

    def _loop(self):
        now = time.perf_counter()
        if self.running:
            if self.last_wall is None:
                self.last_wall = now
            elapsed = now - self.last_wall
            self.last_wall = now
            try:
                self.step(elapsed)
            except Exception as exc:
                self.running = False
                messagebox.showerror("积分失败", str(exc))
        self.draw()
        self.root.after(16, self._loop)

    def world_to_canvas(self, x, y, box, scale_px):
        left, top, right, bottom = box
        cx = (left + right) / 2.0
        pivot_y = top + 90
        return cx + x * scale_px, pivot_y - y * scale_px

    def draw(self):
        c = self.canvas
        c.delete("all")
        w = max(800, c.winfo_width())
        h = max(600, c.winfo_height())
        apparatus = (40, 35, w - 40, int(h * 0.58))
        plot = (60, int(h * 0.64), w - 40, h - 55)
        p = self.params()
        theta = self.state[:N]
        omega = self.state[N:]
        px = self.pivot_x(p)
        x, y = self.centers(theta, p)
        span = max(abs(px[0]) + p["L"] + p["spacing"], abs(px[-1]) + p["L"] + p["spacing"])
        scale_px = min((apparatus[2] - apparatus[0]) / (2.4 * span), (apparatus[3] - apparatus[1]) / (1.55 * p["L"]))

        c.create_text(apparatus[0], 18, anchor="w", text=f"实时计算 t = {self.t:6.2f} s", fill="#222", font=("Microsoft YaHei", 14, "bold"))
        c.create_line(apparatus[0], apparatus[1] + 90, apparatus[2], apparatus[1] + 90, fill="#b99b5d", width=8)

        for i in range(N):
            x0, y0 = self.world_to_canvas(px[i], 0, apparatus, scale_px)
            xb, yb = self.world_to_canvas(x[i], y[i], apparatus, scale_px)
            c.create_line(x0, y0, xb, yb, fill="#555", width=3)
            radius = max(8, p["r"] * scale_px)
            c.create_oval(xb - radius, yb - radius, xb + radius, yb + radius, fill=COLORS[i], outline="#222", width=1)
            c.create_text(xb, yb, text=str(i + 1), fill="white", font=("Arial", 10, "bold"))
            c.create_oval(x0 - 4, y0 - 4, x0 + 4, y0 + 4, fill="#333")

        c.create_text(apparatus[2] - 10, apparatus[1] + 12, anchor="ne",
                      text="theta(deg): " + "  ".join(f"{math.degrees(v):+.1f}" for v in theta),
                      fill="#333", font=("Consolas", 11))
        c.create_text(apparatus[2] - 10, apparatus[1] + 34, anchor="ne",
                      text="omega(deg/s): " + "  ".join(f"{math.degrees(v):+.1f}" for v in omega),
                      fill="#555", font=("Consolas", 10))

        self.draw_trace(plot)

    def draw_trace(self, box):
        c = self.canvas
        left, top, right, bottom = box
        c.create_rectangle(left, top, right, bottom, outline="#333")
        c.create_text(left, top - 20, anchor="w", text="实时角度曲线", fill="#333", font=("Microsoft YaHei", 12, "bold"))
        if len(self.history_t) < 2:
            return
        ts = np.array(self.history_t)
        th = np.array(self.history_theta)
        t0, t1 = max(ts[-1] - 20.0, ts[0]), ts[-1]
        mask = ts >= t0
        ts = ts[mask]
        th = th[mask]
        ymin = min(-0.8, float(np.min(th)) * 1.1)
        ymax = max(0.8, float(np.max(th)) * 1.1)
        if abs(ymax - ymin) < 1e-9:
            ymax += 1
            ymin -= 1

        for k in range(5):
            xg = left + k * (right - left) / 4
            c.create_line(xg, top, xg, bottom, fill="#e0ddd5")
        for k in range(5):
            yg = top + k * (bottom - top) / 4
            c.create_line(left, yg, right, yg, fill="#e0ddd5")

        for i in range(N):
            pts = []
            for tv, yv in zip(ts, th[:, i]):
                px = left + (tv - t0) / max(1e-9, t1 - t0) * (right - left)
                py = bottom - (yv - ymin) / (ymax - ymin) * (bottom - top)
                pts.extend([px, py])
            if len(pts) >= 4:
                c.create_line(*pts, fill=COLORS[i], width=2)
            c.create_text(right - 80, top + 18 + i * 18, anchor="w", text=f"bob{i+1}", fill=COLORS[i], font=("Arial", 10, "bold"))

        c.create_text(left, bottom + 18, anchor="w", text=f"{t0:.1f}s", fill="#555")
        c.create_text(right, bottom + 18, anchor="e", text=f"{t1:.1f}s", fill="#555")
        c.create_text(left - 5, top, anchor="e", text=f"{math.degrees(ymax):.0f}deg", fill="#555")
        c.create_text(left - 5, bottom, anchor="e", text=f"{math.degrees(ymin):.0f}deg", fill="#555")


def main():
    root = Tk()
    ttk.Style().theme_use("clam")
    RealtimeSimulator(root)
    root.mainloop()


if __name__ == "__main__":
    main()
