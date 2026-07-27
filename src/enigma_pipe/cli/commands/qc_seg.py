import typer
from typing import Optional
from pathlib import Path
from rich.prompt import Prompt, IntPrompt
from datetime import datetime, timezone

from enigma_pipe.core.config import load_settings
from enigma_pipe.core.models import ProcessingMode, ExistingOutputPolicy, TerminalStatus, SegmentationType
from enigma_pipe.services.case_discovery import discover_cases
from enigma_pipe.services.itksnap import ITKSnapLauncher
from enigma_pipe.services.qc_segmentation import write_segmentation_qc_csv
from enigma_pipe.core.manifest import CompletionManifest, write_manifest
from enigma_pipe.cli.main import state, app
from enigma_pipe.cli.formatting import print_error, print_info, print_warning, print_json_summary
import re

# Map of SegmentationType to expected FastSurfer output filenames
SEG_FILES = {
    SegmentationType.ASEG: "mri/aparc.DKTatlas+aseg.deep.mgz",
    SegmentationType.BRAINSTEM: "mri/brainstem.mgz",
    SegmentationType.CEREBNET: "mri/cerebnet.mgz",
    SegmentationType.ENIGMA_SC: "mri/enigma-sc.mgz"
}

@app.command(name="qc-seg", help="Interactive Segmentation QC via ITK-SNAP")
def qc_seg_main(
    input_dir: Path = typer.Argument(..., help="Directory containing FastSurfer outputs", exists=True, file_okay=False, dir_okay=True),
    output_dir: Path = typer.Argument(..., help="Output directory for QC records", file_okay=False, dir_okay=True),
    processing_mode: ProcessingMode = typer.Option(ProcessingMode.ALL, "--processing-mode", help="Case selection mode"),
    existing_output: ExistingOutputPolicy = typer.Option(ExistingOutputPolicy.SKIP, "--existing-output", help="Existing output policy"),
    reviewer_id: Optional[str] = typer.Option(None, "--reviewer-id", help="Reviewer ID (defaults to OS user)")
):
    settings = load_settings(state.settings_path)
    
    # Precedence: CLI > YAML (default OS user is handled in config)
    actual_reviewer = reviewer_id if reviewer_id is not None else settings.reviewer_id
    
    # input_dir is the output_dir from fastsurfer containing case folders
    try:
        # We need to find the NIfTI inputs that generated these outputs, or just iterate the fastsurfer output dirs.
        # But wait, discover_cases looks for T1w.nii.gz.
        # For qc-seg, the input is actually the FastSurfer output directory itself.
        # However, plan/spec says "cases" are resolved based on the input_dir.
        # We will reuse discover_cases by looking for the brainmask in the fastsurfer output.
        # Wait, the requirements state deterministic traversal for qc-seg stops when it finds FastSurfer output.
        cases = discover_cases(input_dir, output_dir, "qc-seg", processing_mode, existing_output, extensions=("brainmask.mgz",))
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
    
    print_info(f"Starting Segmentation QC for {total} cases.")
    
    for idx, case in enumerate(cases):
        print_info(f"[{idx+1}/{total}] Case: {case.id}")
        started = datetime.now(timezone.utc)
        
        # The T1 image to load as background
        t1_path = case.original_path # this is brainmask.mgz based on extensions arg above
        
        # For each segmentation type to eval
        case_root = case.original_path.parent.parent # Since original_path is mri/brainmask.mgz
        
        # Extract FastSurfer version
        fastsurfer_version = ""
        log_file = case_root / "scripts" / "recon-surf.log"
        if log_file.exists():
            try:
                content = log_file.read_text()
                # Look for FastSurfer version string
                match = re.search(r"FastSurfer version:?\s*v?([\d\.]+)", content, re.IGNORECASE)
                if match:
                    fastsurfer_version = match.group(1)
            except Exception:
                pass
                
        if not fastsurfer_version:
            print_warning(f"Could not determine FastSurfer version for case {case.id}")
        
        csvs_written = []
        for seg_type in settings.segmentation_to_eval:
            seg_file = case_root / SEG_FILES[seg_type]
            if not seg_file.exists():
                print_info(f"Skipping {seg_type.value}, not found for case {case.id}")
                continue
                
            print_info(f"Reviewing {seg_type.value}...")
            launcher.launch(t1_path, [seg_file])
            
            rating = None
            while rating is None:
                try:
                    val = IntPrompt.ask(f"Enter quality rating for {seg_type.value} (0-5)", show_choices=False)
                    if 0 <= val <= 5:
                        rating = val
                    else:
                        print_error("Rating must be between 0 and 5.")
                except typer.Abort:
                    launcher.close()
                    manifest = CompletionManifest(
                        status=TerminalStatus.INTERRUPTED,
                        case_id=case.id,
                        subcommand="qc-seg",
                        started_at=started
                    )
                    write_manifest(output_dir, case.id, "qc-seg", manifest)
                    results.append({"case_id": case.id, "status": TerminalStatus.INTERRUPTED.value})
                    if state.json_output:
                        print_json_summary("qc-seg", total, succeeded, 0, total - succeeded - 1, 130, results)
                    raise typer.Exit(130)
                    
            comment = Prompt.ask(f"Enter comment for {seg_type.value} (optional)", default="")
            
            case_out = output_dir / case.id
            case_out.mkdir(parents=True, exist_ok=True)
            csv_path = write_segmentation_qc_csv(
                output_dir=output_dir, 
                case_id=case.id, 
                image_path=t1_path, 
                segmentation_path=seg_file, 
                seg_type=seg_type, 
                rating=rating, 
                reviewer_id=actual_reviewer,
                fastsurfer_version=fastsurfer_version,
                comment=comment
            )
            csvs_written.append(csv_path.name)
            
        manifest = CompletionManifest(
            status=TerminalStatus.SUCCESS,
            case_id=case.id,
            subcommand="qc-seg",
            started_at=started,
            outputs=csvs_written
        )
        write_manifest(output_dir, case.id, "qc-seg", manifest)
        
        succeeded += 1
        results.append({"case_id": case.id, "status": TerminalStatus.SUCCESS.value})
        
    launcher.close()
    
    if state.json_output:
        print_json_summary("qc-seg", total, succeeded, 0, 0, 0, results)
