import os
from pathlib import Path
from typing import List, Set, Iterator

from neuroimage_cli.core.models import CaseIdentifier, ProcessingMode, ExistingOutputPolicy
from neuroimage_cli.core.manifest import read_manifest
from neuroimage_cli.services.case_identifier import derive_case_id
from neuroimage_cli.core.exceptions import InvalidSettingsError

def is_hidden(path: Path) -> bool:
    return path.name.startswith('.')

def discover_cases(
    input_dir: Path, 
    output_dir: Path,
    subcommand: str,
    processing_mode: ProcessingMode,
    existing_output: ExistingOutputPolicy,
    extensions: tuple = ('.nii.gz', '.nii', '.mgz')
) -> List[CaseIdentifier]:
    """
    Traverse input_dir deterministically and yield eligible cases.
    Applies existing_output and processing_mode policies.
    """
    cases = []
    seen_ids: Set[str] = set()
    
    # Deterministic traversal
    for root, dirs, files in os.walk(input_dir, followlinks=False):
        root_path = Path(root)
        
        # Prune hidden dirs
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        dirs.sort()
        
        # Stop traversing into FastSurfer output directories (heuristic: presence of 'mri' dir)
        if 'mri' in dirs and 'scripts' in dirs:
            dirs[:] = []
            continue
            
        for file in sorted(files):
            if file.startswith('.'):
                continue
                
            if file.endswith(extensions):
                file_path = root_path / file
                case_id = derive_case_id(file_path)
                
                # Output collision detection
                if case_id in seen_ids:
                    raise InvalidSettingsError(f"Output collision detected for case_id '{case_id}'.")
                
                # Check existing manifest
                manifest = read_manifest(output_dir, case_id, subcommand)
                is_completed = manifest is not None and manifest.status == "success"
                
                if processing_mode == ProcessingMode.CONTINUE and is_completed:
                    continue
                    
                if is_completed and existing_output == ExistingOutputPolicy.SKIP:
                    continue
                    
                if is_completed and existing_output == ExistingOutputPolicy.ERROR:
                    raise InvalidSettingsError(f"Case {case_id} already has completed output and policy is 'error'.")
                
                seen_ids.add(case_id)
                cases.append(CaseIdentifier(id=case_id, original_path=file_path))
                
    return cases
