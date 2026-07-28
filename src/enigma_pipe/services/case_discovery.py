import os
from pathlib import Path

from enigma_pipe.core.exceptions import InvalidSettingsError
from enigma_pipe.core.manifest import read_manifest
from enigma_pipe.core.models import CaseIdentifier, ExistingOutputPolicy, ProcessingMode
from enigma_pipe.services.case_identifier import derive_case_id


class DiscoveryResult(list):
    def __init__(self, cases: list, total_found: int = 0, skipped_count: int = 0):
        super().__init__(cases)
        self.total_found = total_found
        self.skipped_count = skipped_count


def is_hidden(path: Path) -> bool:
    return path.name.startswith(".")


def discover_cases(
    input_dir: Path,
    output_dir: Path,
    subcommand: str,
    processing_mode: ProcessingMode,
    existing_output: ExistingOutputPolicy,
    extensions: tuple = (".nii.gz", ".nii", ".mgz"),
    prune_fastsurfer: bool = True,
) -> DiscoveryResult:
    """
    Traverse input_dir deterministically and yield eligible cases.
    Applies existing_output and processing_mode policies.
    """
    cases = []
    seen_ids: set[str] = set()
    total_found = 0
    skipped_count = 0

    # Deterministic traversal
    for root, dirs, files in os.walk(input_dir, followlinks=False):
        root_path = Path(root)

        # Prune hidden dirs
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        dirs.sort()

        # Stop traversing into FastSurfer output directories (heuristic: presence of 'mri' dir)
        if prune_fastsurfer and "mri" in dirs and "scripts" in dirs:
            dirs[:] = []
            continue

        for file in sorted(files):
            if file.startswith("."):
                continue

            if file.endswith(extensions):
                file_path = root_path / file
                case_id = derive_case_id(file_path)

                # Output collision detection
                if case_id in seen_ids:
                    raise InvalidSettingsError(
                        f"Output collision detected for case_id '{case_id}'."
                    )

                total_found += 1

                # Check existing manifest
                manifest = read_manifest(output_dir, case_id, subcommand)
                is_completed = manifest is not None and manifest.status == "success"

                if processing_mode == ProcessingMode.CONTINUE and is_completed:
                    skipped_count += 1
                    continue

                if is_completed and existing_output == ExistingOutputPolicy.SKIP:
                    skipped_count += 1
                    continue

                if is_completed and existing_output == ExistingOutputPolicy.ERROR:
                    raise InvalidSettingsError(
                        f"Case {case_id} already has completed output and policy is 'error'."
                    )

                seen_ids.add(case_id)
                cases.append(CaseIdentifier(id=case_id, original_path=file_path))

    return DiscoveryResult(cases, total_found=total_found, skipped_count=skipped_count)
