import json
import logging
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

console = Console(stderr=True)

logger = logging.getLogger("enigma_pipe")
logger.setLevel(logging.INFO)

console_handler = RichHandler(console=console, show_time=True, show_path=False, markup=True)
console_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(console_handler)


def setup_logging(output_dir: Path):
    """Set up file logging to output_dir/logs/enigma-pipe-YYYY-MM-DD-HHMMSS.log."""
    logs_dir = output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    log_file = logs_dir / f"enigma-pipe-{timestamp}.log"

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)


def print_error(msg: str):
    logger.error(msg)


def print_warning(msg: str):
    logger.warning(msg)


def print_info(msg: str):
    logger.info(msg)


def print_json_summary(
    command: str, total: int, succeeded: int, failed: int, skipped: int, exit_code: int, cases: list
):
    """Print the final JSON run summary to stdout."""
    summary = {
        "command": command,
        "total_cases": total,
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
        "interrupted": 0,  # Depending on logic
        "exit_code": exit_code,
        "cases": cases,
    }
    print(json.dumps(summary, indent=2))
