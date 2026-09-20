from datetime import datetime, timezone
from pathlib import Path

import typer

from enigma_pipe.cli.formatting import (
    print_error,
    print_info,
    print_json_summary,
    setup_logging,
)
from enigma_pipe.cli.main import app, state
from enigma_pipe.core.exceptions import InvalidSettingsError, MissingDependencyError
from enigma_pipe.core.manifest import CompletionManifest, read_manifest, write_manifest
from enigma_pipe.core.models import (
    ExecutionMode,
    ExistingOutputPolicy,
    ProcessingMode,
    TerminalStatus,
)
from enigma_pipe.services.case_discovery import discover_cases
from enigma_pipe.services.enigma_sc import (
    EnigmaSCRunner,
    check_gpu_availability,
    consolidate_group_tables,
    discover_bids_cases,
    is_bids_dataset,
    verify_case_outputs,
)


@app.command(name="enigma-sc", help="Automated spinal cord processing via ENIGMA-SC")
def enigma_sc_main(
    input_dir: Path = typer.Argument(
        ...,
        help="Input directory containing NIfTI images or BIDS dataset",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
    output_dir: Path = typer.Argument(
        ...,
        help="Output directory for subject outputs, manifests, and group metrics",
        file_okay=False,
        dir_okay=True,
    ),
    execution_mode: str = typer.Option(
        "docker",
        "--execution-mode",
        help="Container runtime to use (docker, singularity, or apptainer)",
    ),
    device: str = typer.Option(
        "cpu",
        "--device",
        help="Compute device ('cpu', 'gpu', or 'cuda')",
    ),
    image_sif: str | None = typer.Option(
        None,
        "--image-sif",
        help="Path to custom Singularity/Apptainer .sif container image (default: ~/enigma-pipe/images/pipeline_enigma_cli.sif)",
    ),
    image_docker: str | None = typer.Option(
        None,
        "--image-docker",
        help="Docker image name or tag (default: art2mri/pipeline_enigma_cli:1.0)",
    ),
    processing_mode: ProcessingMode = typer.Option(
        ProcessingMode.ALL,
        "--processing-mode",
        help="Case selection mode ('all' for entire directory, 'continue' to resume incomplete runs)",
    ),
    existing_output: ExistingOutputPolicy = typer.Option(
        ExistingOutputPolicy.ERROR,
        "--existing-output",
        help="Action when output exists: 'error' (abort), 'skip' (ignore), 'replace' (overwrite), 'resume' (re-run incomplete/failed)",
    ),
) -> None:
    """
    Execute ENIGMA Spinal Cord pipeline analysis on NIfTI images or BIDS datasets.
    """
    setup_logging(output_dir)

    # 1. Validate device requirements
    if device.lower() not in ("cpu", "gpu", "cuda"):
        print_error(f"Invalid device: '{device}'. Must be 'cpu', 'gpu', or 'cuda'.")
        raise typer.Exit(2)

    if device.lower() in ("gpu", "cuda") and not check_gpu_availability():
        print_error(
            "GPU acceleration requested (--device gpu), but nvidia-smi / NVIDIA GPU is not available on host."
        )
        raise typer.Exit(3)

    # 2. Initialize container runner
    try:
        mode_enum = ExecutionMode(execution_mode.lower())
    except ValueError:
        print_error(
            f"Invalid execution mode: '{execution_mode}'. Must be 'docker', 'singularity', or 'apptainer'."
        )
        raise typer.Exit(2)

    try:
        runner = EnigmaSCRunner(
            mode=mode_enum,
            image_sif=image_sif,
            image_docker=image_docker,
        )
    except MissingDependencyError as e:
        print_error(str(e))
        raise typer.Exit(3)

    # 3. Discover cases (BIDS or loose NIfTI discovery)
    try:
        if is_bids_dataset(input_dir):
            print_info("BIDS dataset detected.")
            cases = discover_bids_cases(
                input_dir=input_dir,
                output_dir=output_dir,
                subcommand="enigma-sc",
                processing_mode=processing_mode,
                existing_output=existing_output,
            )
        else:
            cases = discover_cases(
                input_dir=input_dir,
                output_dir=output_dir,
                subcommand="enigma-sc",
                processing_mode=processing_mode,
                existing_output=existing_output,
                extensions=(".nii.gz", ".nii"),
            )
    except InvalidSettingsError as e:
        print_error(str(e))
        raise typer.Exit(2)
    except Exception as e:  # noqa: BLE001
        print_error(f"Validation error: {e}")
        raise typer.Exit(2)

    total_to_process = len(cases)
    total_found = getattr(cases, "total_found", total_to_process)
    skipped_count = getattr(cases, "skipped_count", 0)
    total = total_found

    succeeded = 0
    failed = 0
    skipped = skipped_count
    results: list[dict[str, str]] = []
    succeeded_cases: list[str] = []

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

    # 4. Batch execution loop
    for case in cases:
        started = datetime.now(timezone.utc)
        try:
            retcode = runner.run_case(
                case_id=case.id,
                input_nifti_path=case.original_path,
                output_dir=output_dir,
                device=device,
            )

            error_msg: str | None = None
            if retcode == 0:
                valid, verify_err = verify_case_outputs(output_dir, case.id)
                if valid:
                    status = TerminalStatus.SUCCESS
                    succeeded += 1
                    succeeded_cases.append(case.id)
                else:
                    status = TerminalStatus.FAILED
                    failed += 1
                    error_msg = verify_err
            else:
                status = TerminalStatus.FAILED
                failed += 1
                error_msg = f"Container execution failed with return code {retcode}"

            manifest = CompletionManifest(
                status=status,
                case_id=case.id,
                subcommand="enigma-sc",
                started_at=started,
                error_message=error_msg,
                outputs=[str(output_dir / case.id)] if status == TerminalStatus.SUCCESS else [],
            )
            write_manifest(output_dir, case.id, "enigma-sc", manifest)
            results.append({"case_id": case.id, "status": status.value})

        except KeyboardInterrupt:
            manifest = CompletionManifest(
                status=TerminalStatus.INTERRUPTED,
                case_id=case.id,
                subcommand="enigma-sc",
                started_at=started,
                error_message="Execution interrupted by user",
            )
            write_manifest(output_dir, case.id, "enigma-sc", manifest)
            results.append({"case_id": case.id, "status": TerminalStatus.INTERRUPTED.value})
            if state.json_output:
                print_json_summary("enigma-sc", total, succeeded, failed, skipped, 130, results)
            raise typer.Exit(130)

    # 5. Consolidate group tables for all successful cases in output directory
    all_successful_cases = set(succeeded_cases)
    if output_dir.exists():
        for case_dir in output_dir.iterdir():
            if case_dir.is_dir() and not case_dir.name.startswith("."):
                m = read_manifest(output_dir, case_dir.name, "enigma-sc")
                if m and m.status == TerminalStatus.SUCCESS:
                    all_successful_cases.add(case_dir.name)

    consolidate_group_tables(output_dir, sorted(all_successful_cases))

    # 6. Exit code & JSON summary handling
    exit_code = 0
    if failed > 0:
        exit_code = 4

    if state.json_output:
        print_json_summary("enigma-sc", total, succeeded, failed, skipped, exit_code, results)

    raise typer.Exit(exit_code)
