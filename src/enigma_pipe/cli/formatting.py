import sys
import json
from datetime import datetime
from pathlib import Path
from loguru import logger

logger.remove()
logger.add(
    lambda msg: sys.stderr.write(msg), 
    colorize=True, 
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>", 
    level="INFO"
)


def setup_logging(output_dir: Path):
    """Set up file logging to output_dir/logs/enigma-pipe-YYYY-MM-DD-HHMMSS.log."""
    logs_dir = output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    log_file = logs_dir / f"enigma-pipe-{timestamp}.log"

    logger.add(
        log_file, 
        format="{time:YYYY-MM-DD HH:mm:ss} - {level} - {message}", 
        level="INFO"
    )


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
