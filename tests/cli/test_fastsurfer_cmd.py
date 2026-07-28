import pytest
from typer.testing import CliRunner

from enigma_pipe.cli.main import app

runner = CliRunner()


def test_fastsurfer_missing_license(tmp_path):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    result = runner.invoke(app, ["fastsurfer", str(input_dir), str(out_dir)])
    assert result.exit_code == 3
    assert "FreeSurfer license is required" in result.output


def test_fastsurfer_skip_version_check(tmp_path, monkeypatch):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    fs_license = tmp_path / "license.txt"
    fs_license.write_text("license")

    # Mock the discover_cases to prevent it from failing on empty input
    from enigma_pipe.cli.commands import fastsurfer

    monkeypatch.setattr(fastsurfer, "discover_cases", lambda *args, **kwargs: [])

    # Mock ContainerRunner to not look for docker
    monkeypatch.setattr(
        "enigma_pipe.services.container.ContainerRunner._check_runtime", lambda self: None
    )

    # Mock FreeSurferChecker
    monkeypatch.setattr(
        "enigma_pipe.cli.commands.fastsurfer.FreeSurferChecker.check_availability", lambda: None
    )

    # Mock the check_version to always return an unsupported version if called
    monkeypatch.setattr(
        "enigma_pipe.services.fastsurfer.FastSurferRunner.check_version",
        lambda self: "FastSurfer v2.3.9",
    )

    # Run WITHOUT skip_version_check
    result1 = runner.invoke(
        app, ["fastsurfer", "--fs-license", str(fs_license), str(input_dir), str(out_dir)]
    )
    assert "below the minimum supported version" in result1.output

    # Run WITH skip_version_check
    result2 = runner.invoke(
        app,
        [
            "fastsurfer",
            "--fs-license",
            str(fs_license),
            "--skip-version-check",
            str(input_dir),
            str(out_dir),
        ],
    )
    assert "below the minimum supported version" not in result2.output


from datetime import datetime, timezone
from unittest.mock import MagicMock

from enigma_pipe.core.manifest import BrainstemSegmentation


def test_fastsurfer_brainstem_seg_integration(tmp_path, monkeypatch):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    fs_license = tmp_path / "license.txt"
    fs_license.write_text("license")

    # Mock discover_cases to return 2 dummy cases
    class DummyCase:
        def __init__(self, id, path):
            self.id = id
            self.original_path = path

    mock_cases = [
        DummyCase("sub-01", input_dir / "sub-01"),
        DummyCase("sub-02", input_dir / "sub-02"),
    ]

    from enigma_pipe.cli.commands import fastsurfer

    monkeypatch.setattr(fastsurfer, "discover_cases", lambda *args, **kwargs: mock_cases)
    monkeypatch.setattr(
        "enigma_pipe.services.container.ContainerRunner._check_runtime", lambda self: None
    )
    monkeypatch.setattr(
        "enigma_pipe.services.fastsurfer.FastSurferRunner.check_version",
        lambda self: "FastSurfer v2.4.0",
    )

    # Mock FreeSurferChecker to avoid abort
    monkeypatch.setattr(
        "enigma_pipe.cli.commands.fastsurfer.FreeSurferChecker.check_availability", lambda: None
    )

    # Mock FastSurferRunner.run_case to succeed for sub-01 and fail for sub-02
    def mock_run_case(self, case_id, **kwargs):
        if case_id == "sub-01":
            return 0
        return 1

    monkeypatch.setattr("enigma_pipe.services.fastsurfer.FastSurferRunner.run_case", mock_run_case)

    # Mock run_brainstem_segmentation
    mock_run_brainstem = MagicMock()
    mock_run_brainstem.return_value = BrainstemSegmentation(
        status="SUCCESS", exit_code=0, started_at=datetime.now(timezone.utc), threads_used=1
    )
    monkeypatch.setattr(
        "enigma_pipe.cli.commands.fastsurfer.run_brainstem_segmentation", mock_run_brainstem
    )

    result = runner.invoke(
        app, ["fastsurfer", "--fs-license", str(fs_license), str(input_dir), str(out_dir)]
    )

    assert result.exit_code == 4
    assert "Discovered 2 cases" in result.output

    # sub-01 succeeded in FS, so brainstem seg should have been called
    # sub-02 failed in FS, so brainstem seg should NOT have been called
    assert mock_run_brainstem.call_count == 1
    mock_run_brainstem.assert_called_once_with(out_dir, "sub-01", None)


def _make_single_case_env(tmp_path, monkeypatch, run_case_retcode=0):
    """Helper: set up mocks for a single-case fastsurfer run."""
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    fs_license = tmp_path / "license.txt"
    fs_license.write_text("license")

    class DummyCase:
        def __init__(self, id, path):
            self.id = id
            self.original_path = path

    mock_cases = [DummyCase("sub-01", input_dir / "sub-01")]

    from enigma_pipe.cli.commands import fastsurfer as fs_cmd_module

    monkeypatch.setattr(fs_cmd_module, "discover_cases", lambda *a, **kw: mock_cases)
    monkeypatch.setattr(
        "enigma_pipe.services.container.ContainerRunner._check_runtime", lambda self: None
    )
    monkeypatch.setattr(
        "enigma_pipe.services.fastsurfer.FastSurferRunner.check_version",
        lambda self: "FastSurfer v2.4.0",
    )
    monkeypatch.setattr(
        "enigma_pipe.cli.commands.fastsurfer.FreeSurferChecker.check_availability", lambda: None
    )
    monkeypatch.setattr(
        "enigma_pipe.services.fastsurfer.FastSurferRunner.run_case",
        lambda self, case_id, **kwargs: run_case_retcode,
    )
    return input_dir, out_dir, fs_license


def test_fastsurfer_brainstem_seg_failure_exits_4(tmp_path, monkeypatch):
    """When segment_subregions fails (FAILED status), the CLI must exit 4 and record the case as FAILED."""
    input_dir, out_dir, fs_license = _make_single_case_env(
        tmp_path, monkeypatch, run_case_retcode=0
    )

    failed_brainstem = BrainstemSegmentation(
        status="FAILED",
        exit_code=1,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        threads_used=1,
        error_message="Process exited with code 1",
    )

    mock_run_brainstem = MagicMock(return_value=failed_brainstem)
    monkeypatch.setattr(
        "enigma_pipe.cli.commands.fastsurfer.run_brainstem_segmentation", mock_run_brainstem
    )

    result = runner.invoke(
        app, ["fastsurfer", "--fs-license", str(fs_license), str(input_dir), str(out_dir)]
    )

    assert result.exit_code == 4, (
        f"Expected exit 4, got {result.exit_code}. Output:\n{result.output}"
    )
    mock_run_brainstem.assert_called_once()


def test_fastsurfer_brainstem_seg_interrupted_exits_130(tmp_path, monkeypatch):
    """When segment_subregions is interrupted (INTERRUPTED status), the CLI must exit 130 immediately."""
    input_dir, out_dir, fs_license = _make_single_case_env(
        tmp_path, monkeypatch, run_case_retcode=0
    )

    interrupted_brainstem = BrainstemSegmentation(
        status="INTERRUPTED",
        exit_code=None,
        started_at=datetime.now(timezone.utc),
        finished_at=None,
        threads_used=1,
        error_message="KeyboardInterrupt",
    )

    mock_run_brainstem = MagicMock(return_value=interrupted_brainstem)
    monkeypatch.setattr(
        "enigma_pipe.cli.commands.fastsurfer.run_brainstem_segmentation", mock_run_brainstem
    )

    result = runner.invoke(
        app, ["fastsurfer", "--fs-license", str(fs_license), str(input_dir), str(out_dir)]
    )

    assert result.exit_code == 130, (
        f"Expected exit 130, got {result.exit_code}. Output:\n{result.output}"
    )
    mock_run_brainstem.assert_called_once()


def test_fastsurfer_hpc_backend_rejection(tmp_path):
    """When --backend hpc is specified, the CLI must exit 3 with an error message."""
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    fs_license = tmp_path / "license.txt"
    fs_license.write_text("license")

    result = runner.invoke(
        app,
        [
            "fastsurfer",
            "--fs-license",
            str(fs_license),
            "--backend",
            "hpc",
            str(input_dir),
            str(out_dir),
        ],
    )

    assert result.exit_code == 3
    assert "HPC scheduler submission is not yet implemented" in result.output


def test_fastsurfer_missing_dependency_error(tmp_path, monkeypatch):
    """When FastSurferRunner raises MissingDependencyError, the CLI must exit 3."""
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    fs_license = tmp_path / "license.txt"
    fs_license.write_text("license")

    from enigma_pipe.core.exceptions import MissingDependencyError

    monkeypatch.setattr(
        "enigma_pipe.cli.commands.fastsurfer.FreeSurferChecker.check_availability", lambda: None
    )

    def mock_init(self, *args, **kwargs):
        raise MissingDependencyError("Container engine docker is not available")

    monkeypatch.setattr("enigma_pipe.services.fastsurfer.FastSurferRunner.__init__", mock_init)

    result = runner.invoke(
        app, ["fastsurfer", "--fs-license", str(fs_license), str(input_dir), str(out_dir)]
    )

    assert result.exit_code == 3
    assert "Container engine docker is not available" in result.output


def test_fastsurfer_fastsurfer_run_interrupted(tmp_path, monkeypatch):
    """When KeyboardInterrupt is raised during FastSurfer run_case, the CLI must record INTERRUPTED manifest and exit 130."""
    input_dir, out_dir, fs_license = _make_single_case_env(
        tmp_path, monkeypatch, run_case_retcode=0
    )

    def mock_run_case_interrupt(self, case_id, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(
        "enigma_pipe.services.fastsurfer.FastSurferRunner.run_case", mock_run_case_interrupt
    )

    result = runner.invoke(
        app, ["fastsurfer", "--fs-license", str(fs_license), str(input_dir), str(out_dir)]
    )

    assert result.exit_code == 130
    from enigma_pipe.core.manifest import read_manifest

    manifest = read_manifest(out_dir, "sub-01", "fastsurfer")
    assert manifest is not None
    assert manifest.status.value == "interrupted"


def test_quickstart_validation_missing_dependency(tmp_path, monkeypatch):
    """Validation Scenario 2 from quickstart.md: Missing segment_subregions exits code 3."""
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    fs_license = tmp_path / "license.txt"
    fs_license.write_text("license")

    import shutil

    monkeypatch.setattr(
        shutil, "which", lambda cmd: None if cmd == "segment_subregions" else shutil.which(cmd)
    )

    result = runner.invoke(
        app, ["fastsurfer", "--fs-license", str(fs_license), str(input_dir), str(out_dir)]
    )

    assert result.exit_code == 3
    assert "segment_subregions not found on PATH" in result.output


@pytest.mark.smoke
@pytest.mark.skipif(
    not pytest.importorskip("shutil").which("segment_subregions"),
    reason="FreeSurfer segment_subregions not on PATH",
)
def test_quickstart_validation_smoke(tmp_path):
    """Validation Scenario 1 from quickstart.md: Happy path smoke test when FreeSurfer is installed."""
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    fs_license = tmp_path / "license.txt"
    fs_license.write_text("license")

    result = runner.invoke(
        app,
        [
            "fastsurfer",
            "--fs-license",
            str(fs_license),
            str(input_dir),
            str(out_dir),
            "--threads",
            "max",
        ],
    )
    # This will run if segment_subregions is available on PATH
    assert result.exit_code in (0, 4)
