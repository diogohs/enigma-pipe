import typer
from typing import Optional
from pathlib import Path

app = typer.Typer(
    name="enigma-pipe",
    help="Enigma Pipe CLI",
    no_args_is_help=True
)

# State object to hold global config
class GlobalState:
    verbose: bool = False
    debug: bool = False
    json_output: bool = False
    settings_path: Optional[Path] = None
    
state = GlobalState()

@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
    debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug output"),
    json_output: bool = typer.Option(False, "--json", help="Output final summary in JSON format"),
    settings: Optional[Path] = typer.Option(None, "--settings", "-s", help="Path to YAML settings file")
):
    state.verbose = verbose
    state.debug = debug
    state.json_output = json_output
    state.settings_path = settings

# Import commands to register them with the Typer app
import enigma_pipe.cli.commands.fastsurfer
import enigma_pipe.cli.commands.qc_img
import enigma_pipe.cli.commands.qc_seg
import enigma_pipe.cli.commands.mriqc
import enigma_pipe.cli.commands.slicer

if __name__ == "__main__":
    app()

