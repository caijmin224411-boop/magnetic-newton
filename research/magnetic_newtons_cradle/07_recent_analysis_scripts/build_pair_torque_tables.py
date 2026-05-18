import csv
import math
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
FORCE_TABLE = ROOT / "04_data_outputs" / "force_table_measured_70mT_disk_2d.csv"
OUT = ROOT / "04_data_outputs" / "pair_torque_tables"
OUT.mkdir(parents=True, exist_ok=True)

G = 9.81
M = 0.070
L = 0.12359
R = 0.015
SCALE = 0.5
MIN_TABLE_GAP = 0.002


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


GAPS, OFFSETS, AXIAL, LATERAL = read_force_table(FORCE_TABLE)


def interp2(gap, offset, table):
    gap = float(np.clip(gap, MIN_TABLE_GAP, GAPS[-1]))
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


def pair_quantities(pivot_spacing, theta_i, theta_j):
    xi = L * math.sin(theta_i)
    yi = -L * math.cos(theta_i)
    xj = pivot_spacing + L * math.sin(theta_j)
    yj = -L * math.cos(theta_j)
    dx = xi - xj
    dy = yi - yj
    center_distance = math.hypot(dx, dy)
    surface_gap = center_distance - 2 * R
    axial_gap = abs(dx) - 2 * R

    fax = abs(interp2(axial_gap, abs(dy), AXIAL))
    flat = abs(interp2(axial_gap, abs(dy), LATERAL))
    fx_i = SCALE * (math.copysign(fax, dx) if abs(dx) > 1e-12 else 0.0)
    fy_i = SCALE * (math.copysign(flat, dy) if abs(dy) > 1e-12 else 0.0)
    fx_j = -fx_i
    fy_j = -fy_i

    tau_mag_i = xi * fy_i - yi * fx_i
    tau_mag_j = (xj - pivot_spacing) * fy_j - yj * fx_j
    tau_g_i = -M * G * L * math.sin(theta_i)
    tau_g_j = -M * G * L * math.sin(theta_j)
    return {
        "theta_i_deg": math.degrees(theta_i),
        "theta_j_deg": math.degrees(theta_j),
        "pivot_spacing_m": pivot_spacing,
        "center_distance_m": center_distance,
        "surface_gap_m": surface_gap,
        "axial_gap_for_table_m": axial_gap,
        "force_x_on_i_N": fx_i,
        "force_y_on_i_N": fy_i,
        "tau_mag_i_Nm": tau_mag_i,
        "tau_mag_j_Nm": tau_mag_j,
        "tau_gravity_i_Nm": tau_g_i,
        "tau_gravity_j_Nm": tau_g_j,
        "tau_total_i_pair_Nm": tau_g_i + tau_mag_i,
        "tau_total_j_pair_Nm": tau_g_j + tau_mag_j,
        "invalid_if_surface_gap_lt_0": int(surface_gap < 0),
        "near_field_if_surface_gap_lt_0p02m": int(surface_gap < 0.02),
    }


def write_table(name, pivot_spacing, theta_min=-80, theta_max=80, theta_step=2):
    path = OUT / f"{name}_pair_torque_table.csv"
    angles = np.deg2rad(np.arange(theta_min, theta_max + 0.1, theta_step))
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        fieldnames = list(pair_quantities(pivot_spacing, 0.0, 0.0).keys())
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for ti in angles:
            for tj in angles:
                w.writerow(pair_quantities(pivot_spacing, float(ti), float(tj)))
    return path


def write_diagnostics():
    path = OUT / "torque_table_diagnostic_points.csv"
    cases = [
        ("5cm_equilibrium_like", 0.05, -8.54, -2.28),
        ("5cm_large_release_pair12", 0.05, -59.85, -8.54),
        ("5cm_symmetric_pair45", 0.05, 2.59, 9.08),
        ("3cm_large_release_pair23", 0.03, -18.95, -5.82),
        ("3cm_symmetric_pair45", 0.03, 6.81, 20.01),
        ("zero_angles_5cm", 0.05, 0.0, 0.0),
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        fieldnames = ["case", *pair_quantities(0.05, 0.0, 0.0).keys()]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for name, d, ai, aj in cases:
            row = pair_quantities(d, math.radians(ai), math.radians(aj))
            row["case"] = name
            w.writerow(row)
    return path


def main():
    outputs = [
        write_table("adjacent_3cm", 0.03),
        write_table("second_neighbor_3cm", 0.06),
        write_table("adjacent_5cm", 0.05),
        write_table("second_neighbor_5cm", 0.10),
        write_diagnostics(),
    ]
    for p in outputs:
        print(p)


if __name__ == "__main__":
    main()
