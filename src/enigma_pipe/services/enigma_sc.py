from __future__ import annotations

import csv
import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from enigma_pipe.cli.formatting import print_error, print_info, print_warning
from enigma_pipe.core.exceptions import MissingDependencyError
from enigma_pipe.core.models import ExecutionMode, ExistingOutputPolicy, ProcessingMode
from enigma_pipe.services.case_discovery import DiscoveryResult, discover_cases
from enigma_pipe.services.case_identifier import derive_case_id
from enigma_pipe.services.container import ContainerRunner

# Default container images
DEFAULT_DOCKER_IMAGE = "art2mri/pipeline_enigma_cli:1.0"
DEFAULT_SIF_IMAGE = Path.home() / "enigma-pipe" / "images" / "pipeline_enigma_cli.sif"
LEGACY_SIF_IMAGE = Path.home() / "enigma-pipe" / "images" / "pipeline-enigma-cli.sif"
ENIGMA_SC_ENTRYPOINT = ["python3", "/enigma_pipeline.py"]


def check_gpu_availability() -> bool:
    """Check whether NVIDIA GPU and nvidia-smi are available on host."""
    try:
        res = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            check=False,
            text=True,
        )
        return res.returncode == 0
    except (FileNotFoundError, PermissionError):
        return False


def verify_case_outputs(output_dir: Path, case_id: str) -> tuple[bool, str | None]:
    """
    Verify that all mandatory output files exist for a processed case.
    Required artifacts in <output_dir>/<case_id>/:
      1. <case_id>/<case_id>_seg.nii.gz
      2. <case_id>/<case_id>_seg_labeled.nii.gz
      3. <case_id>/<case_id>_labels_vert.nii.gz
      4. <case_id>/<case_id>_csa.csv
      5. At least one summary CSV (csa_final_table_*.csv or eccentricity_table_*.csv)
    """
    case_out = output_dir / case_id
    subfolder = case_out / case_id

    missing: list[str] = []
    # 1. Check core segmentations and metrics in subject subfolder
    core_files = [
        f"{case_id}_seg.nii.gz",
        f"{case_id}_seg_labeled.nii.gz",
        f"{case_id}_labels_vert.nii.gz",
        f"{case_id}_csa.csv",
    ]
    for filename in core_files:
        if not (subfolder / filename).is_file():
            missing.append(f"{case_id}/{filename}")

    # 2. Check summary tables in case output directory
    csa_tables = list(case_out.glob("csa_final_table_*.csv"))
    ecc_tables = list(case_out.glob("eccentricity_table_*.csv"))

    if not csa_tables and not ecc_tables:
        missing.append("csa_final_table_*.csv or eccentricity_table_*.csv")

    if missing:
        return False, f"Missing required output artifacts: {', '.join(missing)}"
    return True, None


def consolidate_group_tables(
    output_dir: Path, case_ids: Sequence[str]
) -> tuple[Path | None, Path | None]:
    """
    Consolidate per-subject summary CSVs into group-level summary CSVs at the output root.
    Generates:
      - <output_dir>/csa_group_summary.csv
      - <output_dir>/eccentricity_group_summary.csv
    If zero cases completed successfully or no tables are found, logs notice and returns (None, None).
    """
    if not case_ids:
        print_info("No successful cases to consolidate into group summary tables.")
        return None, None

    csa_rows: list[list[str]] = []
    csa_header: list[str] | None = None

    ecc_rows: list[list[str]] = []
    ecc_header: list[str] | None = None

    for case_id in sorted(case_ids):
        case_dir = output_dir / case_id
        if not case_dir.is_dir():
            continue

        # Find latest/matching CSA summary table
        csa_candidates = sorted(case_dir.glob("csa_final_table_*.csv"))
        if csa_candidates:
            csa_file = csa_candidates[-1]
            try:
                with open(csa_file, "r", newline="", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    header = next(reader, None)
                    if header:
                        if csa_header is None:
                            csa_header = header
                        for row in reader:
                            if row:
                                csa_rows.append(row)
            except Exception as e:  # noqa: BLE001
                print_warning(f"Could not read CSA table for case '{case_id}': {e}")

        # Find latest/matching Eccentricity summary table
        ecc_candidates = sorted(case_dir.glob("eccentricity_table_*.csv"))
        if ecc_candidates:
            ecc_file = ecc_candidates[-1]
            try:
                with open(ecc_file, "r", newline="", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    header = next(reader, None)
                    if header:
                        if ecc_header is None:
                            ecc_header = header
                        for row in reader:
                            if row:
                                ecc_rows.append(row)
            except Exception as e:  # noqa: BLE001
                print_warning(f"Could not read eccentricity table for case '{case_id}': {e}")

    csa_out_path: Path | None = None
    ecc_out_path: Path | None = None

    # Write csa_group_summary.csv atomically if rows found
    if csa_header and csa_rows:
        target = output_dir / "csa_group_summary.csv"
        tmp_target = output_dir / ".csa_group_summary.csv.tmp"
        try:
            with open(tmp_target, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(csa_header)
                writer.writerows(csa_rows)
            os.replace(tmp_target, target)
            csa_out_path = target
        except Exception as e:  # noqa: BLE001
            if tmp_target.exists():
                tmp_target.unlink(missing_ok=True)
            print_error(f"Failed to write group CSA summary table: {e}")

    # Write eccentricity_group_summary.csv atomically if rows found
    if ecc_header and ecc_rows:
        target = output_dir / "eccentricity_group_summary.csv"
        tmp_target = output_dir / ".eccentricity_group_summary.csv.tmp"
        try:
            with open(tmp_target, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(ecc_header)
                writer.writerows(ecc_rows)
            os.replace(tmp_target, target)
            ecc_out_path = target
        except Exception as e:  # noqa: BLE001
            if tmp_target.exists():
                tmp_target.unlink(missing_ok=True)
            print_error(f"Failed to write group eccentricity summary table: {e}")

    return csa_out_path, ecc_out_path


def derive_bids_case_id(file_path: Path) -> str:
    """
    Extract a unique case identifier from a BIDS T1w scan path,
    preserving participant, session, and run entities while stripping the _T1w suffix.
    """
    case_id = derive_case_id(file_path)
    return case_id.removesuffix("_T1w")


def is_bids_dataset(input_dir: Path) -> bool:
    """
    Check if a directory conforms to a BIDS dataset layout.
    Detects dataset_description.json or presence of participant directories (sub-*).
    """
    if not input_dir.is_dir():
        return False
    if (input_dir / "dataset_description.json").is_file():
        return True
    for child in input_dir.iterdir():
        if child.is_dir() and child.name.startswith("sub-"):
            return True
    return False


def stage_case_input(
    source_path: Path,
    target_dir: Path,
    target_filename: str,
) -> Path:
    """
    Stage an input NIfTI file into target_dir using hardlink when possible,
    falling back to file copy if linking fails.
    Returns the Path to the staged file.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    staged_path = target_dir / target_filename
    if staged_path.exists():
        staged_path.unlink()

    resolved_source = source_path.resolve()
    try:
        os.link(resolved_source, staged_path)
    except OSError:
        shutil.copy2(resolved_source, staged_path)

    return staged_path


def discover_bids_cases(
    input_dir: Path,
    output_dir: Path,
    subcommand: str = "enigma-sc",
    processing_mode: ProcessingMode = ProcessingMode.ALL,
    existing_output: ExistingOutputPolicy = ExistingOutputPolicy.ERROR,
) -> DiscoveryResult:
    """
    Discover T1w anatomical scans from a BIDS dataset layout,
    deriving unique case identifiers preserving session and run entities.
    """
    return discover_cases(
        input_dir=input_dir,
        output_dir=output_dir,
        subcommand=subcommand,
        processing_mode=processing_mode,
        existing_output=existing_output,
        extensions=("T1w.nii.gz", "T1w.nii"),
        case_id_extractor=derive_bids_case_id,
    )


class EnigmaSCRunner(ContainerRunner):
    """Container runner for the ENIGMA Spinal Cord pipeline."""

    def __init__(
        self,
        mode: ExecutionMode,
        image_sif: str | None = None,
        image_docker: str | None = None,
    ):
        if mode == ExecutionMode.DOCKER:
            configured_image = (
                image_docker
                or os.environ.get("ENIGMA_PIPE_ENIGMA_SC_IMAGE")
                or DEFAULT_DOCKER_IMAGE
            )
        else:
            if image_sif or os.environ.get("ENIGMA_PIPE_ENIGMA_SC_IMAGE"):
                configured_image = image_sif or os.environ.get("ENIGMA_PIPE_ENIGMA_SC_IMAGE") or ""
            else:
                default_sif = (
                    DEFAULT_SIF_IMAGE
                    if DEFAULT_SIF_IMAGE.is_file() or not LEGACY_SIF_IMAGE.is_file()
                    else LEGACY_SIF_IMAGE
                )
                configured_image = str(default_sif)
            configured_image = os.path.expandvars(os.path.expanduser(configured_image))

            if "://" not in configured_image:
                image_path = Path(configured_image)
                if not image_path.is_file():
                    raise MissingDependencyError(
                        f"ENIGMA-SC Singularity/Apptainer image not found at {image_path}. "
                        "Provide a valid .sif image via --image-sif or set ENIGMA_PIPE_ENIGMA_SC_IMAGE."
                    )
                configured_image = str(image_path.resolve())

        super().__init__(mode, configured_image)

    def _entrypoint(self) -> list[str]:
        """Docker entrypoint is preset in image; Singularity/Apptainer requires explicit script."""
        if self.mode == ExecutionMode.DOCKER:
            return []
        return list(ENIGMA_SC_ENTRYPOINT)

    def build_case_command(
        self,
        case_id: str,
        input_dir: Path,
        output_dir: Path,
        device: str = "cpu",
    ) -> list[str]:
        """Build container command for running a single case."""
        case_out = output_dir / case_id

        binds = [
            (input_dir.resolve(), Path("/input_data")),
            (case_out.resolve(), Path("/output_data")),
        ]

        container_opts: list[str] = []
        if device.lower() in ("gpu", "cuda"):
            if self.mode == ExecutionMode.DOCKER:
                container_opts.extend(["--gpus", "all"])
            elif self.mode in (ExecutionMode.SINGULARITY, ExecutionMode.APPTAINER):
                container_opts.append("--nv")

        args = self._entrypoint() + [
            "--input-dir",
            "/input_data",
            "--output-dir",
            "/output_data",
            "--subject",
            case_id,
        ]

        return self.build_command(binds, args, container_opts=container_opts)

    def run_case(
        self,
        case_id: str,
        input_nifti_path: Path,
        output_dir: Path,
        device: str = "cpu",
        replace_output: bool = False,
    ) -> int:
        """
        Run ENIGMA-SC on a single case.
        Creates an isolated staging input directory containing only the target NIfTI file,
        points container output to <output_dir>/<case_id>, and invokes the container.
        """
        case_out = output_dir / case_id
        if replace_output and case_out.exists():
            shutil.rmtree(case_out)
        case_out.mkdir(parents=True, exist_ok=True)

        # Create ephemeral staging input dir for this case to isolate inputs
        staging_dir = case_out / ".staging_input"
        staging_dir.mkdir(parents=True, exist_ok=True)

        try:
            staged_filename = f"{case_id}.nii.gz"
            if input_nifti_path.name.endswith(".nii"):
                staged_filename = f"{case_id}.nii"
            stage_case_input(input_nifti_path, staging_dir, staged_filename)

            binds = [
                (staging_dir.resolve(), Path("/input_data")),
                (case_out.resolve(), Path("/output_data")),
            ]

            container_opts: list[str] = []
            if device.lower() in ("gpu", "cuda"):
                if self.mode == ExecutionMode.DOCKER:
                    container_opts.extend(["--gpus", "all"])
                elif self.mode in (ExecutionMode.SINGULARITY, ExecutionMode.APPTAINER):
                    container_opts.append("--nv")

            args = self._entrypoint() + [
                "--input-dir",
                "/input_data",
                "--output-dir",
                "/output_data",
                "--subject",
                case_id,
            ]

            return self.run(binds, args, container_opts=container_opts)

        finally:
            # Clean up ephemeral staging directory
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
