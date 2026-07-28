import pytest

from enigma_pipe.core.exceptions import InvalidSettingsError
from enigma_pipe.core.models import ExistingOutputPolicy, ProcessingMode
from enigma_pipe.services.case_discovery import discover_cases


def test_output_collision(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    (input_dir / "sub-01_T1w.nii.gz").touch()
    # Create another file that resolves to the same ID
    (input_dir / "sub-01_T1w.mgz").touch()

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    with pytest.raises(InvalidSettingsError, match="Output collision detected"):
        discover_cases(
            input_dir, output_dir, "fastsurfer", ProcessingMode.ALL, ExistingOutputPolicy.ERROR
        )
