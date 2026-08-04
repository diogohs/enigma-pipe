import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from enigma_pipe.core.models import CaseOutcome, TerminalStatus
from enigma_pipe.core.validation import validate_threads


def validate_fastsurfer_output(case_dir: Path) -> None:
    """Validates that a directory is a valid FastSurfer output structure."""
    mri_dir = case_dir / "mri"
    missing = []
    if not (mri_dir / "norm.mgz").exists():
        missing.append("mri/norm.mgz")
    if not (mri_dir / "nu.mgz").exists():
        missing.append("mri/nu.mgz")
    if not ((mri_dir / "aseg.mgz").exists() or (mri_dir / "aseg.presurf.mgz").exists()):
        missing.append("mri/aseg.mgz or mri/aseg.presurf.mgz")

    if missing:
        raise ValueError(
            f"Invalid FastSurfer output directory '{case_dir}'. Missing required files: {', '.join(missing)}"
        )





class FreeSurferChecker:
    @staticmethod
    def check_availability() -> None:
        cmd_path = shutil.which("segment_subregions")
        if not cmd_path:
            sys.stderr.write(
                "ERROR: segment_subregions not found on PATH. FreeSurfer must be installed.\n"
            )
            sys.exit(3)

        if not os.path.exists(cmd_path) or not os.access(cmd_path, os.X_OK):
            sys.stderr.write(
                f"ERROR: segment_subregions found at {cmd_path} but is not executable.\n"
            )
            sys.exit(3)

        # Check FreeSurfer version
        version_str = None
        fs_home = os.environ.get("FREESURFER_HOME")
        if fs_home:
            stamp_file = os.path.join(fs_home, "build-stamp.txt")
            if os.path.exists(stamp_file):
                try:
                    with open(stamp_file, "r") as f:
                        version_str = f.read().strip()
                except Exception:
                    pass

        if not version_str:
            try:
                result = subprocess.run(
                    ["recon-all", "--version"], capture_output=True, text=True, check=False
                )
                if result.returncode == 0:
                    version_str = result.stdout.strip()
            except Exception:
                pass

        if version_str:
            match = re.search(
                r"freesurfer-[a-zA-Z0-9_]+-[a-zA-Z0-9_]+-7\.([0-2])(?:\.|$)", version_str
            )
            if match:
                sys.stderr.write(
                    f"WARNING: FreeSurfer version {version_str} detected. Minimum supported version is 7.3.\n"
                )



def compute_threads(threads_arg: int | str | None) -> int:
    validated = validate_threads(threads_arg)
    if validated == "max":
        if hasattr(os, "sched_getaffinity"):
            try:
                cpus = len(os.sched_getaffinity(0))
                return max(1, cpus // 2)
            except Exception:
                pass
        cpus = os.cpu_count() or 1
        return max(1, cpus // 2)
    return int(validated)


def run_brainstem_segmentation(
    output_dir: Path, case_id: str, threads_arg: int | str | None
) -> CaseOutcome:
    start_time = datetime.now(timezone.utc)
    threads = compute_threads(threads_arg)

    # Base command
    cmd = [
        "segment_subregions",
        "brainstem",
        "--cross",
        case_id,
        "--sd",
        str(output_dir),
    ]
    cmd.extend(["--threads", str(threads)])

    # Print to stderr before execution
    sys.stderr.write(f"Executing: {' '.join(cmd)}\n")

    # Execute
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = str(threads)
    env["ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"] = str(threads)

    try:
        result = subprocess.run(cmd, env=env, check=False)

        if result.returncode == 0:
            return CaseOutcome(
                case_id=case_id,
                status=TerminalStatus.SUCCESS,
            )
        else:
            return CaseOutcome(
                case_id=case_id,
                status=TerminalStatus.FAILED,
                error_message=f"Process exited with code {result.returncode}",
            )
    except KeyboardInterrupt:
        return CaseOutcome(
            case_id=case_id,
            status=TerminalStatus.INTERRUPTED,
            error_message="KeyboardInterrupt",
        )
    except Exception as e:
        return CaseOutcome(
            case_id=case_id,
            status=TerminalStatus.FAILED,
            error_message=str(e),
        )
