import pytest
from pathlib import Path
from enigma_pipe.core.config import load_settings
from enigma_pipe.core.exceptions import InvalidSettingsError
from enigma_pipe.services.case_discovery import discover_cases, is_hidden
from enigma_pipe.core.models import ProcessingMode, ExistingOutputPolicy

def test_load_settings_defaults():
    settings = load_settings()
    assert settings.slicer.alpha == 0.5
    assert settings.slicer.format == "jpeg"

def test_is_hidden():
    assert is_hidden(Path(".hidden")) is True
    assert is_hidden(Path("visible")) is False

def test_discover_cases(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    
    (input_dir / "sub-01_T1w.nii.gz").touch()
    (input_dir / "sub-02_T1w.mgz").touch()
    (input_dir / ".hidden_T1w.nii").touch()
    
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    
    cases = discover_cases(
        input_dir, output_dir, "fastsurfer", 
        ProcessingMode.ALL, ExistingOutputPolicy.ERROR
    )
    
    assert len(cases) == 2
    case_ids = {c.id for c in cases}
    assert "sub-01_T1w" in case_ids
    assert "sub-02_T1w" in case_ids
