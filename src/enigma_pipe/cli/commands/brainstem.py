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
from enigma_pipe.services.case_discovery import discover_cases


@app.command(name="brainstem", help="Run standalone brainstem subsegmentation on FastSurfer output")
def brainstem_main(
    input_dir: Path = typer.Argument(
        ..., help="Directory containing FastSurfer outputs", exists=True, file_okay=False, dir_okay=True
    ),
    output_dir: Path = typer.Argument(..., help="Output directory", file_okay=False, dir_okay=True),
    processing_mode: ProcessingMode = typer.Option(
        ProcessingMode.ALL, "--processing-mode", help="Case selection mode ('all' for entire directory, 'continue' to resume incomplete runs, 'file' for explicit lists)"
    ),
    existing_output: ExistingOutputPolicy = typer.Option(
        ExistingOutputPolicy.ERROR, "--existing-output", help="Action when output exists: 'error' (abort), 'skip' (ignore), 'resume' (continue partial), 'replace' (overwrite)"
    ),
    threads: int | None = typer.Option(None, "--threads", help="Thread count"),
):
    FreeSurferChecker.check_availability()

    try:
        cases = discover_cases(
            input_dir, output_dir, "brainstem", processing_mode, existing_output
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
        try:
            # We must validate that the case output dir is a valid FastSurfer output
            # (which is what brainstem requires as input)
            validate_fastsurfer_output(output_dir / case.id)
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
            write_manifest(output_dir, case.id, "brainstem", manifest)
            continue

        started = datetime.now(timezone.utc)
        print_info(f"Running brainstem subsegmentation for {case.id}")
        
        result = run_brainstem_segmentation(output_dir, case.id, threads)

        if result.status == TerminalStatus.INTERRUPTED:
            print_error("Brainstem subsegmentation interrupted.")
            manifest = CompletionManifest(
                status=TerminalStatus.INTERRUPTED,
                case_id=case.id,
                subcommand="brainstem",
                started_at=started,
            )
            write_manifest(output_dir, case.id, "brainstem", manifest)
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
            outputs=[str(output_dir / case.id / "mri" / "brainstemSsLabels.v13.FSvoxelSpace.mgz")] if result.status == TerminalStatus.SUCCESS else [],
        )
        write_manifest(output_dir, case.id, "brainstem", manifest)
        results.append({"case_id": case.id, "status": result.status.value})

    exit_code = 0
    if failed > 0:
        exit_code = 4

    if state.json_output:
        print_json_summary("brainstem", total, succeeded, failed, skipped, exit_code, results)

    raise typer.Exit(exit_code)
