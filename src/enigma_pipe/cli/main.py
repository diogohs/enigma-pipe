from pathlib import Path

import typer

app = typer.Typer(name="enigma-pipe", help="Enigma Pipe CLI", no_args_is_help=True)


# State object to hold global config
class GlobalState:
    verbose: bool = False
    debug: bool = False
    json_output: bool = False
    settings_path: Path | None = None


state = GlobalState()


def version_callback(value: bool) -> None:
    if value:
        import enigma_pipe

        typer.echo(f"enigma-pipe {enigma_pipe.__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool | None = typer.Option(
        None,
        "--version",
        "-V",
        help="Show version and exit",
        callback=version_callback,
        is_eager=True,
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
    debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug output"),
    json_output: bool = typer.Option(False, "--json", help="Output final summary in JSON format"),
    settings: Path | None = typer.Option(
        None, "--settings", "-s", help="Path to YAML settings file"
    ),
) -> None:
    state.verbose = verbose
    state.debug = debug
    state.json_output = json_output
    state.settings_path = settings


# Import commands to register them with the Typer app
from enigma_pipe.cli.commands import (  # noqa: F401
    brainstem,
    enigma_sc,
    fastsurfer,
    mriqc,
    qc_img,
    qc_seg,
    slicer,
)

if __name__ == "__main__":
    app()
