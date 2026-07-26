import typer
from pathlib import Path
from typing import Optional
from rich.prompt import Prompt, IntPrompt
from datetime import datetime, timezone

from neuroimage_cli.core.config import load_settings
from neuroimage_cli.core.models import ProcessingMode, ExistingOutputPolicy, TerminalStatus
from neuroimage_cli.services.case_discovery import discover_cases
from neuroimage_cli.services.itksnap import ITKSnapLauncher
from neuroimage_cli.services.qc_image import write_image_qc_csv
from neuroimage_cli.core.manifest import CompletionManifest, write_manifest
from neuroimage_cli.cli.main import state, app
from neuroimage_cli.cli.formatting import print_error, print_info, print_warning, print_json_summary

qc_img_app = typer.Typer(help="Interactive Image QC via ITK-SNAP")
app.add_typer(qc_img_app, name="qc-img")

@qc_img_app.callback(invoke_without_command=True)
def qc_img_main(
    input_dir: Path = typer.Argument(..., help="Directory containing T1w images", exists=True, file_okay=False, dir_okay=True),
    output_dir: Path = typer.Argument(..., help="Output directory", file_okay=False, dir_okay=True),
    processing_mode: ProcessingMode = typer.Option(ProcessingMode.ALL, "--processing-mode", help="Case selection mode"),
    existing_output: ExistingOutputPolicy = typer.Option(ExistingOutputPolicy.SKIP, "--existing-output", help="Existing output policy"),
    reviewer_id: Optional[str] = typer.Option(None, "--reviewer-id", help="Reviewer ID (defaults to OS user)")
):
    settings = load_settings(state.settings_path)
    
    # Precedence: CLI > YAML (default OS user is handled in config)
    actual_reviewer = reviewer_id if reviewer_id is not None else settings.reviewer_id
    
    try:
        cases = discover_cases(input_dir, output_dir, "qc-img", processing_mode, existing_output)
    except Exception as e:
        print_error(f"Validation error: {e}")
        raise typer.Exit(2)
        
    total = len(cases)
    if total == 0:
        print_info("No cases found to process.")
        raise typer.Exit(0)
        
    launcher = ITKSnapLauncher(settings.itksnap_path)
    succeeded = 0
    results = []
    
    print_info(f"Starting Image QC for {total} cases.")
    
    for idx, case in enumerate(cases):
        print_info(f"[{idx+1}/{total}] Case: {case.id}")
        started = datetime.now(timezone.utc)
        
        # Launch ITK-SNAP
        launcher.launch(case.original_path)
        
        # Prompt for rating
        rating = None
        while rating is None:
            try:
                val = IntPrompt.ask("Enter quality rating (0-5)", show_choices=False)
                if 0 <= val <= 5:
                    rating = val
                else:
                    print_error("Rating must be between 0 and 5.")
            except typer.Abort:
                # Handle Ctrl+C during prompt
                launcher.close()
                manifest = CompletionManifest(
                    status=TerminalStatus.INTERRUPTED,
                    case_id=case.id,
                    subcommand="qc-img",
                    started_at=started
                )
                write_manifest(output_dir, case.id, "qc-img", manifest)
                results.append({"case_id": case.id, "status": TerminalStatus.INTERRUPTED.value})
                if state.json_output:
                    print_json_summary("qc-img", total, succeeded, 0, total - succeeded - 1, 130, results)
                raise typer.Exit(130)
                
        comment = Prompt.ask("Enter comment (optional)", default="")
        
        # Write outputs
        case_out = output_dir / case.id
        case_out.mkdir(parents=True, exist_ok=True)
        csv_path = write_image_qc_csv(output_dir, case.id, case.original_path, rating, actual_reviewer, comment)
        
        manifest = CompletionManifest(
            status=TerminalStatus.SUCCESS,
            case_id=case.id,
            subcommand="qc-img",
            started_at=started,
            outputs=["qc_image.csv"]
        )
        write_manifest(output_dir, case.id, "qc-img", manifest)
        
        succeeded += 1
        results.append({"case_id": case.id, "status": TerminalStatus.SUCCESS.value})
        
    launcher.close()
    
    if state.json_output:
        print_json_summary("qc-img", total, succeeded, 0, 0, 0, results)
