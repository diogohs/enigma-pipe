import json

from rich.console import Console

console = Console(stderr=True)


def print_error(msg: str):
    console.print(f"[bold red]Error:[/bold red] {msg}")


def print_warning(msg: str):
    console.print(f"[bold yellow]Warning:[/bold yellow] {msg}")


def print_info(msg: str):
    console.print(f"[bold blue]Info:[/bold blue] {msg}")


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
