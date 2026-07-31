from datetime import datetime, timezone
from pathlib import Path

import typer

from enigma_pipe.cli.formatting import (
    print_error,
    print_info,
    print_json_summary,
    print_warning,
    setup_logging,
)
from enigma_pipe.cli.main import app, state
from enigma_pipe.core.exceptions import MissingDependencyError
from enigma_pipe.core.manifest import CompletionManifest, write_manifest
from enigma_pipe.core.models import (
    ExecutionMode,
    TerminalStatus,
)
from enigma_pipe.services.mriqc import MRIQCRunner


@app.command(name="mriqc", help="Automated Image Quality Assessment via MRIQC")
def mriqc_main(
    input_dir: Path = typer.Argument(
        ..., help="Input dir in BIDS dataset format.", exists=True, file_okay=False, dir_okay=True
    ),
    output_dir: Path = typer.Argument(..., help="Output directory.", file_okay=False, dir_okay=True),
    work_dir: Path | None = typer.Argument(
        None, help="Work/scratch directory (optional).", file_okay=False, dir_okay=True
    ),
    execution_mode: str = typer.Option("docker", "--execution-mode", help="docker, apptainer or singularity."),
    participant_label: list[str] | None = typer.Option(
        None, "--participant-label", help="List of participants to run (optional)."
    ),
    n_procs: int | None = typer.Option(None, "--nprocs", help="Number of processors to use (optional)."),
):
    setup_logging(output_dir)
    try:
        runner = MRIQCRunner(mode=ExecutionMode(execution_mode))
    except MissingDependencyError as e:
        print_error(str(e))
        raise typer.Exit(3)

    print_info(f"Starting MRIQC on {input_dir}")

    # BIDS Validation (FR-019, FR-028)
    try:
        import bids

        # Validate BIDS dataset using BIDSLayout. It warns on issues.
        # We can capture warnings if we want, but BIDSLayout emits them by default.
        # Let's explicitly try to load with validate=True and catch exceptions or print warning.
        layout = bids.BIDSLayout(str(input_dir), validate=True)
        print_info("BIDS validation passed (no critical errors).")
    except Exception as e:
        print_warning(f"BIDS validation found issues: {e}")
        # print_warning("Continuing attempt despite BIDS validation warnings per FR-019.")
    started = datetime.now(timezone.utc)

    try:
        retcode = runner.run_bids_dataset(
            input_dir, output_dir, work_dir, participant_label, n_procs
        )

        status = TerminalStatus.SUCCESS if retcode == 0 else TerminalStatus.FAILED

        # In a real app we'd parse the outputs and manifest per participant or batch
        # For brevity here, we create one manifest for the batch run
        manifest = CompletionManifest(
            status=status, case_id="mriqc_batch", subcommand="mriqc", started_at=started
        )
        write_manifest(output_dir, "mriqc_batch", "mriqc", manifest)

        exit_code = 0 if retcode == 0 else 4

        if state.json_output:
            print_json_summary(
                "mriqc", 1, 1 if retcode == 0 else 0, 1 if retcode != 0 else 0, 0, exit_code, []
            )

        raise typer.Exit(exit_code)

    except KeyboardInterrupt:
        manifest = CompletionManifest(
            status=TerminalStatus.INTERRUPTED,
            case_id="mriqc_batch",
            subcommand="mriqc",
            started_at=started,
        )
        write_manifest(output_dir, "mriqc_batch", "mriqc", manifest)
        if state.json_output:
            print_json_summary("mriqc", 1, 0, 0, 0, 130, [])
        raise typer.Exit(130)
