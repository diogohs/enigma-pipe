from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from enigma_pipe.cli.main import app
from enigma_pipe.core.manifest import read_manifest
from enigma_pipe.core.models import CaseOutcome, TerminalStatus

runner = CliRunner()


@pytest.fixture
def mock_brainstem_segmentation():
    with patch("enigma_pipe.cli.commands.brainstem.run_brainstem_segmentation") as mock_run:
        mock_result = CaseOutcome(
            case_id="case-01",
            status=TerminalStatus.SUCCESS,
        )
        mock_run.return_value = mock_result
        yield mock_run


@pytest.fixture
def mock_discover_fs_cases(tmp_path):
    with patch("enigma_pipe.cli.commands.brainstem.discover_fs_cases") as mock_discover:
        class DummyCase:
            def __init__(self, id, path):
                self.id = id
                self.original_path = path

        class DummyList(list):
            pass

        # By default, pretend we found one case called "case-01"
        case_path = tmp_path / "in" / "case-01"
        lst = DummyList([DummyCase("case-01", case_path)])
        lst.total_found = 1
        lst.skipped_count = 0
        mock_discover.return_value = lst
        yield mock_discover


def setup_case_dir(input_dir, case_id="case-01"):
    # Setup valid mock FS output
    case_dir = input_dir / case_id
    mri_dir = case_dir / "mri"
    mri_dir.mkdir(parents=True, exist_ok=True)
    (mri_dir / "norm.mgz").touch()
    (mri_dir / "nu.mgz").touch()
    (mri_dir / "aseg.mgz").touch()
    return input_dir


def test_brainstem_command_happy_path(tmp_path, mock_brainstem_segmentation, mock_discover_fs_cases):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    setup_case_dir(input_dir)

    with patch("enigma_pipe.cli.commands.brainstem.FreeSurferChecker.check_availability"):
        result = runner.invoke(app, ["brainstem", str(input_dir)])

    assert result.exit_code == 0
    mock_brainstem_segmentation.assert_called_once()
    args, _ = mock_brainstem_segmentation.call_args
    assert args[0] == input_dir  # output_dir
    assert args[1] == "case-01" # case_id
    assert args[2] is None     # threads

    manifest = read_manifest(input_dir, "case-01", "brainstem")
    assert manifest is not None
    assert manifest.status == TerminalStatus.SUCCESS
    assert manifest.subcommand == "brainstem"


def test_brainstem_command_with_threads(tmp_path, mock_brainstem_segmentation, mock_discover_fs_cases):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    setup_case_dir(input_dir)

    with patch("enigma_pipe.cli.commands.brainstem.FreeSurferChecker.check_availability"):
        result = runner.invoke(app, ["brainstem", str(input_dir), "--threads", "4"])

    assert result.exit_code == 0
    mock_brainstem_segmentation.assert_called_once()
    args, _ = mock_brainstem_segmentation.call_args
    assert args[2] == 4


def test_brainstem_command_invalid_threads(tmp_path):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    result = runner.invoke(app, ["brainstem", str(input_dir), "--threads", "abc"])
    assert result.exit_code == 2
    assert "Invalid --threads value" in result.output


def test_brainstem_command_args_passed_to_discover(tmp_path, mock_brainstem_segmentation, mock_discover_fs_cases):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    setup_case_dir(input_dir)

    with patch("enigma_pipe.cli.commands.brainstem.FreeSurferChecker.check_availability"):
        result = runner.invoke(
            app, 
            ["brainstem", str(input_dir), "--processing-mode", "continue", "--existing-output", "skip"]
        )

    assert result.exit_code == 0
    mock_discover_fs_cases.assert_called_once()
    args, _ = mock_discover_fs_cases.call_args
    assert args[1].value == "continue"  # processing_mode
    assert args[2].value == "skip"      # existing_output


def test_brainstem_command_invalid_directory(tmp_path, mock_discover_fs_cases, mock_brainstem_segmentation):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    # Do NOT set up the required files inside input_dir/case-01
    (input_dir / "case-01").mkdir()

    with patch("enigma_pipe.cli.commands.brainstem.FreeSurferChecker.check_availability"):
        result = runner.invoke(app, ["brainstem", str(input_dir)])

    assert result.exit_code == 4  # Validation failed during processing loop
    assert "Invalid FastSurfer output directory" in result.output
    mock_brainstem_segmentation.assert_not_called()
    
    manifest = read_manifest(input_dir, "case-01", "brainstem")
    assert manifest is not None
    assert manifest.status == TerminalStatus.FAILED


def test_brainstem_command_failed(tmp_path, mock_brainstem_segmentation, mock_discover_fs_cases):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    setup_case_dir(input_dir)

    # Modify mock to return FAILED
    mock_brainstem_segmentation.return_value.status = TerminalStatus.FAILED
    mock_brainstem_segmentation.return_value.error_message = "Mocked failure"

    with patch("enigma_pipe.cli.commands.brainstem.FreeSurferChecker.check_availability"):
        result = runner.invoke(app, ["brainstem", str(input_dir)])

    assert result.exit_code == 4
    assert "Mocked failure" in result.output


def test_brainstem_command_interrupted(tmp_path, mock_brainstem_segmentation, mock_discover_fs_cases):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    setup_case_dir(input_dir)

    # Modify mock to return INTERRUPTED
    mock_brainstem_segmentation.return_value.status = TerminalStatus.INTERRUPTED

    with patch("enigma_pipe.cli.commands.brainstem.FreeSurferChecker.check_availability"):
        result = runner.invoke(app, ["brainstem", str(input_dir)])

    assert result.exit_code == 130
    assert "interrupted" in result.output
