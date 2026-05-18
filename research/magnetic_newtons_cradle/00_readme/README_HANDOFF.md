# Magnetic Newton's Cradle Handoff

This folder is a compact handoff package for continuing the Magnetic Newton's Cradle research in another window/session.

## Current Best Experimental Case

Latest corrected experimental parameters:

- Pivot spacing: `4 cm`
- Magnet diameter: `3 cm`
- Magnet thickness: `2.5 cm`
- Magnet surface field: `220 mT`
- Bob mass: `70 g`
- Tracker release angle: about `50 deg`
- Tracker data file: `06_sources/牛顿.xlsx`

The measured surface field was converted to an effective cylindrical-magnet remanence:

```text
B_surface = Br / 2 * L / sqrt(R^2 + L^2)
Br = 2 * B_surface * sqrt(R^2 + L^2) / L
Br ≈ 0.513 T
```

This is an effective model value constrained by the measured surface field, not a claim about the true material remanence.

## Core Model

Each pendulum has one angular degree of freedom:

```text
state = (theta1, theta2, theta3, theta4, theta5, omega1, omega2, omega3, omega4, omega5)
```

The equation used in the current model is:

```text
theta_i'' = tau_i / (m L_i^2)

tau_i = -m g L_i sin(theta_i)
        - c_i theta_i'
        + sum_j (r_i x F_ij)_z
```

Magnetic forces are not hand-scaled. They are read from a finite cylindrical magnet force table:

```text
gap_m, offset_m, force_axial_N, force_lateral_N
```

The force table is generated with:

```text
05_code/run_force_table_java_5cm_220mT.ps1
05_code/DiskMagnetForceTable.java
```

Despite the script name containing `5cm`, the force table itself depends only on magnet geometry/field, not pivot spacing. The pivot spacing is set in the dynamics script.

## Static Equilibrium

Static angles are solved from torque equilibrium, not hand-estimated from the photo:

```text
tau_i(theta) = 0
```

For the `4 cm / 220 mT / 70 g` case, solved equilibrium:

```text
bob 1: -0.7719 rad = -44.23 deg
bob 2: -0.3516 rad = -20.14 deg
bob 3:  0.0000 rad =   0.00 deg
bob 4:  0.3516 rad =  20.14 deg
bob 5:  0.7719 rad =  44.23 deg
```

Data file:

```text
04_data_outputs/realfield_4cm_220mT_solved_eq_left_release_equilibrium.csv
```

## Tracker Comparison Results

Tracker data contains 3 tracked points: `质量_A/B/C`, each with independent `t,x,y`.

Estimated Tracker sample rate:

```text
12.05 Hz
```

Effective common duration:

```text
42.08 s
```

Main Tracker peaks:

```text
track 1: 2.277 Hz and 1.376 Hz
track 2: 1.376-1.399 Hz
track 3: 1.352-1.399 Hz
```

Model with solved equilibrium and small release:

```text
end bob high-frequency peak: about 2.25 Hz
low-frequency peak: about 1.21-1.25 Hz
lambda_max ≈ 0.077 s^-1
```

Model with solved equilibrium and 50 deg release:

```text
main peaks: about 1.00-1.04 Hz and 2.04 Hz
lambda_max ≈ 0.211 s^-1
```

Interpretation:

- The model captures the end-bob magnetic-coupling peak reasonably well.
- The low-frequency mode is too slow compared with Tracker.
- A likely correction is shorter effective pendulum length / center-of-mass distance than currently assumed.
- Large release angle makes the nonlinear pendulum frequency lower, so release angle alone does not fix the slow model peak.

## Key Figures

Use these first:

- `03_key_figures/tracker_vs_4cm_220mT_solved_eq_model_frequency.png`
- `03_key_figures/tracker_vs_4cm_220mT_release50deg_model_frequency.png`
- `03_key_figures/realfield_4cm_220mT_solved_eq_left_release_lyapunov.png`
- `03_key_figures/realfield_4cm_220mT_solved_eq_release50deg_lyapunov.png`
- `03_key_figures/cradle_initial_condition_response_map.png`

Important clarification on response map:

- The paper `一类典型磁力摆的全局动力学行为分析.pdf` uses a 2D magnetic pendulum with `(x,y)` degrees of freedom and multiple fixed-point attractors.
- Our cradle has five one-dimensional pendula, not a free `(x,y)` bob.
- Therefore, the appropriate visual is not a direct `(x,y)` basin of attraction.
- A more defensible visualization is a 2D slice of the 10D phase space, e.g. `(left release angle, left initial angular velocity) -> dominant responding bob`.
- Current file: `03_key_figures/cradle_initial_condition_response_map.png`.

## PPT

Presentation file:

```text
02_presentation/Magnetic_Newtons_Cradle_Theory_and_Simulation.pptx
```

Preview:

```text
02_presentation/ppt_preview_contact_sheet.png
```

The PPT has already been revised so formulas are presentation-style, not LaTeX/code blocks.

## Code Entrypoints

Generate finite-cylinder force table:

```powershell
powershell -ExecutionPolicy Bypass -File 05_code/run_force_table_java_5cm_220mT.ps1
```

Run real-field dynamics model:

```powershell
$env:MNC_CASE_PREFIX='realfield_4cm_220mT_solved_eq_release50deg'
$env:MNC_FORCE_TABLE='force_table_5cm_220mT_disk_2d.csv'
$env:MNC_MASS_KG='0.070'
$env:MNC_PIVOT_SPACING_M='0.040'
$env:MNC_DISK_RADIUS_M='0.015'
$env:MNC_MIN_GAP_M='0.0020'
$env:MNC_DURATION_S='24'
$env:MNC_USE_SOLVED_EQUILIBRIUM='1'
$env:MNC_RELEASE_INDEX='0'
$env:MNC_RELEASE_DELTA_RAD='-0.872664626'
python 05_code/analyze_realistic_field_model.py
```

Compare model with Tracker:

```powershell
$env:MNC_MODEL_CSV='realfield_4cm_220mT_solved_eq_release50deg_time_domain.csv'
$env:MNC_COMPARE_PREFIX='tracker_vs_4cm_220mT_release50deg_model'
python 05_code/compare_tracker_with_model_pil.py
```

Generate response map:

```powershell
python 05_code/make_cradle_initial_condition_response_map.py
```

Note: paths inside copied scripts may still point to the original project folder. If running only inside this handoff folder, update `ROOT`/file paths or run from the original project.

## Source Papers

Included:

- `06_sources/一类典型磁力摆的全局动力学行为分析.pdf`
- `06_sources/PhysRevX.8.021030.pdf`

The Chinese magnetic pendulum paper is useful for:

- basin-of-attraction methodology
- multi-attractor interpretation
- warning that initial-condition sensitivity may come from fractal basin boundaries, not only sustained chaos

But its system has different degrees of freedom than our cradle.

## Recommended Next Step

The biggest unresolved parameter is effective pendulum length:

```text
L_eff = suspension point to magnet center of mass
```

The model low-frequency peak is too low. To move it toward the Tracker peak near `1.38 Hz`, the effective length likely needs to be shorter than the current `13.2-13.5 cm` assumption.

Recommended next actions:

1. Measure `L_eff` directly from video or apparatus.
2. Use Tracker to extract all five magnets if possible, not only three.
3. Fit damping from a separate single-pendulum free-decay experiment.
4. Recompute frequency and Lyapunov estimates after correcting `L_eff`.
5. Treat response-domain plots as phase-space sections, not literal `(x,y)` fractal basins.
