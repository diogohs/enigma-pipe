import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from enigma_pipe.core.manifest import BrainstemSegmentation


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


def compute_threads(threads_arg: str | None) -> int:
    if not threads_arg:
        return 1

    if threads_arg.lower() != "max":
        try:
            val = int(threads_arg)
            return max(1, val)
        except ValueError:
            return 1

    # Handle "max" logic
    cpu_count = None
    if hasattr(os, "sched_getaffinity"):
        try:
            cpu_count = len(os.sched_getaffinity(0))
        except Exception:
            pass

    if cpu_count is None:
        cpu_count = os.cpu_count()

    if not cpu_count:
        return 1

    return max(1, cpu_count // 2)


def run_brainstem_segmentation(
    output_dir: Path, case_id: str, threads_arg: str | None
) -> BrainstemSegmentation:
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
        "--threads",
        str(threads),
    ]

    # Print to stderr before execution
    sys.stderr.write(f"Executing: {' '.join(cmd)}\n")

    # Execute
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = str(threads)
    env["ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"] = str(threads)

    try:
        result = subprocess.run(cmd, env=env, check=False)
        end_time = datetime.now(timezone.utc)

        if result.returncode == 0:
            return BrainstemSegmentation(
                status="SUCCESS",
                exit_code=0,
                started_at=start_time,
                finished_at=end_time,
                threads_used=threads,
            )
        else:
            return BrainstemSegmentation(
                status="FAILED",
                exit_code=result.returncode,
                started_at=start_time,
                finished_at=end_time,
                threads_used=threads,
                error_message=f"Process exited with code {result.returncode}",
            )
    except KeyboardInterrupt:
        return BrainstemSegmentation(
            status="INTERRUPTED",
            exit_code=None,
            started_at=start_time,
            finished_at=None,
            threads_used=threads,
            error_message="KeyboardInterrupt",
        )
    except Exception as e:
        end_time = datetime.now(timezone.utc)
        return BrainstemSegmentation(
            status="FAILED",
            exit_code=1,
            started_at=start_time,
            finished_at=end_time,
            threads_used=threads,
            error_message=str(e),
        )
