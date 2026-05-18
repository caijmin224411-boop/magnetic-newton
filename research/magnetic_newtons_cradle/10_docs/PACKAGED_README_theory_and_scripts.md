# Magnetic Newtons Cradle: Theory Application and Script Guide

## Research Logic

The goal is not to force the model to match every video frame. The better goal is:

1. Calibrate physical parameters: effective length, damping, magnetic force scale.
2. Explain main frequency modes and how they change with pivot spacing.
3. Describe time-domain complexity: energy exchange, envelope decay, irregular peak intervals.

The current model should be treated as a semi-quantitative physical model, not a final precision engineering model.

## Basic Equation

For bob `i`, define angle `theta_i`, angular velocity `omega_i`, length `L_i`, mass `m_i`, and moment of inertia:

```math
I_i=m_i L_i^2
```

The equation of motion is:

```math
I_i ddot(theta_i) = tau_g,i + tau_m,i + tau_d,i
```

Gravity torque:

```math
tau_g,i = -m_i g L_i sin(theta_i)
```

Nonlinear damping torque calibrated from single-pendulum data:

```math
tau_d,i = -c1_i dot(theta_i) - c2_i dot(theta_i)|dot(theta_i)|
```

Magnetic torque:

```math
tau_m,i = sum_{j != i} tau_ij
```

The current model mainly uses neighboring interactions. A better model should also test non-neighbor magnetic coupling.

## Magnetic Coupling Strength

Magnetic coupling strength is not simply the surface field in mT. It is closer to the effective angular stiffness caused by magnetic torque. Near equilibrium:

```math
tau_ij approx -k_m(theta_i - theta_j)
```

where `k_m` is the magnetic coupling stiffness.

A useful dimensionless parameter is:

```math
eta = k_m/(mgL)
```

- `eta << 1`: weak coupling, close to independent pendulums
- `eta ~ 1`: strong coupling, clear mode splitting
- `eta > 1`: magnetic torque dominates, strong nonlinear behavior is likely

Magnetic coupling depends on pivot spacing, magnet strength, magnet geometry, vertical offset, length, and mass.

## Why Initial Release Matters

For a single small-angle pendulum:

```math
f0 = (1/2pi) sqrt(g/L)
```

So length controls the basic frequency. But the magnetic Newtons cradle is a coupled multi-pendulum system. It has multiple modes:

```math
f1, f2, f3, ...
```

Initial release does not freely set these modal frequencies. It mainly changes modal amplitudes:

```math
theta(t) = A1 phi1 cos(2pi f1 t + phi_1) + A2 phi2 cos(2pi f2 t + phi_2) + ...
```

Therefore release conditions affect which peaks are strong, time-domain phase, energy exchange sequence, and small nonlinear frequency shifts at large amplitude.

## Current Evidence

### 3 cm spacing

Experiment:

```text
1.396 Hz, 2.188 Hz, 3.274 Hz
```

Model with unified magnetic force scale `0.5`:

```text
1.417 Hz, 2.333 Hz, 3.550 Hz
```

The low mode is good, but high modes are too high. The strong-coupling model is too stiff.

### 5 cm spacing

Experiment:

```text
1.387 Hz, 1.846 Hz, 2.543 Hz
```

Model with unified magnetic force scale `0.5`:

```text
1.433 Hz, 1.883 Hz, 2.517 Hz
```

The first three main peaks agree reasonably well. The model works better in the weaker-coupling condition.

## Honest Conclusion

The model can explain:

- length controls the basic pendulum frequency
- pivot spacing changes coupled modes
- weaker coupling gives faster visible decay
- multiple frequency peaks arise from coupled modes
- time-domain energy exchange is not simple Newton-cradle transfer

The model still cannot fully explain:

- static equilibrium and dynamic frequency with one perfect parameter set
- exact frame-by-frame trajectories
- some high-frequency experimental peaks, such as around `3.37 Hz` in 5 cm data

Missing nonideal factors:

- different real lengths for the five bobs
- nonzero release velocities
- magnet posture and string torsion
- non-neighbor magnetic coupling
- camera perspective error
- amplitude-dependent damping and small contact losses

## Recommended Next Research Steps

1. Calibrate each bob separately to get `L_i`, `c1_i`, `c2_i`.
2. Measure static equilibrium angles for `3 cm`, `4 cm`, `5 cm`, `6 cm`.
3. Repeat each release at least three times and compare frequencies, RMS decay, and peak interval CV.
4. Add initial velocities and non-neighbor coupling to the model.
5. Use one unified magnetic force scale. Do not tune magnetic scale separately for every experiment.

## Package Structure

### 01_single_pendulum_calibration

Scripts for effective length and damping calibration.

### 02_magnetic_model_and_force_table

Scripts for magnetic force table generation and five-bob dynamics simulation.

### 03_experiment_time_frequency_analysis

Scripts for tracker data cleaning and time/frequency analysis.

### 04_model_experiment_comparison

Scripts for model-experiment comparison, including the adjustable GUI.

### 05_document_generation

Scripts for generating theory DOCX/PPTX.

### 06_key_outputs

Important result summaries and current comparison outputs.
