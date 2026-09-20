from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from enigma_pipe.core.exceptions import InvalidSettingsError, MissingDependencyError
from enigma_pipe.core.models import ExecutionMode, ExistingOutputPolicy, ProcessingMode
from enigma_pipe.services.case_discovery import discover_cases
from enigma_pipe.services.enigma_sc import (
    DEFAULT_DOCKER_IMAGE,
    DEFAULT_SIF_IMAGE,
    ENIGMA_SC_ENTRYPOINT,
    LEGACY_SIF_IMAGE,
    EnigmaSCRunner,
    check_gpu_availability,
    consolidate_group_tables,
    derive_bids_case_id,
    discover_bids_cases,
    is_bids_dataset,
    stage_case_input,
    verify_case_outputs,
)


@pytest.fixture
def mock_runtime_available():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        yield mock_run


def test_runner_docker_init_default(mock_runtime_available):
    assert DEFAULT_DOCKER_IMAGE == "art2mri/pipeline_enigma_cli:1.0"
    runner = EnigmaSCRunner(mode=ExecutionMode.DOCKER)
    assert runner.mode == ExecutionMode.DOCKER
    assert runner.image == "art2mri/pipeline_enigma_cli:1.0"
    assert runner._entrypoint() == []


def test_runner_docker_init_custom_image(mock_runtime_available):
    runner = EnigmaSCRunner(mode=ExecutionMode.DOCKER, image_docker="my-custom-img:tag")
    assert runner.image == "my-custom-img:tag"


def test_runner_singularity_default_sif_resolution(mock_runtime_available, tmp_path, monkeypatch):
    assert DEFAULT_SIF_IMAGE.name == "pipeline_enigma_cli.sif"
    assert LEGACY_SIF_IMAGE.name == "pipeline-enigma-cli.sif"

    # Case 1: default SIF does not exist
    monkeypatch.setattr(
        "enigma_pipe.services.enigma_sc.DEFAULT_SIF_IMAGE",
        tmp_path / "pipeline_enigma_cli.sif",
    )
    monkeypatch.setattr(
        "enigma_pipe.services.enigma_sc.LEGACY_SIF_IMAGE",
        tmp_path / "pipeline-enigma-cli.sif",
    )
    with pytest.raises(MissingDependencyError) as exc:
        EnigmaSCRunner(mode=ExecutionMode.SINGULARITY)
    assert "pipeline_enigma_cli.sif" in str(exc.value)

    # Case 2: legacy SIF exists, default SIF does not -> falls back to legacy
    legacy_sif = tmp_path / "pipeline-enigma-cli.sif"
    legacy_sif.write_text("legacy")
    runner_legacy = EnigmaSCRunner(mode=ExecutionMode.SINGULARITY)
    assert runner_legacy.image == str(legacy_sif.resolve())

    # Case 3: default SIF exists -> takes precedence
    default_sif = tmp_path / "pipeline_enigma_cli.sif"
    default_sif.write_text("default")
    runner_default = EnigmaSCRunner(mode=ExecutionMode.SINGULARITY)
    assert runner_default.image == str(default_sif.resolve())


def test_runner_singularity_missing_sif(mock_runtime_available, tmp_path):
    non_existent = tmp_path / "missing.sif"
    with pytest.raises(MissingDependencyError) as exc_info:
        EnigmaSCRunner(mode=ExecutionMode.SINGULARITY, image_sif=str(non_existent))
    assert "not found" in str(exc_info.value)


def test_runner_singularity_valid_sif(mock_runtime_available, tmp_path):
    sif_file = tmp_path / "image.sif"
    sif_file.write_text("fake sif content")
    runner = EnigmaSCRunner(mode=ExecutionMode.SINGULARITY, image_sif=str(sif_file))
    assert runner.mode == ExecutionMode.SINGULARITY
    assert runner.image == str(sif_file.resolve())
    assert runner._entrypoint() == ENIGMA_SC_ENTRYPOINT


def test_build_case_command_docker(mock_runtime_available, tmp_path):
    runner = EnigmaSCRunner(mode=ExecutionMode.DOCKER)
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    cmd = runner.build_case_command(
        case_id="patient_01",
        input_dir=input_dir,
        output_dir=output_dir,
        device="cpu",
    )

    assert "docker" in cmd
    assert "run" in cmd
    assert "--input-dir" in cmd
    assert "--output-dir" in cmd
    assert "--subject" in cmd
    assert "patient_01" in cmd
    assert "--gpus" not in cmd


def test_build_case_command_docker_gpu(mock_runtime_available, tmp_path):
    runner = EnigmaSCRunner(mode=ExecutionMode.DOCKER)
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    cmd = runner.build_case_command(
        case_id="patient_01",
        input_dir=input_dir,
        output_dir=output_dir,
        device="gpu",
    )

    assert "--gpus" in cmd
    assert "all" in cmd


def test_build_case_command_singularity_gpu(mock_runtime_available, tmp_path):
    sif_file = tmp_path / "image.sif"
    sif_file.write_text("sif")
    runner = EnigmaSCRunner(mode=ExecutionMode.SINGULARITY, image_sif=str(sif_file))
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    cmd = runner.build_case_command(
        case_id="patient_01",
        input_dir=input_dir,
        output_dir=output_dir,
        device="cuda",
    )

    assert runner.mode.value in cmd[0]
    assert "exec" in cmd
    assert "--nv" in cmd
    assert "python3" in cmd
    assert "/enigma_pipeline.py" in cmd


def test_build_case_command_apptainer_gpu(mock_runtime_available, tmp_path):
    sif_file = tmp_path / "image.sif"
    sif_file.write_text("sif")
    runner = EnigmaSCRunner(mode=ExecutionMode.APPTAINER, image_sif=str(sif_file))
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    cmd = runner.build_case_command(
        case_id="patient_01",
        input_dir=input_dir,
        output_dir=output_dir,
        device="gpu",
    )

    assert runner.mode.value in cmd[0]
    assert "exec" in cmd
    assert "--nv" in cmd
    assert "python3" in cmd
    assert "/enigma_pipeline.py" in cmd


def test_verify_case_outputs_success(tmp_path):
    output_dir = tmp_path / "output"
    case_id = "patient_01"
    case_dir = output_dir / case_id
    subfolder = case_dir / case_id
    subfolder.mkdir(parents=True)

    # Create all mandatory files
    (subfolder / f"{case_id}_seg.nii.gz").write_text("dummy")
    (subfolder / f"{case_id}_seg_labeled.nii.gz").write_text("dummy")
    (subfolder / f"{case_id}_labels_vert.nii.gz").write_text("dummy")
    (subfolder / f"{case_id}_csa.csv").write_text("Slice,Area\n1,75.0\n")
    (case_dir / "csa_final_table_20260920.csv").write_text("Metric,Value\nMean,75.0\n")

    valid, err = verify_case_outputs(output_dir, case_id)
    assert valid is True
    assert err is None


def test_verify_case_outputs_missing_files(tmp_path):
    output_dir = tmp_path / "output"
    case_id = "patient_01"
    case_dir = output_dir / case_id
    subfolder = case_dir / case_id
    subfolder.mkdir(parents=True)

    # Missing labels_vert and summary tables
    (subfolder / f"{case_id}_seg.nii.gz").write_text("dummy")
    (subfolder / f"{case_id}_seg_labeled.nii.gz").write_text("dummy")
    (subfolder / f"{case_id}_csa.csv").write_text("Slice,Area\n1,75.0\n")

    valid, err = verify_case_outputs(output_dir, case_id)
    assert valid is False
    assert err is not None
    assert f"{case_id}_labels_vert.nii.gz" in err
    assert "csa_final_table" in err


def test_consolidate_group_tables_empty(tmp_path):
    csa_path, ecc_path = consolidate_group_tables(tmp_path, [])
    assert csa_path is None
    assert ecc_path is None


def test_consolidate_group_tables_success(tmp_path):
    output_dir = tmp_path / "output"

    # Create case 1
    case1_dir = output_dir / "sub-01"
    case1_dir.mkdir(parents=True)
    (case1_dir / "csa_final_table_2026.csv").write_text("Subject,CSA\nsub-01,72.5\n")
    (case1_dir / "eccentricity_table_2026.csv").write_text("Subject,Ecc\nsub-01,0.85\n")

    # Create case 2
    case2_dir = output_dir / "sub-02"
    case2_dir.mkdir(parents=True)
    (case2_dir / "csa_final_table_2026.csv").write_text("Subject,CSA\nsub-02,68.1\n")
    (case2_dir / "eccentricity_table_2026.csv").write_text("Subject,Ecc\nsub-02,0.79\n")

    csa_out, ecc_out = consolidate_group_tables(output_dir, ["sub-01", "sub-02"])

    assert csa_out is not None and csa_out.is_file()
    assert ecc_out is not None and ecc_out.is_file()

    csa_content = csa_out.read_text().splitlines()
    assert len(csa_content) == 3
    assert csa_content[0] == "Subject,CSA"
    assert "sub-01,72.5" in csa_content
    assert "sub-02,68.1" in csa_content

    ecc_content = ecc_out.read_text().splitlines()
    assert len(ecc_content) == 3
    assert ecc_content[0] == "Subject,Ecc"
    assert "sub-01,0.85" in ecc_content
    assert "sub-02,0.79" in ecc_content


def test_check_gpu_availability():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert check_gpu_availability() is True

    with patch("subprocess.run", side_effect=FileNotFoundError):
        assert check_gpu_availability() is False


def test_runner_run_case(mock_runtime_available, tmp_path):
    runner = EnigmaSCRunner(mode=ExecutionMode.DOCKER)
    input_file = tmp_path / "patient_01.nii.gz"
    input_file.write_text("fake nifti")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    with patch.object(runner, "run", return_value=0) as mock_run_call:
        ret = runner.run_case("patient_01", input_file, output_dir, device="cpu")
        assert ret == 0
        assert mock_run_call.called

        binds = mock_run_call.call_args[0][0]
        src_paths = [str(b[0]) for b in binds]
        dst_paths = [str(b[1]) for b in binds]

        assert any("output" in p and "patient_01" in p for p in src_paths)
        assert any("output_data" in p for p in dst_paths)
        assert any("input_data" in p for p in dst_paths)

        # Ensure staging dir was cleaned up
        staging_dir = output_dir / "patient_01" / ".staging_input"
        assert not staging_dir.exists()


def test_is_bids_dataset(tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert is_bids_dataset(empty_dir) is False

    # With dataset_description.json
    bids_dir1 = tmp_path / "bids1"
    bids_dir1.mkdir()
    (bids_dir1 / "dataset_description.json").write_text('{"Name": "Test"}')
    assert is_bids_dataset(bids_dir1) is True

    # With sub-* directory
    bids_dir2 = tmp_path / "bids2"
    bids_dir2.mkdir()
    (bids_dir2 / "sub-01").mkdir()
    assert is_bids_dataset(bids_dir2) is True


def test_derive_bids_case_id():
    p1 = Path("sub-01_T1w.nii.gz")
    assert derive_bids_case_id(p1) == "sub-01"

    p2 = Path("sub-01_ses-01_T1w.nii.gz")
    assert derive_bids_case_id(p2) == "sub-01_ses-01"

    p3 = Path("sub-02_ses-02_run-1_T1w.nii")
    assert derive_bids_case_id(p3) == "sub-02_ses-02_run-1"

    p4 = Path("loose_scan.nii.gz")
    assert derive_bids_case_id(p4) == "loose_scan"


def test_stage_case_input(tmp_path):
    source = tmp_path / "source.nii.gz"
    source.write_text("dummy nifti content")
    target_dir = tmp_path / "staged"

    staged_file = stage_case_input(source, target_dir, "case_01.nii.gz")
    assert staged_file.is_file()
    assert staged_file.read_text() == "dummy nifti content"
    assert staged_file.name == "case_01.nii.gz"


def test_discover_bids_cases(tmp_path):
    bids_dir = tmp_path / "bids"
    bids_dir.mkdir()
    (bids_dir / "dataset_description.json").write_text('{"Name": "Test"}')

    # Subject 1 with 2 sessions
    sub1_ses1 = bids_dir / "sub-01" / "ses-01" / "anat"
    sub1_ses1.mkdir(parents=True)
    (sub1_ses1 / "sub-01_ses-01_T1w.nii.gz").write_text("t1")
    (sub1_ses1 / "sub-01_ses-01_T2w.nii.gz").write_text("t2")  # should be ignored

    sub1_ses2 = bids_dir / "sub-01" / "ses-02" / "anat"
    sub1_ses2.mkdir(parents=True)
    (sub1_ses2 / "sub-01_ses-02_T1w.nii.gz").write_text("t1")

    # Subject 2 with single session
    sub2_anat = bids_dir / "sub-02" / "anat"
    sub2_anat.mkdir(parents=True)
    (sub2_anat / "sub-02_T1w.nii.gz").write_text("t1")

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    results = discover_bids_cases(
        input_dir=bids_dir,
        output_dir=output_dir,
        subcommand="enigma-sc",
        processing_mode=ProcessingMode.ALL,
        existing_output=ExistingOutputPolicy.ERROR,
    )

    assert len(results) == 3
    discovered_ids = {c.id for c in results}
    assert discovered_ids == {"sub-01_ses-01", "sub-01_ses-02", "sub-02"}


def test_collision_detection(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "sub-01.nii").write_text("1")
    (input_dir / "sub-01.nii.gz").write_text("2")

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    with pytest.raises(InvalidSettingsError) as exc_info:
        discover_cases(
            input_dir=input_dir,
            output_dir=output_dir,
            subcommand="enigma-sc",
            processing_mode=ProcessingMode.ALL,
            existing_output=ExistingOutputPolicy.ERROR,
            extensions=(".nii.gz", ".nii"),
        )
    assert "Output collision detected for case_id 'sub-01'" in str(exc_info.value)


def test_bids_collision_detection(tmp_path):
    bids_dir = tmp_path / "bids"
    bids_dir.mkdir()
    (bids_dir / "dataset_description.json").write_text('{"Name": "Test"}')

    # Two scans that resolve to same BIDS case_id
    d1 = bids_dir / "sub-01" / "anat"
    d1.mkdir(parents=True)
    (d1 / "sub-01_T1w.nii").write_text("1")
    (d1 / "sub-01_T1w.nii.gz").write_text("2")

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    with pytest.raises(InvalidSettingsError) as exc_info:
        discover_bids_cases(
            input_dir=bids_dir,
            output_dir=output_dir,
            subcommand="enigma-sc",
            processing_mode=ProcessingMode.ALL,
            existing_output=ExistingOutputPolicy.ERROR,
        )
    assert "Output collision detected for case_id 'sub-01'" in str(exc_info.value)


def test_empty_input_directory(tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    results = discover_cases(
        input_dir=empty_dir,
        output_dir=output_dir,
        subcommand="enigma-sc",
        processing_mode=ProcessingMode.ALL,
        existing_output=ExistingOutputPolicy.ERROR,
        extensions=(".nii.gz", ".nii"),
    )
    assert len(results) == 0
