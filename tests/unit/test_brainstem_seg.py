import os
import shutil
import subprocess
import pytest
from unittest.mock import patch, mock_open, MagicMock

from enigma_pipe.services.brainstem_seg import FreeSurferChecker

def test_check_availability_missing_executable(capsys):
    with patch("shutil.which", return_value=None):
        with pytest.raises(SystemExit) as exc_info:
            FreeSurferChecker.check_availability()
        
        assert exc_info.value.code == 3
        captured = capsys.readouterr()
        assert "segment_subregions" in captured.err
        assert "not found on PATH" in captured.err

def test_check_availability_not_executable(capsys):
    with patch("shutil.which", return_value="/fake/bin/segment_subregions"):
        with patch("os.access", return_value=False):
            with patch("os.path.exists", return_value=True):
                with pytest.raises(SystemExit) as exc_info:
                    FreeSurferChecker.check_availability()
                
                assert exc_info.value.code == 3
                captured = capsys.readouterr()
                assert "not executable" in captured.err
                assert "/fake/bin/segment_subregions" in captured.err

def test_check_availability_warns_on_old_version(capsys):
    # Mocking os environ and build-stamp.txt reading to simulate FreeSurfer < 7.3
    mock_env = {"FREESURFER_HOME": "/fake/fs"}
    mock_stamp = "freesurfer-linux-centos7_x86_64-7.2.0-20210720-a92bd03\n"
    
    with patch("shutil.which", return_value="/fake/bin/segment_subregions"):
        with patch("os.access", return_value=True):
            with patch("os.path.exists", return_value=True):
                with patch.dict(os.environ, mock_env):
                    with patch("builtins.open", mock_open(read_data=mock_stamp)):
                        FreeSurferChecker.check_availability()
                        
                        captured = capsys.readouterr()
                        assert "WARNING" in captured.err
                        assert "7.3" in captured.err

def test_check_availability_success_on_new_version(capsys):
    mock_env = {"FREESURFER_HOME": "/fake/fs"}
    mock_stamp = "freesurfer-linux-centos7_x86_64-7.3.2-20220804-d4b96f4\n"
    
    with patch("shutil.which", return_value="/fake/bin/segment_subregions"):
        with patch("os.access", return_value=True):
            with patch("os.path.exists", return_value=True):
                with patch.dict(os.environ, mock_env):
                    with patch("builtins.open", mock_open(read_data=mock_stamp)):
                        FreeSurferChecker.check_availability()
                        
                        captured = capsys.readouterr()
                        assert "WARNING" not in captured.err

def test_check_availability_warns_fallback_recon_all(capsys):
    with patch("shutil.which", return_value="/fake/bin/segment_subregions"):
        with patch("os.access", return_value=True):
            with patch("os.path.exists", return_value=True):
                with patch.dict(os.environ, {}, clear=True):
                    # No FREESURFER_HOME, fallback to recon-all --version
                    with patch("subprocess.run") as mock_run:
                        mock_run.return_value = MagicMock(
                            returncode=0,
                            stdout="freesurfer-linux-centos7_x86_64-7.1.1-20201211-1234567\n"
                        )
                        FreeSurferChecker.check_availability()
                        
                        captured = capsys.readouterr()
                        assert "WARNING" in captured.err

def test_check_availability_no_warning_if_unparseable(capsys):
    with patch("shutil.which", return_value="/fake/bin/segment_subregions"):
        with patch("os.access", return_value=True):
            with patch("os.path.exists", return_value=True):
                with patch.dict(os.environ, {}, clear=True):
                    with patch("subprocess.run") as mock_run:
                        mock_run.return_value = MagicMock(returncode=1, stdout="")
                        FreeSurferChecker.check_availability()
                        
                        captured = capsys.readouterr()
                        assert "WARNING" not in captured.err
from enigma_pipe.services.brainstem_seg import compute_threads

def test_compute_threads_default():
    assert compute_threads(None) == 1

def test_compute_threads_explicit():
    assert compute_threads("4") == 4
    assert compute_threads("1") == 1

def test_compute_threads_max_with_affinity():
    with patch("os.sched_getaffinity", return_value={0, 1, 2, 3, 4, 5, 6, 7}, create=True):
        assert compute_threads("max") == 4

def test_compute_threads_max_without_affinity():
    # Simulate os without sched_getaffinity (like Windows/macOS)
    with patch("os.cpu_count", return_value=12):
        with patch("builtins.hasattr", side_effect=lambda obj, name: False if name == "sched_getaffinity" else hasattr(obj, name)):
            assert compute_threads("max") == 6

def test_compute_threads_max_fallback_minimum():
    with patch("os.cpu_count", return_value=1):
        with patch("builtins.hasattr", side_effect=lambda obj, name: False if name == "sched_getaffinity" else hasattr(obj, name)):
            assert compute_threads("max") == 1
from enigma_pipe.services.brainstem_seg import run_brainstem_segmentation
from pathlib import Path
from datetime import datetime, timezone

def test_run_brainstem_segmentation_success(capsys):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        
        result = run_brainstem_segmentation(Path("/out"), "sub-01", "4")
        
        captured = capsys.readouterr()
        assert f"segment_subregions brainstem --cross sub-01 --sd {Path('/out')}" in captured.err
        assert result.status == "SUCCESS"
        assert result.exit_code == 0
        assert result.threads_used == 4
        assert result.error_message is None

def test_run_brainstem_segmentation_interrupted(capsys):
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = KeyboardInterrupt()
        
        result = run_brainstem_segmentation(Path("/out"), "sub-01", "2")
        
        assert result.status == "INTERRUPTED"
        assert result.exit_code is None
        assert result.finished_at is None
        assert result.threads_used == 2
        assert "KeyboardInterrupt" in result.error_message

def test_run_brainstem_segmentation_failure(capsys):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=4)
        
        result = run_brainstem_segmentation(Path("/out"), "sub-01", "max")
        
        assert result.status == "FAILED"
        assert result.exit_code == 4
        assert result.error_message == "Process exited with code 4"
