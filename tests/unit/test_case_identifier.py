import pytest
from pathlib import Path
from neuroimage_cli.core.exceptions import InvalidSettingsError
from neuroimage_cli.services.case_discovery import discover_cases
from neuroimage_cli.core.models import ProcessingMode, ExistingOutputPolicy

def test_output_collision(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    
    (input_dir / "sub-01_T1w.nii.gz").touch()
    # Create another file that resolves to the same ID
    (input_dir / "sub-01_T1w.mgz").touch()
    
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    
    with pytest.raises(InvalidSettingsError, match="Output collision detected"):
        discover_cases(input_dir, output_dir, "fastsurfer", ProcessingMode.ALL, ExistingOutputPolicy.ERROR)
