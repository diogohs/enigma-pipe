import pytest
from typer.testing import CliRunner
from neuroimage_cli.cli.main import app

runner = CliRunner()

def test_qc_img_invalid_rating(tmp_path):
    pass
