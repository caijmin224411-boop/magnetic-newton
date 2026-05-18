import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "05_code"
MODEL = CODE / "analyze_realistic_field_model.py"
OUT = ROOT / "04_data_outputs" / "physical_presets"
FORCE_TABLE = ROOT / "04_data_outputs" / "force_table_measured_70mT_disk_2d.csv"
OUT.mkdir(parents=True, exist_ok=True)


BASE_ENV = {
    "MNC_OUTPUT_DIR": str(OUT),
    "MNC_FORCE_TABLE": str(FORCE_TABLE),
    "MNC_LENGTH_M": "0.12359",
    "MNC_MASS_KG": "0.070",
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
    "MNC_RELEASE_DELTA_RAD": str(-50.0 * 3.141592653589793 / 180.0),
    "MNC_DURATION_S": "5",
    "MNC_SAMPLE_HZ": "360",
    "MNC_SKIP_LYAPUNOV": "1",
    "MNC_SKIP_PLOTS": "1",
}


PRESETS = {
    "physical_3cm_release50_scale0p5_w12": {
        "MNC_CASE_PREFIX": "physical_3cm_release50_scale0p5_w12",
        "MNC_PIVOT_SPACING_M": "0.030",
        "MNC_PAIR_WEIGHTS": "1:1,2:1",
    },
    "physical_5cm_release50_scale0p5_w1": {
        "MNC_CASE_PREFIX": "physical_5cm_release50_scale0p5_w1",
        "MNC_PIVOT_SPACING_M": "0.050",
        "MNC_PAIR_WEIGHTS": "1:1",
    },
}


def run_one(name, overrides):
    env = os.environ.copy()
    env.update(BASE_ENV)
    env.update(overrides)
    print(f"running {name}")
    result = subprocess.run(
        [sys.executable, str(MODEL)],
        cwd=str(CODE),
        env=env,
        text=True,
        capture_output=True,
    )
    log = OUT / f"{name}.log"
    log.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        return False
    return True


def main():
    ok = []
    for name, overrides in PRESETS.items():
        ok.append((name, run_one(name, overrides)))
    for name, success in ok:
        print(f"{name}: {'ok' if success else 'failed physical validity check'}")
    print(OUT)


if __name__ == "__main__":
    main()
