import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from enigma_pipe.cli.main import app
from enigma_pipe.core.exceptions import MissingDependencyError
from enigma_pipe.core.manifest import read_manifest
from enigma_pipe.core.models import TerminalStatus

runner = CliRunner()


def create_dummy_sc_outputs(output_dir: Path, case_id: str):
    """Helper to generate valid ENIGMA-SC output files for a case."""
    case_dir = output_dir / case_id
    subfolder = case_dir / case_id
    subfolder.mkdir(parents=True, exist_ok=True)

    (subfolder / f"{case_id}_seg.nii.gz").write_text("seg")
    (subfolder / f"{case_id}_seg_labeled.nii.gz").write_text("labeled")
    (subfolder / f"{case_id}_labels_vert.nii.gz").write_text("vert")
    (subfolder / f"{case_id}_csa.csv").write_text("Slice,Area\n1,75.0\n")

    (case_dir / "csa_final_table_2026.csv").write_text(f"Subject,CSA\n{case_id},75.0\n")
    (case_dir / "eccentricity_table_2026.csv").write_text(f"Subject,Ecc\n{case_id},0.82\n")


@pytest.fixture
def mock_container_runtime():
    with patch("enigma_pipe.services.container.ContainerRunner._check_runtime") as mock_check:
        mock_check.return_value = None
        yield mock_check


def test_enigma_sc_happy_path(tmp_path, mock_container_runtime, monkeypatch):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "patient_01.nii.gz").write_text("nii")
    (input_dir / "patient_02.nii.gz").write_text("nii")

    output_dir = tmp_path / "output"

    def fake_run_case(
        self, case_id, input_nifti_path, output_dir, device="cpu", replace_output=False
    ):
        create_dummy_sc_outputs(output_dir, case_id)
        return 0

    monkeypatch.setattr(
        "enigma_pipe.services.enigma_sc.EnigmaSCRunner.run_case",
        fake_run_case,
    )

    result = runner.invoke(app, ["enigma-sc", str(input_dir), str(output_dir)])
    assert result.exit_code == 0

    # Verify manifests
    m1 = read_manifest(output_dir, "patient_01", "enigma-sc")
    assert m1 is not None
    assert m1.status == TerminalStatus.SUCCESS

    m2 = read_manifest(output_dir, "patient_02", "enigma-sc")
    assert m2 is not None
    assert m2.status == TerminalStatus.SUCCESS

    # Verify group summary tables
    csa_group = output_dir / "csa_group_summary.csv"
    ecc_group = output_dir / "eccentricity_group_summary.csv"
    assert csa_group.is_file()
    assert ecc_group.is_file()

    csa_content = csa_group.read_text()
    assert "patient_01,75.0" in csa_content
    assert "patient_02,75.0" in csa_content


def test_enigma_sc_existing_output_skip_and_continue(tmp_path, mock_container_runtime, monkeypatch):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "patient_01.nii.gz").write_text("nii")
    (input_dir / "patient_02.nii.gz").write_text("nii")

    output_dir = tmp_path / "output"

    processed = []

    def fake_run_case(
        self, case_id, input_nifti_path, output_dir, device="cpu", replace_output=False
    ):
        processed.append(case_id)
        create_dummy_sc_outputs(output_dir, case_id)
        return 0

    monkeypatch.setattr(
        "enigma_pipe.services.enigma_sc.EnigmaSCRunner.run_case",
        fake_run_case,
    )

    # First run processes both
    res1 = runner.invoke(app, ["enigma-sc", str(input_dir), str(output_dir)])
    assert res1.exit_code == 0
    assert processed == ["patient_01", "patient_02"]

    processed.clear()

    # Second run with --existing-output skip skips both
    res2 = runner.invoke(
        app,
        ["enigma-sc", "--existing-output", "skip", str(input_dir), str(output_dir)],
    )
    assert res2.exit_code == 0
    assert processed == []

    # Third run with --processing-mode continue also skips both
    res3 = runner.invoke(
        app,
        ["enigma-sc", "--processing-mode", "continue", str(input_dir), str(output_dir)],
    )
    assert res3.exit_code == 0
    assert processed == []


def test_enigma_sc_existing_output_error(tmp_path, mock_container_runtime, monkeypatch):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "patient_01.nii.gz").write_text("nii")
    output_dir = tmp_path / "output"

    def fake_run_case(
        self, case_id, input_nifti_path, output_dir, device="cpu", replace_output=False
    ):
        create_dummy_sc_outputs(output_dir, case_id)
        return 0

    monkeypatch.setattr(
        "enigma_pipe.services.enigma_sc.EnigmaSCRunner.run_case",
        fake_run_case,
    )

    res1 = runner.invoke(app, ["enigma-sc", str(input_dir), str(output_dir)])
    assert res1.exit_code == 0

    # Running with --existing-output error must fail with exit code 2
    res2 = runner.invoke(
        app,
        ["enigma-sc", "--existing-output", "error", str(input_dir), str(output_dir)],
    )
    assert res2.exit_code == 2
    assert "already has completed output" in res2.output


def test_enigma_sc_existing_output_replace_sets_replace_flag(
    tmp_path, mock_container_runtime, monkeypatch
):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "patient_01.nii.gz").write_text("nii")
    output_dir = tmp_path / "output"

    replace_flags = []

    def fake_run_case(
        self, case_id, input_nifti_path, output_dir, device="cpu", replace_output=False
    ):
        replace_flags.append(replace_output)
        create_dummy_sc_outputs(output_dir, case_id)
        return 0

    monkeypatch.setattr(
        "enigma_pipe.services.enigma_sc.EnigmaSCRunner.run_case",
        fake_run_case,
    )

    res = runner.invoke(
        app,
        ["enigma-sc", "--existing-output", "replace", str(input_dir), str(output_dir)],
    )
    assert res.exit_code == 0
    assert replace_flags == [True]


def test_enigma_sc_case_failure(tmp_path, mock_container_runtime, monkeypatch):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "patient_01.nii.gz").write_text("nii")
    output_dir = tmp_path / "output"

    def fake_run_case(
        self, case_id, input_nifti_path, output_dir, device="cpu", replace_output=False
    ):
        return 1

    monkeypatch.setattr(
        "enigma_pipe.services.enigma_sc.EnigmaSCRunner.run_case",
        fake_run_case,
    )

    res = runner.invoke(app, ["enigma-sc", str(input_dir), str(output_dir)])
    assert res.exit_code == 4

    m = read_manifest(output_dir, "patient_01", "enigma-sc")
    assert m is not None
    assert m.status == TerminalStatus.FAILED


def test_enigma_sc_missing_output_demoted_to_failed(tmp_path, mock_container_runtime, monkeypatch):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "patient_01.nii.gz").write_text("nii")
    output_dir = tmp_path / "output"

    def fake_run_case(
        self, case_id, input_nifti_path, output_dir, device="cpu", replace_output=False
    ):
        # Returncode 0 but DO NOT create expected outputs
        return 0

    monkeypatch.setattr(
        "enigma_pipe.services.enigma_sc.EnigmaSCRunner.run_case",
        fake_run_case,
    )

    res = runner.invoke(app, ["enigma-sc", str(input_dir), str(output_dir)])
    assert res.exit_code == 4

    m = read_manifest(output_dir, "patient_01", "enigma-sc")
    assert m is not None
    assert m.status == TerminalStatus.FAILED
    assert "Missing required output artifacts" in (m.error_message or "")


def test_enigma_sc_keyboard_interrupt(tmp_path, mock_container_runtime, monkeypatch):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "patient_01.nii.gz").write_text("nii")
    output_dir = tmp_path / "output"

    def fake_run_case(
        self, case_id, input_nifti_path, output_dir, device="cpu", replace_output=False
    ):
        raise KeyboardInterrupt()

    monkeypatch.setattr(
        "enigma_pipe.services.enigma_sc.EnigmaSCRunner.run_case",
        fake_run_case,
    )

    res = runner.invoke(app, ["enigma-sc", str(input_dir), str(output_dir)])
    assert res.exit_code == 130

    m = read_manifest(output_dir, "patient_01", "enigma-sc")
    assert m is not None
    assert m.status == TerminalStatus.INTERRUPTED


def test_enigma_sc_json_output(tmp_path, mock_container_runtime, monkeypatch):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "patient_01.nii.gz").write_text("nii")
    output_dir = tmp_path / "output"

    def fake_run_case(
        self, case_id, input_nifti_path, output_dir, device="cpu", replace_output=False
    ):
        create_dummy_sc_outputs(output_dir, case_id)
        return 0

    monkeypatch.setattr(
        "enigma_pipe.services.enigma_sc.EnigmaSCRunner.run_case",
        fake_run_case,
    )

    res = runner.invoke(app, ["--json", "enigma-sc", str(input_dir), str(output_dir)])
    assert res.exit_code == 0

    data = json.loads(res.stdout.strip())
    assert data["command"] == "enigma-sc"
    assert data["total_cases"] == 1
    assert data["succeeded"] == 1
    assert data["failed"] == 0
    assert data["exit_code"] == 0


def test_enigma_sc_bids_dataset(tmp_path, mock_container_runtime, monkeypatch):
    bids_dir = tmp_path / "bids_dataset"
    bids_dir.mkdir()
    (bids_dir / "dataset_description.json").write_text('{"Name": "BIDS Study"}')

    # Two sessions for sub-01
    s1 = bids_dir / "sub-01" / "ses-01" / "anat"
    s1.mkdir(parents=True)
    (s1 / "sub-01_ses-01_T1w.nii.gz").write_text("dummy")

    s2 = bids_dir / "sub-01" / "ses-02" / "anat"
    s2.mkdir(parents=True)
    (s2 / "sub-01_ses-02_T1w.nii.gz").write_text("dummy")

    output_dir = tmp_path / "output"

    processed = []

    def fake_run_case(
        self, case_id, input_nifti_path, output_dir, device="cpu", replace_output=False
    ):
        processed.append(case_id)
        create_dummy_sc_outputs(output_dir, case_id)
        return 0

    monkeypatch.setattr(
        "enigma_pipe.services.enigma_sc.EnigmaSCRunner.run_case",
        fake_run_case,
    )

    res = runner.invoke(app, ["enigma-sc", str(bids_dir), str(output_dir)])
    assert res.exit_code == 0
    assert sorted(processed) == ["sub-01_ses-01", "sub-01_ses-02"]

    # Manifests for both
    m1 = read_manifest(output_dir, "sub-01_ses-01", "enigma-sc")
    assert m1 is not None and m1.status == TerminalStatus.SUCCESS

    m2 = read_manifest(output_dir, "sub-01_ses-02", "enigma-sc")
    assert m2 is not None and m2.status == TerminalStatus.SUCCESS

    # Group tables contain both
    csa_group = output_dir / "csa_group_summary.csv"
    assert csa_group.is_file()
    content = csa_group.read_text()
    assert "sub-01_ses-01" in content
    assert "sub-01_ses-02" in content


def test_enigma_sc_gpu_unavailable(tmp_path, monkeypatch):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    monkeypatch.setattr(
        "enigma_pipe.cli.commands.enigma_sc.check_gpu_availability",
        lambda: False,
    )

    res = runner.invoke(app, ["enigma-sc", "--device", "gpu", str(input_dir), str(output_dir)])
    assert res.exit_code == 3
    assert "GPU acceleration requested" in res.output


def test_enigma_sc_invalid_device(tmp_path):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    res = runner.invoke(app, ["enigma-sc", "--device", "tpu", str(input_dir), str(output_dir)])
    assert res.exit_code == 2
    assert "Invalid device" in res.output


def test_enigma_sc_invalid_execution_mode(tmp_path):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    res = runner.invoke(
        app, ["enigma-sc", "--execution-mode", "kubernetes", str(input_dir), str(output_dir)]
    )
    assert res.exit_code == 2
    assert "Invalid execution mode" in res.output


def test_enigma_sc_missing_runtime(tmp_path, monkeypatch):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    def fake_check(self):
        raise MissingDependencyError("Docker runtime not found.")

    monkeypatch.setattr(
        "enigma_pipe.services.container.ContainerRunner._check_runtime",
        fake_check,
    )

    res = runner.invoke(app, ["enigma-sc", str(input_dir), str(output_dir)])
    assert res.exit_code == 3
    assert "Docker runtime not found" in res.output


def test_enigma_sc_singularity_missing_sif(tmp_path, mock_container_runtime):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    missing_sif = tmp_path / "missing.sif"

    res = runner.invoke(
        app,
        [
            "enigma-sc",
            "--execution-mode",
            "singularity",
            "--image-sif",
            str(missing_sif),
            str(input_dir),
            str(output_dir),
        ],
    )
    assert res.exit_code == 3
    assert "not found" in res.output


def test_enigma_sc_singularity_valid_sif_gpu(tmp_path, mock_container_runtime, monkeypatch):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "patient_01.nii.gz").write_text("dummy")

    output_dir = tmp_path / "out"
    output_dir.mkdir()

    sif_file = tmp_path / "pipeline.sif"
    sif_file.write_text("sif dummy")

    monkeypatch.setattr(
        "enigma_pipe.cli.commands.enigma_sc.check_gpu_availability",
        lambda: True,
    )

    def fake_run_case(
        self, case_id, input_nifti_path, output_dir, device="cpu", replace_output=False
    ):
        create_dummy_sc_outputs(output_dir, case_id)
        return 0

    monkeypatch.setattr(
        "enigma_pipe.services.enigma_sc.EnigmaSCRunner.run_case",
        fake_run_case,
    )

    res = runner.invoke(
        app,
        [
            "enigma-sc",
            "--execution-mode",
            "singularity",
            "--image-sif",
            str(sif_file),
            "--device",
            "gpu",
            str(input_dir),
            str(output_dir),
        ],
    )
    assert res.exit_code == 0
    m = read_manifest(output_dir, "patient_01", "enigma-sc")
    assert m is not None and m.status == TerminalStatus.SUCCESS
