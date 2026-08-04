from datetime import datetime, timezone
from pathlib import Path

import typer

from enigma_pipe.cli.formatting import print_error, print_info, print_json_summary
from enigma_pipe.cli.main import app, state
from enigma_pipe.core.manifest import CompletionManifest, write_manifest
from enigma_pipe.core.models import (
    ExistingOutputPolicy,
    ProcessingMode,
    TerminalStatus,
)
from enigma_pipe.services.brainstem_seg import (
    FreeSurferChecker,
    run_brainstem_segmentation,
    validate_fastsurfer_output,
)
from enigma_pipe.core.exceptions import InvalidSettingsError
from enigma_pipe.core.manifest import read_manifest
from enigma_pipe.core.validation import validate_threads

class DiscoveryResult(list):
    def __init__(self, cases, total_found=0, skipped_count=0):
        super().__init__(cases)
        self.total_found = total_found
        self.skipped_count = skipped_count

def discover_fs_cases(
    input_dir: Path, processing_mode: ProcessingMode, existing_output: ExistingOutputPolicy
) -> DiscoveryResult:
    from enigma_pipe.core.models import CaseIdentifier

    cases = []
    total_found = 0
    skipped_count = 0

    candidates = []
    
    # Check if input_dir itself is a valid case
    try:
        validate_fastsurfer_output(input_dir)
        candidates.append(input_dir)
    except ValueError:
        pass
        
    if not candidates and input_dir.is_dir():
        # Check subdirectories
        for child in sorted(input_dir.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                try:
                    validate_fastsurfer_output(child)
                    candidates.append(child)
                except ValueError:
                    pass

    if not candidates:
        # Found nothing
        return DiscoveryResult([], total_found=0, skipped_count=0)
        
    for candidate in candidates:
        case_id = candidate.name
        output_dir = candidate.parent
        total_found += 1
        
        manifest = read_manifest(output_dir, case_id, "brainstem")
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
            
        cases.append(CaseIdentifier(id=case_id, original_path=candidate))

    return DiscoveryResult(cases, total_found=total_found, skipped_count=skipped_count)


@app.command(name="brainstem", help="Run standalone brainstem subsegmentation on FastSurfer output")
def brainstem_main(
    input_dir: Path = typer.Argument(
        ..., help="Directory containing FastSurfer outputs", exists=True, file_okay=False, dir_okay=True
    ),
    processing_mode: ProcessingMode = typer.Option(
        ProcessingMode.ALL, "--processing-mode", help="Case selection mode ('all' for entire directory, 'continue' to resume incomplete runs, 'file' for explicit lists)"
    ),
    existing_output: ExistingOutputPolicy = typer.Option(
        ExistingOutputPolicy.ERROR, "--existing-output", help="Action when output exists: 'error' (abort), 'skip' (ignore), 'resume' (continue partial), 'replace' (overwrite)"
    ),
    threads: str | None = typer.Option(None, "--threads", help="Thread count or 'max'"),
):
    try:
        threads = validate_threads(threads)
    except InvalidSettingsError as e:
        print_error(str(e))
        raise typer.Exit(2)

    FreeSurferChecker.check_availability()

    try:
        cases = discover_fs_cases(
            input_dir, processing_mode, existing_output
        )
    except Exception as e:
        print_error(f"Validation error: {e}")
        raise typer.Exit(2)

    total = len(cases)
    total_to_process = len(cases)
    total_found = getattr(cases, "total_found", total_to_process)
    skipped_count = getattr(cases, "skipped_count", 0)

    succeeded = 0
    failed = 0
    skipped = skipped_count
    results = []

    case_word_found = "case" if total_found == 1 else "cases"
    case_word_process = "case" if total_to_process == 1 else "cases"

    if total_found > 0 and total_to_process == 0:
        print_info(
            f"Discovered {total_found} {case_word_found}, but all {skipped_count} {case_word_found} are already completed and skipped according to policy."
        )
    elif skipped_count > 0:
        print_info(
            f"Discovered {total_found} {case_word_found}: {total_to_process} {case_word_process} to process ({skipped_count} already completed and skipped)."
        )
    else:
        print_info(f"Discovered {total_to_process} {case_word_process} to process.")

    for case in cases:
        # The output_dir for this case is its parent directory
        case_output_dir = case.original_path.parent
        
        try:
            validate_fastsurfer_output(case.original_path)
        except ValueError as e:
            print_error(str(e))
            failed += 1
            results.append({"case_id": case.id, "status": TerminalStatus.FAILED.value})
            manifest = CompletionManifest(
                status=TerminalStatus.FAILED,
                case_id=case.id,
                subcommand="brainstem",
                started_at=datetime.now(timezone.utc),
                error_message=str(e),
            )
            write_manifest(case_output_dir, case.id, "brainstem", manifest)
            continue

        started = datetime.now(timezone.utc)
        print_info(f"Running brainstem subsegmentation for {case.id}")
        
        result = run_brainstem_segmentation(case_output_dir, case.id, threads)

        if result.status == TerminalStatus.INTERRUPTED:
            print_error("Brainstem subsegmentation interrupted.")
            manifest = CompletionManifest(
                status=TerminalStatus.INTERRUPTED,
                case_id=case.id,
                subcommand="brainstem",
                started_at=started,
            )
            write_manifest(case_output_dir, case.id, "brainstem", manifest)
            results.append({"case_id": case.id, "status": TerminalStatus.INTERRUPTED.value})
            if state.json_output:
                print_json_summary(
                    "brainstem", total, succeeded, failed, skipped, 130, results
                )
            raise typer.Exit(130)
        elif result.status == TerminalStatus.FAILED:
            failed += 1
            print_error(f"Brainstem subsegmentation failed for {case.id}: {result.error_message}")
        else:
            succeeded += 1

        manifest = CompletionManifest(
            status=result.status,
            case_id=case.id,
            subcommand="brainstem",
            started_at=started,
            error_message=result.error_message,
            outputs=[str(case.original_path / "mri" / "brainstemSsLabels.v13.FSvoxelSpace.mgz")] if result.status == TerminalStatus.SUCCESS else [],
        )
        write_manifest(case_output_dir, case.id, "brainstem", manifest)
        results.append({"case_id": case.id, "status": result.status.value})

    exit_code = 0
    if failed > 0:
        exit_code = 4

    if state.json_output:
        print_json_summary("brainstem", total, succeeded, failed, skipped, exit_code, results)

    raise typer.Exit(exit_code)
