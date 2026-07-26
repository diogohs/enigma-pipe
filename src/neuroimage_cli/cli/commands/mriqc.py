import typer
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timezone

from neuroimage_cli.core.config import load_settings
from neuroimage_cli.core.models import ProcessingMode, ExistingOutputPolicy, TerminalStatus, ExecutionMode
from neuroimage_cli.services.mriqc import MRIQCRunner
from neuroimage_cli.core.manifest import CompletionManifest, write_manifest
from neuroimage_cli.core.exceptions import MissingDependencyError
from neuroimage_cli.cli.main import state, app
from neuroimage_cli.cli.formatting import print_error, print_info, print_warning, print_json_summary

mriqc_app = typer.Typer(help="Automated Image Quality Assessment via MRIQC")
app.add_typer(mriqc_app, name="mriqc")

@mriqc_app.callback(invoke_without_command=True)
def mriqc_main(
    bids_dir: Path = typer.Argument(..., help="BIDS dataset directory", exists=True, file_okay=False, dir_okay=True),
    output_dir: Path = typer.Argument(..., help="Output directory", file_okay=False, dir_okay=True),
    work_dir: Path = typer.Argument(..., help="Work/scratch directory", file_okay=False, dir_okay=True),
    execution_mode: str = typer.Option("docker", "--execution-mode", help="docker or singularity"),
    participant_label: Optional[List[str]] = typer.Option(None, "--participant-label", help="List of participants to run"),
    n_procs: Optional[int] = typer.Option(None, "--nprocs", help="Number of processors to use")
):
    try:
        runner = MRIQCRunner(mode=ExecutionMode(execution_mode))
    except MissingDependencyError as e:
        print_error(str(e))
        raise typer.Exit(3)
        
    print_info(f"Starting MRIQC on {bids_dir}")
    
    # BIDS Validation (FR-019, FR-028)
    try:
        import bids
        # Validate BIDS dataset using BIDSLayout. It warns on issues.
        # We can capture warnings if we want, but BIDSLayout emits them by default.
        # Let's explicitly try to load with validate=True and catch exceptions or print warning.
        layout = bids.BIDSLayout(str(bids_dir), validate=True)
        print_info("BIDS validation passed (no critical errors).")
    except Exception as e:
        print_warning(f"BIDS validation found issues: {e}")
        print_warning("Continuing attempt despite BIDS validation warnings per FR-019.")
    started = datetime.now(timezone.utc)
    
    try:
        retcode = runner.run_bids_dataset(bids_dir, output_dir, work_dir, participant_label, n_procs)
        
        status = TerminalStatus.SUCCESS if retcode == 0 else TerminalStatus.FAILED
        
        # In a real app we'd parse the outputs and manifest per participant or batch
        # For brevity here, we create one manifest for the batch run
        manifest = CompletionManifest(
            status=status,
            case_id="mriqc_batch",
            subcommand="mriqc",
            started_at=started
        )
        write_manifest(output_dir, "mriqc_batch", "mriqc", manifest)
        
        exit_code = 0 if retcode == 0 else 4
        
        if state.json_output:
            print_json_summary("mriqc", 1, 1 if retcode == 0 else 0, 1 if retcode != 0 else 0, 0, exit_code, [])
            
        raise typer.Exit(exit_code)
        
    except KeyboardInterrupt:
        manifest = CompletionManifest(
            status=TerminalStatus.INTERRUPTED,
            case_id="mriqc_batch",
            subcommand="mriqc",
            started_at=started
        )
        write_manifest(output_dir, "mriqc_batch", "mriqc", manifest)
        if state.json_output:
            print_json_summary("mriqc", 1, 0, 0, 0, 130, [])
        raise typer.Exit(130)
