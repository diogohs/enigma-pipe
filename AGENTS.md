# AGENTS.md

This document serves as a guide for AI coding agents working on the `enigma-pipe` project. It synthesizes architectural principles, coding standards, and development workflows derived from the project's Speckit documentation, specifications, and configuration files.

## Project Overview

`enigma-pipe` is a command-line interface for running containerized neuroimaging pipelines. It wraps FastSurfer, MRIQC, FreeSurfer brainstem subsegmentation, and interactive quality-control workflows (via ITK-SNAP) behind a single, scriptable entry point. It is explicitly designed to support both interactive workstation usage and unattended HPC batch submission (e.g., SLURM, SGE).

**Core Technologies:**
* **Python**: >=3.10
* **CLI Framework**: Typer, Rich
* **Configuration**: Pydantic, Pydantic-Settings
* **Logging**: Loguru
* **Container Runtimes**: Docker, Singularity, Apptainer
* **Neuroimaging Tools**: nibabel, ANTsPy (antspyx)

## Repository Structure

* **`src/enigma_pipe/`**: Main source code package.
  * **`cli/`**: Typer application entry points (`main.py`) and specific command modules (`commands/`). Also handles formatting and logging configuration.
  * **`core/`**: Domain models, Pydantic configuration schemas, standardized exceptions, validation logic, and constants.
  * **`services/`**: Core business logic and external integrations. Contains the `ContainerRunner` abstraction, specific runners (`fastsurfer.py`, `mriqc.py`), and other services (`itksnap.py`, `slicer.py`, `brainstem_seg.py`).
  * **`data/`**: Bundled resources (e.g., FreeSurfer lookup tables, MNI templates).
* **`tests/`**: Pytest test suite, organized into `unit/`, `integration/`, and `cli/`.
* **`docs/`**: Technical documentation, including manual test plans and comprehensive specifications (e.g., `Specification_v6.md`).
* **`specs/`**: Speckit feature designs, workflows, and task tracking.
* **`pyproject.toml`**: Project dependencies and tool configurations (Hatchling, Ruff, Black, Mypy, Pytest).

## Development Workflow

### Installation

Use `uv` (recommended) or `pip` to install the project with development dependencies:
```bash
uv sync --group dev
# Or with pip:
pip install -e ".[dev]"
```

### Running Locally
The CLI is exposed as `enigma-pipe`. During development, run it via `uv`:
```bash
uv run enigma-pipe --help
```

### Validation Commands
Agents must validate their work before concluding a task by running the following commands:
1. **Formatting**: `uv run black src/ tests/`
2. **Linting**: `uv run ruff check src/ tests/`
3. **Type Checking**: `uv run mypy src/`
4. **Testing**: `uv run pytest`

## Coding Standards

* **Naming Conventions**: Follow standard Python conventions (PEP 8). CLI commands and arguments should use kebab-case (e.g., `fastsurfer`, `--fs-license`).
* **Configuration Precedence**: Configuration resolution strictly follows this hierarchy:
  1. CLI Argument
  2. YAML Settings File (validated via Pydantic)
  3. Environment Variable
  4. Built-in Default
* **Error Handling**: Use the structured exception hierarchy found in `core/exceptions.py`. Do not raise generic Python exceptions for domain-specific errors.
* **Exit Codes**: The application uses specific exit codes to signal state to HPC schedulers. Adhere to the established constants (e.g., `0` for success, `1` for generic error, `2` for invalid arguments, `3` for missing dependency, `4` for partial failures, `130` for user interrupt).
* **Logging**: Use `loguru` and `rich`. Normal execution should not be excessively noisy. Print warnings/errors to stderr. Detailed debugging should be hidden behind `--verbose` or `--debug` flags.
* **File Operations**: Use `pathlib.Path`. Atomic writes are mandatory for output generation (e.g., write to `.tmp`, then use `os.replace` to rename to the final path) to avoid leaving corrupted files on interruption.

## Testing Expectations

* **Framework**: `pytest`
* **Coverage**: The project enforces coverage reporting (`--cov=src/enigma_pipe`). Ensure tests are added for all new logic.
* **Structure**: Place unit tests in `tests/unit/` and CLI interaction tests in `tests/cli/`.
* **Mocking**: External dependencies (FreeSurfer, Docker, Singularity, ITK-SNAP) must be mocked appropriately during unit and CLI testing.

## Architecture Guidelines

* **Separation of Concerns**: The CLI layer (`cli/`) handles argument parsing and printing. It delegates all heavy lifting to the Services layer (`services/`). Services depend on the Core layer (`core/`), which is independent of everything else.
* **State Management**: The CLI is inherently stateless. "Completion Manifests" (`<case_id>/<subcommand>_manifest.json`) are the single source of truth for tracking whether a specific pipeline stage was successfully completed for a case. Do not rely on ad-hoc file existence checks (like CSVs).
* **Container Execution**: The `ContainerRunner` class abstracts the underlying runtime (Docker vs. Singularity). Singularity executions must explicitly invoke internal scripts (e.g., `/fastsurfer/run_fastsurfer.sh`) instead of relying on Docker entrypoints.
* **Interactivity Constraints**: Commands like `fastsurfer` and `mriqc` are designed for unattended batch execution. They must never block on interactive prompts. Interactive commands (`qc-img`, `qc-seg`) are the only exception and are scoped out of unattended HPC usage.

## Agent Instructions

* **Read First**: Always read the relevant source files and existing abstractions before implementing new logic.
* **Extend, Don't Reinvent**: Use existing abstractions (like `ContainerRunner`, `validate_threads`, `CaseOutcome`) rather than writing new ones for similar purposes.
* **Preserve Integrity**: Do not break backward compatibility unless explicitly instructed to do so.
* **Update Documentation**: If modifying CLI arguments, update the help text and reflect the changes in `README.md`.
* **Security**: Never commit secrets, license files, or patient data.
* **Validation**: Run the Validation Checklist strictly before completing any task.

## Important Files

Familiarize yourself with these files before making architectural changes:
* `src/enigma_pipe/cli/main.py`: The root Typer application.
* `src/enigma_pipe/services/container.py`: The `ContainerRunner` abstraction.
* `src/enigma_pipe/core/manifest.py`: Logic for writing and reading JSON completion manifests.
* `src/enigma_pipe/core/config.py`: The Pydantic settings model.
* `pyproject.toml`: The Hatchling configuration, strict Mypy settings, and dependencies.
