import typer
from typing import Optional
import nibabel as nib
import tempfile
import os
from pathlib import Path
from datetime import datetime, timezone

from enigma_pipe.core.config import load_settings
from enigma_pipe.core.models import ProcessingMode, ExistingOutputPolicy, TerminalStatus, SegmentationType
from enigma_pipe.services.case_discovery import discover_cases
from enigma_pipe.services.registration import register_to_mni, apply_transform
from enigma_pipe.services.slicer import generate_captures
from enigma_pipe.services.lut import parse_freesurfer_lut
from enigma_pipe.core.manifest import CompletionManifest, write_manifest
from enigma_pipe.cli.main import state, app
from enigma_pipe.cli.formatting import print_error, print_info, print_json_summary
from enigma_pipe.cli.commands.qc_seg import SEG_FILES

@app.command(name="slicer", help="Generate Slice Captures")
def slicer_main(
    input_dir: Path = typer.Argument(..., help="Directory containing FastSurfer outputs", exists=True, file_okay=False, dir_okay=True),
    output_dir: Path = typer.Argument(..., help="Output directory for captures", file_okay=False, dir_okay=True),
    mni_template: Path = typer.Option(..., "--mni", help="Path to MNI152 template"),
    lut_file: Optional[Path] = typer.Option(None, "--lut", help="Path to specific LUT file (optional)"),
    processing_mode: ProcessingMode = typer.Option(ProcessingMode.ALL, "--processing-mode", help="Case selection mode"),
    existing_output: ExistingOutputPolicy = typer.Option(ExistingOutputPolicy.SKIP, "--existing-output", help="Existing output policy"),
    alpha: Optional[float] = typer.Option(None, "--alpha", help="Overlay alpha blending"),
    slices_per_plane: Optional[int] = typer.Option(None, "--slices", help="Slices per plane"),
    fmt: Optional[str] = typer.Option(None, "--format", help="Output image format")
):
    settings = load_settings(state.settings_path)
    
    # Apply CLI overrides to settings
    if alpha is not None:
        settings.slicer.alpha = alpha
    if slices_per_plane is not None:
        settings.slicer.slices_per_plane = slices_per_plane
    if fmt is not None:
        settings.slicer.format = fmt
    
    try:
        cases = discover_cases(input_dir, output_dir, "slicer", processing_mode, existing_output, extensions=("brainmask.mgz",))
    except Exception as e:
        print_error(f"Validation error: {e}")
        raise typer.Exit(2)
        
    total = len(cases)
    total_found = getattr(cases, "total_found", total)
    skipped_count = getattr(cases, "skipped_count", 0)

    if total_found > 0 and total == 0:
        print_info(f"Discovered {total_found} cases, but all {skipped_count} cases are already completed and skipped according to policy.")
        raise typer.Exit(0)
    elif total == 0:
        print_info("No cases found to process.")
        raise typer.Exit(0)
    elif skipped_count > 0:
        print_info(f"Discovered {total_found} cases: {total} to process ({skipped_count} already completed and skipped).")
        
    succeeded = 0
    results = []
    
    print_info(f"Starting Slicer for {total} cases.")
    for idx, case in enumerate(cases):
        print_info(f"[{idx+1}/{total}] Case: {case.id}")
        started = datetime.now(timezone.utc)
        
        case_root = case.original_path.parent.parent
        t1_path = case.original_path # brainmask.mgz
        
        try:
            # 1. Convert to NIfTI & Reorient to RAS
            t1_img = nib.load(t1_path)
            t1_ras = nib.as_closest_canonical(t1_img)
            
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_t1 = Path(tmpdir) / "t1_ras.nii.gz"
                nib.save(t1_ras, tmp_t1)
                
                # 2. Register to MNI
                transform = register_to_mni(tmp_t1, mni_template)
                
                t1_mni = apply_transform(tmp_t1, transform, mni_template, is_labels=False)
                
                generated_outputs = []
                
                # 3. Process each segmentation
                for seg_type in settings.segmentation_to_eval:
                    seg_file = case_root / SEG_FILES[seg_type]
                    if not seg_file.exists():
                        continue
                        
                    # Determine LUT file
                    actual_lut_file = None
                    if lut_file:
                        actual_lut_file = lut_file
                    else:
                        lut_candidates = []
                        if seg_type == SegmentationType.ASEG:
                            lut_candidates = ["FastSurfer_ColorLUT.tsv", "FreeSurferColorLUT.txt"]
                        elif seg_type == SegmentationType.CEREBNET:
                            lut_candidates = ["CerebNet_ColorLUT.tsv", "FreeSurferColorLUT.txt"]
                        else:
                            lut_candidates = ["FreeSurferColorLUT.txt", "FreeSurferColorLUT"]
                            
                        # Check case_root/mri or case_root
                        for cand in lut_candidates:
                            if (case_root / cand).exists():
                                actual_lut_file = case_root / cand
                                break
                            if (case_root / "mri" / cand).exists():
                                actual_lut_file = case_root / "mri" / cand
                                break
                                
                    if not actual_lut_file or not actual_lut_file.exists():
                        print_warning(f"LUT file for {seg_type.value} not found. Skipping coloring for case {case.id}.")
                        # For now we skip entirely or use a fallback. The spec says "skips coloring".
                        # Let's pass an empty LUT to generate_captures so it handles it or skips.
                        # Wait, generate_captures expects a Dict. If empty, it'll just render labels without colors?
                        # Spec: "skips coloring ... rather than failing the case"
                        lut = {}
                    else:
                        lut = parse_freesurfer_lut(actual_lut_file)
                        
                    seg_img = nib.load(seg_file)
                    seg_ras = nib.as_closest_canonical(seg_img)
                    tmp_seg = Path(tmpdir) / f"seg_{seg_type.value}.nii.gz"
                    nib.save(seg_ras, tmp_seg)
                    
                    seg_mni = apply_transform(tmp_seg, transform, mni_template, is_labels=True)
                    
                    case_out_dir = output_dir / case.id
                    case_out_dir.mkdir(parents=True, exist_ok=True)
                    
                    captures = generate_captures(
                        t1_mni, seg_mni, output_dir, case.id, lut,
                        slices_per_plane=settings.slicer.slices_per_plane,
                        fmt=settings.slicer.format,
                        alpha=settings.slicer.alpha
                    )
                    
                    generated_outputs.extend(captures)
                    
                # Clean up transform
                if os.path.exists(transform):
                    os.remove(transform)
                    
            manifest = CompletionManifest(
                status=TerminalStatus.SUCCESS,
                case_id=case.id,
                subcommand="slicer",
                started_at=started,
                outputs=generated_outputs
            )
            write_manifest(output_dir, case.id, "slicer", manifest)
            succeeded += 1
            results.append({"case_id": case.id, "status": TerminalStatus.SUCCESS.value})
            
        except Exception as e:
            print_error(f"Failed to process case {case.id}: {e}")
            manifest = CompletionManifest(
                status=TerminalStatus.FAILED,
                case_id=case.id,
                subcommand="slicer",
                started_at=started,
                error_message=str(e)
            )
            write_manifest(output_dir, case.id, "slicer", manifest)
            results.append({"case_id": case.id, "status": TerminalStatus.FAILED.value})
            
    exit_code = 0 if succeeded == total else 4
    if state.json_output:
        print_json_summary("slicer", total, succeeded, total - succeeded, 0, exit_code, results)
        
    raise typer.Exit(exit_code)
