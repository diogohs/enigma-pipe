# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-09-20

### Added
- **`enigma-sc` subcommand**: Automated containerized spinal cord analysis wrapping `pipeline-enigma-cli`.
  - Supports loose NIfTI datasets and native BIDS formatted datasets with multi-session / multi-run support.
  - Per-case container execution mounting isolated ephemeral staging directories to guarantee output encapsulation.
  - Strict output artifact verification (`verify_case_outputs`) requiring core segmentation artifacts (`*_seg.nii.gz`, `*_seg_labeled.nii.gz`, `*_labels_vert.nii.gz`, `*_csa.csv`) and summary CSVs.
  - Automatic post-batch consolidation into `csa_group_summary.csv` and `eccentricity_group_summary.csv` at dataset root.
  - Compute device selection (`--device cpu/gpu/cuda`) mapping to `--gpus all` (Docker) or `--nv` (Singularity/Apptainer), with host GPU pre-flight availability checks.
  - Custom container image resolution via `--image-sif` and `--image-docker`.
  - Resumption support via `--processing-mode continue` and `--existing-output resume/skip`.
- **Root CLI version flags**: Added `--version` and `-V` flags to `enigma-pipe`.

## [0.1.1] - 2026-09-18

### Added
- Initial stable release of `enigma-pipe` featuring:
  - `fastsurfer`: Automated FastSurfer structural processing with optional brainstem subsegmentation.
  - `brainstem`: Standalone FreeSurfer brainstem subsegmentation.
  - `mriqc`: Automated MRIQC image quality assessment for BIDS and loose NIfTI data.
  - `qc-img` & `qc-seg`: Interactive ITK-SNAP quality control workflows for structural images and segmentations.
  - `slicer`: Multi-slice PNG/JPEG capture generation with MNI template registration.
