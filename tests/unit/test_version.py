from typer.testing import CliRunner

import enigma_pipe
from enigma_pipe.cli.main import app

runner = CliRunner()


def test_package_version() -> None:
    assert enigma_pipe.__version__ == "0.2.0"


def test_cli_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "enigma-pipe 0.2.0" in result.stdout

    result_short = runner.invoke(app, ["-V"])
    assert result_short.exit_code == 0
    assert "enigma-pipe 0.2.0" in result_short.stdout
