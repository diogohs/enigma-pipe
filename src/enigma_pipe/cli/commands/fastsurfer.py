from datetime import datetime, timezone
from pathlib import Path

import typer

from enigma_pipe.cli.formatting import print_error, print_info, print_json_summary, print_warning, setup_logging
from enigma_pipe.cli.main import app, state
from enigma_pipe.core.config import load_settings
from enigma_pipe.core.exceptions import MissingDependencyError
from enigma_pipe.core.manifest import CompletionManifest, write_manifest
from enigma_pipe.core.models import (
    ExecutionMode,
    ExistingOutputPolicy,
    ProcessingMode,
    TerminalStatus,
)
from enigma_pipe.services.brainstem_seg import FreeSurferChecker, run_brainstem_segmentation
from enigma_pipe.services.case_discovery import discover_cases
from enigma_pipe.services.fastsurfer import FastSurferRunner
from enigma_pipe.services.version_checker import VersionCheckResult, check_fastsurfer_version


@app.command(name="fastsurfer", help="Structural processing via FastSurfer")
def fastsurfer_main(
    input_dir: Path = typer.Argument(
        ..., help="Directory containing T1w images", exists=True, file_okay=False, dir_okay=True
    ),
    output_dir: Path = typer.Argument(..., help="Output directory", file_okay=False, dir_okay=True),
    fs_license: Path | None = typer.Option(None, "--fs-license", help="Path to FreeSurfer license"),
    execution_mode: str = typer.Option(
        "docker", "--execution-mode", help="Container runtime to use (docker, singularity, or apptainer)"
    ),
    processing_mode: ProcessingMode = typer.Option(
        ProcessingMode.ALL, "--processing-mode", help="Case selection mode ('all' for entire directory, 'continue' to resume incomplete runs, 'file' for explicit lists)"
    ),
    existing_output: ExistingOutputPolicy = typer.Option(
        ExistingOutputPolicy.ERROR, "--existing-output", help="Action when output exists: 'error' (abort), 'skip' (ignore), 'resume' (continue partial), 'replace' (overwrite)"
    ),
    device: str = typer.Option(
        "cpu", "--device", help="Compute device for neural network inference ('cpu', 'gpu', or 'cuda')"
    ),
    threads: str | None = typer.Option(None, "--threads", help="Thread count or 'max'"),
    # backend: str = typer.Option("local", "--backend", help="Execution backend (local or hpc)"),
    no_asegdkt: bool = typer.Option(False, "--no-asegdkt", help="Skip asegdkt (whole brain segmentation) segmentation"),
    no_cc: bool = typer.Option(False, "--no-cc", help="Skip corpus callosum segmentation"),
    no_cereb: bool = typer.Option(False, "--no-cereb", help="Skip cerebellum segmentation"),
    no_hypothal: bool = typer.Option(True, "--no-hypothal", help="Skip hypothalamus segmentation"),
    skip_version_check: bool = typer.Option(
        False, "--skip-version-check", help="Bypass FastSurfer version check"
    ),
):
    setup_logging(output_dir)
    settings = load_settings(state.settings_path)
    license_path = fs_license or settings.fs_license

    if not license_path or not license_path.exists():
        print_error("FreeSurfer license is required. Provide via --fs-license or settings.")
        raise typer.Exit(3)

    # if backend.lower() == "hpc":
    #     print_error("HPC scheduler submission is not yet implemented.")
    #     raise typer.Exit(3)

    # Phase 2: Host dependencies (Brainstem segmentation)
    FreeSurferChecker.check_availability()

    try:
        runner = FastSurferRunner(mode=ExecutionMode(execution_mode))
        if not skip_version_check:
            raw_version = runner.check_version()
            res, ver = check_fastsurfer_version(raw_version)
            if res == VersionCheckResult.UNSUPPORTED:
                print_warning(
                    f"FastSurfer version {ver} is below the minimum supported version (2.4.0)"
                )
            elif res == VersionCheckResult.UNPARSEABLE:
                print_warning("FastSurfer version could not be verified")
    except MissingDependencyError as e:
        print_error(str(e))
        raise typer.Exit(3)

    try:
        cases = discover_cases(
            input_dir, output_dir, "fastsurfer", processing_mode, existing_output
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
            started = datetime.now(timezone.utc)
            retcode = runner.run_case(
                case_id=case.id,
                input_path=case.original_path,
                output_dir=output_dir,
                fs_license=license_path,
                device=device,
                threads=threads,
                no_asegdkt=no_asegdkt,
                no_cc=no_cc,
                no_cereb=no_cereb,
                no_hypothal=no_hypothal,
            )

            brainstem_result = None
            if retcode == 0:
                succeeded += 1
                status = TerminalStatus.SUCCESS
                brainstem_result = run_brainstem_segmentation(
                    output_dir, case.id, str(threads) if threads else None
                )

                # Handle brainstem segmentation outcome
                if brainstem_result.status == "INTERRUPTED":
                    # Write manifest with INTERRUPTED status and exit immediately
                    manifest = CompletionManifest(
                        status=TerminalStatus.INTERRUPTED,
                        case_id=case.id,
                        subcommand="fastsurfer",
                        started_at=started,
                        outputs=[str(output_dir / case.id)],
                        brainstem_segmentation=brainstem_result,
                    )
                    write_manifest(output_dir, case.id, "fastsurfer", manifest)
                    results.append({"case_id": case.id, "status": TerminalStatus.INTERRUPTED.value})
                    if state.json_output:
                        print_json_summary(
                            "fastsurfer", total, succeeded, failed, skipped, 130, results
                        )
                    raise typer.Exit(130)
                elif brainstem_result.status == "FAILED":
                    # Demote success to failure — brainstem seg failed
                    succeeded -= 1
                    failed += 1
                    status = TerminalStatus.FAILED
            else:
                failed += 1
                status = TerminalStatus.FAILED

            manifest = CompletionManifest(
                status=status,
                case_id=case.id,
                subcommand="fastsurfer",
                started_at=started,
                outputs=[str(output_dir / case.id)],
                brainstem_segmentation=brainstem_result,
            )
            write_manifest(output_dir, case.id, "fastsurfer", manifest)
            results.append({"case_id": case.id, "status": status.value})

        except KeyboardInterrupt:
            # Handle Ctrl+C
            manifest = CompletionManifest(
                status=TerminalStatus.INTERRUPTED,
                case_id=case.id,
                subcommand="fastsurfer",
                started_at=started,
            )
            write_manifest(output_dir, case.id, "fastsurfer", manifest)
            results.append({"case_id": case.id, "status": TerminalStatus.INTERRUPTED.value})
            if state.json_output:
                print_json_summary("fastsurfer", total, succeeded, failed, skipped, 130, results)
            raise typer.Exit(130)

    exit_code = 0
    if failed > 0:
        exit_code = 4

    if state.json_output:
        print_json_summary("fastsurfer", total, succeeded, failed, skipped, exit_code, results)

    raise typer.Exit(exit_code)
