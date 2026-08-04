# enigma-pipe

A command-line interface for running containerized neuroimaging pipelines. It wraps FastSurfer, MRIQC, FreeSurfer brainstem subsegmentation, and interactive quality-control workflows behind a single, scriptable entry point designed for both workstation and HPC use.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Container Images](#container-images)
  - [Option A: Docker](#option-a-docker)
  - [Option B: Singularity / Apptainer](#option-b-singularity--apptainer)
- [Quick Start](#quick-start)
- [Commands](#commands)
  - [fastsurfer](#fastsurfer)
  - [brainstem](#brainstem)
  - [mriqc](#mriqc)
  - [qc-img](#qc-img)
  - [qc-seg](#qc-seg)
  - [slicer](#slicer)
- [Global Options](#global-options)
- [Configuration](#configuration)
  - [YAML Settings File](#yaml-settings-file)
  - [Environment Variables](#environment-variables)
  - [Precedence](#precedence)
- [Processing Modes and Output Policies](#processing-modes-and-output-policies)
- [Exit Codes](#exit-codes)
- [Project Structure](#project-structure)
- [Development](#development)
- [License](#license)

## Prerequisites

| Dependency | Required By | Notes |
|---|---|---|
| Python >= 3.10 | All | Runtime environment. |
| Docker **or** Singularity/Apptainer | `fastsurfer`, `mriqc` | At least one container runtime must be available on `PATH`. See [Container Images](#container-images) below. |
| FreeSurfer (>= 7.3) | `fastsurfer`, `brainstem` | `segment_subregions` must be on `PATH`. A valid FreeSurfer license file is required. |
| ITK-SNAP | `qc-img`, `qc-seg` | Must be on `PATH` or specified via settings. |
| ANTsPy | `slicer` | Installed automatically as a Python dependency (`antspyx`). |

## Installation

Clone the repository:

```bash
git clone https://github.com/diogohs/enigma-pipe.git
cd enigma-pipe
```

### Option A: Using uv (recommended)

```bash
uv sync
```

To include development dependencies:

```bash
uv sync --group dev
```

### Option B: Using pip

```bash
pip install -e .
```

To include development dependencies:

```bash
pip install -e ".[dev]"
```

### Verify

```bash
enigma-pipe --help
```

---

## Container Images

`enigma-pipe` delegates the heavy processing to containers. You need to obtain the images before running `fastsurfer` or `mriqc`. Choose **one** of the two approaches below.

### Option A: Docker

Docker downloads images automatically on first use — no extra steps needed. Make sure the Docker daemon is running:

```bash
docker info
```

Images used:

| Command | Image |
|---|---|
| `fastsurfer` | `deepmi/fastsurfer:latest` |
| `mriqc` | `nipreps/mriqc:latest` |

### Option B: Singularity / Apptainer

Singularity and Apptainer work with local `.sif` files. You must build the images before running the pipeline. Run the commands below **once** on your system:

```bash
# Create the folder that will hold the container images
mkdir -p "$HOME/enigma-pipe/images"

# Build FastSurfer
singularity build \
    "$HOME/enigma-pipe/images/fastsurfer.sif" \
    docker://deepmi/fastsurfer:latest

# Build MRIQC
singularity build \
    "$HOME/enigma-pipe/images/mriqc.sif" \
    docker://nipreps/mriqc:latest
```

> **Note:** Replace `singularity` with `apptainer` if that is the command on your system. The flags and arguments are identical.

Verify that both images were created successfully:

```bash
ls -lh "$HOME/enigma-pipe/images/"*.sif
```

Expected output (sizes will vary):

```
-rw-r--r-- 1 user group 12G ... fastsurfer.sif
-rw-r--r-- 1 user group  8G ... mriqc.sif
```

By default, `enigma-pipe` looks for images at `~/enigma-pipe/images/fastsurfer.sif` and `~/enigma-pipe/images/mriqc.sif`. If you saved them elsewhere, use the `--image-sif` option or the environment variables described in [Configuration](#configuration).

#### How FastSurfer is called inside the container

When running with Singularity or Apptainer, `enigma-pipe` invokes FastSurfer through its main script:

```
/fastsurfer/run_fastsurfer.sh
```

This is the standard interface used by all FastSurfer installation modes. Unlike Docker (which uses the image entrypoint automatically), `singularity exec` requires the script to be stated explicitly — `enigma-pipe` handles this for you.

## Quick Start

Run FastSurfer structural processing on a directory of T1-weighted images:

```bash
enigma-pipe fastsurfer /data/raw /data/output --fs-license /opt/freesurfer/license.txt
```

Run automated image quality assessment on a BIDS dataset:

```bash
enigma-pipe mriqc /data/bids /data/mriqc_output
```

Generate slice captures from existing FastSurfer output:

```bash
enigma-pipe slicer /data/output /data/captures --format png
```

## Commands

### fastsurfer

Runs the FastSurfer structural processing pipeline via a container runtime. By default, brainstem subsegmentation is executed after each case completes successfully.

```bash
enigma-pipe fastsurfer INPUT_DIR OUTPUT_DIR [OPTIONS]
```

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `INPUT_DIR` | path (required) | -- | Directory containing T1-weighted images. |
| `OUTPUT_DIR` | path (required) | -- | Output directory for processed results. |
| `--fs-license` | path | None | Path to FreeSurfer license file. Required unless set in YAML settings. |
| `--execution-mode` | string | `docker` | Container runtime: `docker`, `singularity`, or `apptainer`. |
| `--image-sif` | path | `~/enigma-pipe/images/fastsurfer.sif` | Path to a custom Apptainer/Singularity `.sif` file. Overrides `ENIGMA_PIPE_FASTSURFER_IMAGE`. |
| `--processing-mode` | string | `all` | Case selection: `all`, `continue`, or path to a selection file. |
| `--existing-output` | string | `error` | Policy when output exists: `error`, `skip`, `resume`, or `replace`. |
| `--device` | string | `cpu` | Compute device: `cpu`, `gpu`, or `cuda`. |
| `--threads` | string | None | Thread count or `max`. |
| `--no-asegdkt` | flag | false | Skip whole-brain segmentation. |
| `--no-cc` | flag | false | Skip corpus callosum segmentation. |
| `--no-cereb` | flag | false | Skip cerebellum segmentation. |
| `--no-hypothal` | flag | true | Skip hypothalamus segmentation. |
| `--no-brainstem` | flag | false | Skip brainstem subsegmentation. |
| `--skip-version-check` | flag | false | Bypass FastSurfer version validation. |

---

### brainstem

Runs standalone brainstem subsegmentation on existing FastSurfer output directories. Requires FreeSurfer `segment_subregions` on `PATH`.

```bash
enigma-pipe brainstem INPUT_DIR [OPTIONS]
```

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `INPUT_DIR` | path (required) | -- | Directory containing FastSurfer output (single case or parent of multiple cases). |
| `--processing-mode` | string | `all` | Case selection: `all`, `continue`, or path to a selection file. |
| `--existing-output` | string | `error` | Policy when output exists: `error`, `skip`, `resume`, or `replace`. |
| `--threads` | integer | None | Thread count for segmentation. |

---

### mriqc

Runs the MRIQC automated image quality assessment pipeline via a container runtime.

The input directory can be:
- An existing **BIDS dataset** (containing `dataset_description.json` and T1w images under `sub-*/anat/`); or
- A plain directory with **loose `.nii` / `.nii.gz` T1-weighted images** — `enigma-pipe` will automatically create a temporary BIDS structure before calling MRIQC.

```bash
enigma-pipe mriqc INPUT_DIR OUTPUT_DIR [WORK_DIR] [OPTIONS]
```

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `INPUT_DIR` | path (required) | -- | BIDS dataset or directory containing loose T1w NIfTI images. |
| `OUTPUT_DIR` | path (required) | -- | Output directory for MRIQC results. |
| `WORK_DIR` | path (optional) | None | Scratch/working directory. |
| `--execution-mode` | string | `docker` | Container runtime: `docker`, `singularity`, or `apptainer`. |
| `--image-sif` | path | `~/enigma-pipe/images/mriqc.sif` | Path to a custom Apptainer/Singularity `.sif` file. Overrides `ENIGMA_PIPE_MRIQC_IMAGE`. |
| `--participant-label` | list | None | Restrict processing to specific participant labels. |
| `--nprocs` | integer | None | Number of processors to use. |

---

### qc-img

Interactive image quality control. Opens each T1-weighted image in ITK-SNAP and prompts the operator for a rating (0--5) and an optional comment. Results are written to a per-case CSV file.

This command requires a display and a live terminal (TTY). It is not suitable for unattended batch submission.

```bash
enigma-pipe qc-img INPUT_DIR OUTPUT_DIR [OPTIONS]
```

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `INPUT_DIR` | path (required) | -- | Directory containing T1-weighted images. |
| `OUTPUT_DIR` | path (required) | -- | Output directory for QC records. |
| `--processing-mode` | string | `all` | Case selection mode. |
| `--existing-output` | string | `skip` | Existing output policy. |
| `--reviewer-id` | string | OS username | Identifier for the reviewer. |

---

### qc-seg

Interactive segmentation quality control. Opens the T1 image with each configured segmentation overlay in ITK-SNAP and prompts for a per-segmentation rating (0--5) and comment.

This command requires a display and a live terminal (TTY). It is not suitable for unattended batch submission.

```bash
enigma-pipe qc-seg INPUT_DIR OUTPUT_DIR [OPTIONS]
```

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `INPUT_DIR` | path (required) | -- | Directory containing FastSurfer outputs. |
| `OUTPUT_DIR` | path (required) | -- | Output directory for QC records. |
| `--processing-mode` | string | `all` | Case selection mode. |
| `--existing-output` | string | `skip` | Existing output policy. |
| `--reviewer-id` | string | OS username | Identifier for the reviewer. |

Segmentation types evaluated are configured via the YAML settings file (`segmentation_to_eval`). Supported types: `aseg`, `brainstem`, `cerebnet`, `enigma-sc`.

---

### slicer

Generates slice capture images (PNG or JPEG) of the T1 volume and configured segmentation overlays. Optionally registers images to the MNI152 template via rigid (6 DOF) registration before capture. A bundled MNI template and FreeSurfer color lookup table are included with the package.

```bash
enigma-pipe slicer INPUT_DIR OUTPUT_DIR [OPTIONS]
```

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `INPUT_DIR` | path (required) | -- | Directory containing FastSurfer outputs. |
| `OUTPUT_DIR` | path (required) | -- | Output directory for captures. |
| `--mni-template` | path | bundled | Path to MNI152 template. Falls back to the bundled template. |
| `--lut` | path | auto | Path to a LUT/colormap file. Auto-detected from case directory or bundled data. |
| `--processing-mode` | string | `all` | Case selection mode. |
| `--existing-output` | string | `skip` | Existing output policy. |
| `--alpha` | float | `0.5` | Overlay alpha blending (0.0--1.0). |
| `--step` | integer | `1` | Interval between consecutive slices. |
| `--padding` | integer | `10` | Padding around the segmentation bounding box in voxels. |
| `--skip-empty` | flag | false | Omit slices where both segmentation and image are empty. |
| `--format` | string | `jpeg` | Output image format (`png`, `jpeg`, `jpg`). |
| `--neurological-orientation` | flag | true | Use neurological (left-is-left) orientation. |
| `--image-source` | string | `mri/brainmask.mgz` | Background image path relative to each case root. |
| `--max-longest-side` | integer | `240` | Maximum longest side of each output image in pixels. |
| `--register/--no-register` | flag | true | Enable or disable rigid registration to MNI. |

## Global Options

These options are available on every invocation, before the subcommand:

```bash
enigma-pipe [GLOBAL OPTIONS] COMMAND [ARGS]
```

| Option | Description |
|---|---|
| `--verbose`, `-v` | Enable verbose output. |
| `--debug`, `-d` | Enable debug output. |
| `--json` | Print the final run summary to stdout as structured JSON. |
| `--settings`, `-s` | Path to a YAML settings file. |

## Configuration

### YAML Settings File

A YAML file can be passed via `--settings` (or `-s`) to provide defaults for options that would otherwise need to be repeated on every invocation:

```yaml
fs_license: /opt/freesurfer/license.txt
execution_mode: docker
itksnap_path: /usr/bin/itksnap
reviewer_id: reviewer_01
segmentation_to_eval:
  - aseg
  - brainstem
  - cerebnet
```

Unknown keys are rejected at startup (exit code 2).

### Environment Variables

All settings can also be provided via environment variables prefixed with `ENIGMA_PIPE_`. Nested keys use double underscores as delimiters.

General settings:

```bash
export ENIGMA_PIPE_FS_LICENSE=/opt/freesurfer/license.txt
export ENIGMA_PIPE_REVIEWER_ID=reviewer_01
```

Container image overrides (useful when images are not in the default `~/enigma-pipe/images` location):

```bash
export ENIGMA_PIPE_FASTSURFER_IMAGE=/data/containers/fastsurfer.sif
export ENIGMA_PIPE_MRIQC_IMAGE=/data/containers/mriqc.sif
```

These variables are overridden by the `--image-sif` CLI option.

### Precedence

Configuration values are resolved in the following order (highest to lowest priority):

1. CLI argument
2. YAML settings file
3. Environment variable
4. Built-in default

## Processing Modes and Output Policies

All batch-oriented commands (`fastsurfer`, `brainstem`, `mriqc`, `qc-img`, `qc-seg`, `slicer`) accept two orthogonal arguments that control case selection and conflict resolution:

| `--processing-mode` | Behavior |
|---|---|
| `all` (default) | Select every eligible case in the input directory. |
| `continue` | Select only cases without a successful completion manifest. |
| `<path>` | Select only cases listed in the specified text file. |

| `--existing-output` | Behavior |
|---|---|
| `error` (default) | Abort if output already exists for a selected case. |
| `skip` | Leave existing output untouched and do not reprocess. |
| `resume` | Continue incomplete output where supported; otherwise replace. |
| `replace` | Delete existing output and reprocess from scratch. |

Each processed case produces a completion manifest at `<output>/<case_id>/<subcommand>_manifest.json`, which serves as the authoritative record of processing status.

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | All requested cases processed successfully. |
| 1 | Generic or unexpected runtime error. |
| 2 | Invalid arguments or settings validation failure. |
| 3 | Missing required external dependency. |
| 4 | Partial failure: one or more cases failed while others succeeded. |
| 130 | Interrupted by the user (SIGINT / Ctrl+C). |

## Project Structure

```
enigma-pipe/
  src/enigma_pipe/
    cli/
      main.py              CLI entry point and global options (Typer).
      formatting.py         Logging configuration (Loguru) and output helpers.
      commands/
        fastsurfer.py       FastSurfer structural processing command.
        brainstem.py        Standalone brainstem subsegmentation command.
        mriqc.py            MRIQC quality assessment command.
        qc_img.py           Interactive image QC command.
        qc_seg.py           Interactive segmentation QC command.
        slicer.py           Slice capture generation command.
    core/
      config.py             YAML/env settings (Pydantic).
      constants.py          Exit codes, version constraints, defaults.
      exceptions.py         Structured error hierarchy.
      manifest.py           Completion manifest read/write.
      models.py             Enumerations and data classes.
    services/
      container.py          Docker/Singularity/Apptainer abstraction.
      fastsurfer.py         FastSurfer container runner.
      mriqc.py              MRIQC container runner.
      brainstem_seg.py      FreeSurfer brainstem subsegmentation.
      case_discovery.py     Deterministic input directory traversal.
      itksnap.py            ITK-SNAP process management.
      registration.py       ANTs rigid registration to MNI.
      slicer.py             Slice capture rendering.
      lut.py                FreeSurfer LUT parser.
      qc_image.py           Image QC CSV writer.
      qc_segmentation.py    Segmentation QC CSV writer.
      atomic.py             Atomic file write utility.
    data/
      FreeSurferColorLUT.txt    Bundled color lookup table.
      mni_icbm152_t1_tal_nlin_sym_09c.nii    Bundled MNI152 template.
  tests/
    cli/                    CLI integration tests.
    unit/                   Unit tests.
    integration/            Integration tests.
  docs/
    Specification_v6.md     Full functional specification.
    test_plan.md            Manual test plan.
```

## Development

Install development dependencies:

Using uv:

```bash
uv sync --group dev
```

Using pip:

```bash
pip install -e ".[dev]"
```

Run the test suite:

```bash
uv run pytest
```

Run the linter:

```bash
uv run ruff check src/ tests/
```

Run the formatter:

```bash
uv run black src/ tests/
```

Run type checking:

```bash
uv run mypy src/
```

## License

This project is distributed under the MIT License. See `LICENSE` for details.
