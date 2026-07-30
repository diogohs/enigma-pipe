import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from enigma_pipe.core.models import TerminalStatus
from enigma_pipe.services.atomic import atomic_write


class CompletionManifest(BaseModel):
    status: TerminalStatus
    case_id: str
    subcommand: str
    started_at: datetime
    finished_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    outputs: list[str] = Field(default_factory=list)
    error_message: str | None = None


def write_manifest(
    output_dir: Path, case_id: str, subcommand: str, manifest: CompletionManifest
) -> Path:
    """
    Write a completion manifest atomically.
    """
    manifest_path = output_dir / case_id / f"{subcommand}_manifest.json"

    with atomic_write(manifest_path) as f:
        json.dump(manifest.model_dump(mode="json"), f, indent=2)

    return manifest_path


def read_manifest(output_dir: Path, case_id: str, subcommand: str) -> CompletionManifest | None:
    """
    Read a completion manifest if it exists.
    """
    manifest_path = output_dir / case_id / f"{subcommand}_manifest.json"
    if not manifest_path.exists():
        return None

    with open(manifest_path, "r") as f:
        data = json.load(f)
        return CompletionManifest(**data)
