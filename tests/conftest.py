import json

import nibabel as nib
import numpy as np
import pytest


@pytest.fixture
def synthetic_nifti_image():
    """Create a synthetic 10x10x10 NIfTI image for testing."""
    data = np.zeros((10, 10, 10), dtype=np.uint8)
    data[2:8, 2:8, 2:8] = 255  # Add a "brain" cube
    affine = np.eye(4)
    return nib.Nifti1Image(data, affine)


@pytest.fixture
def synthetic_nifti_file(tmp_path, synthetic_nifti_image):
    """Write a synthetic NIfTI image to a temporary file."""
    file_path = tmp_path / "sub-01_T1w.nii.gz"
    nib.save(synthetic_nifti_image, str(file_path))
    return file_path


@pytest.fixture
def mock_fastsurfer_output(tmp_path):
    """Create a mock FastSurfer output directory structure."""
    out_dir = tmp_path / "fastsurfer_out"
    out_dir.mkdir()

    # Create sub-01 output
    sub1_dir = out_dir / "sub-01_T1w"
    mri_dir = sub1_dir / "mri"
    mri_dir.mkdir(parents=True)

    # Create dummy files
    (mri_dir / "brainmask.mgz").touch()
    (mri_dir / "aparc.DKTatlas+aseg.deep.mgz").touch()

    # Write a success manifest
    manifest_path = sub1_dir / "fastsurfer_manifest.json"
    manifest_data = {
        "status": "success",
        "case_id": "sub-01_T1w",
        "subcommand": "fastsurfer",
        "outputs": ["mri/brainmask.mgz", "mri/aparc.DKTatlas+aseg.deep.mgz"],
    }
    manifest_path.write_text(json.dumps(manifest_data))

    return out_dir
