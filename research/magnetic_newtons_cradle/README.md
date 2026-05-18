# Magnetic Newtons Cradle Research Package

This folder contains reusable scripts, cleaned data tables, and key figures from the magnetic Newtons cradle study.

## What Is Included

- `00_readme/`: handoff notes and research logic.
- `01_single_pendulum_calibration/`: effective length and nonlinear damping calibration scripts.
- `02_magnetic_model_and_force_table/`: magnetic force table and five-bob dynamics model scripts.
- `03_experiment_time_frequency_analysis/`: tracker data cleaning and FFT/time-domain analysis scripts.
- `04_model_experiment_comparison/`: model-experiment comparison and parameter GUI scripts.
- `05_document_generation/`: PPT/DOCX generation scripts.
- `06_key_outputs/`: compact early result summaries from the first curated package.
- `07_recent_analysis_scripts/`: newer reusable analysis scripts, including release-angle spectra, Lyapunov checks, phase/Poincare analysis, force diagrams, and motion/phase video generation.
- `08_reusable_data_outputs/`: selected CSV/JSON outputs used for repeatable analysis.
- `09_key_figures/`: selected exported figures for reports and presentations.
- `10_docs/`: theory notes, handoff docs, and COMSOL notes.

## Current Modeling Assumptions

- Rigid rods, not strings.
- Cylindrical magnets, not spherical bobs.
- Effective pendulum length near `12 cm`.
- Current reference magnetic scale is `0.5`.
- `5 cm` pivot spacing behaves closer to weak coupling and matches experiments better.
- `3 cm` pivot spacing enters stronger nonlinear coupling; the model reproduces the trend but not every peak and amplitude.

## Recommended Entry Points

Run these from this folder or adjust paths inside the scripts:

```powershell
python 07_recent_analysis_scripts\make_release_angle_frequency_sweep.py
python 07_recent_analysis_scripts\export_theory_experiment_pair_plots.py
python 07_recent_analysis_scripts\compute_real_data_lyapunov.py
python 07_recent_analysis_scripts\make_phase_poincare_plots.py
python 07_recent_analysis_scripts\realtime_motion_simulator.py
```

The original interactive recorder and web tracker live at the repository root. This research package is the reusable analysis layer built on top of those tracking outputs.

## Notes

Large videos, COMSOL `.mph` files, compiled Java classes, logs, and cache files are intentionally excluded from git. The committed material is meant to be enough to rerun and explain the current conclusions without turning the repository into a raw-data archive.
