import pytest
from typer.testing import CliRunner
from enigma_pipe.cli.main import app

runner = CliRunner()

def test_mriqc_invalid_bids_dir(tmp_path):
    result = runner.invoke(app, ["mriqc", str(tmp_path / "nonexistent"), str(tmp_path / "out")])
    assert result.exit_code != 0
