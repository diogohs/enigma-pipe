import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field

from neuroimage_cli.core.models import TerminalStatus
from neuroimage_cli.services.atomic import atomic_write

class BrainstemSegmentation(BaseModel):
    status: str
    exit_code: Optional[int] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    threads_used: int
    error_message: Optional[str] = None

class CompletionManifest(BaseModel):
    status: TerminalStatus
    case_id: str
    subcommand: str
    started_at: datetime
    finished_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    outputs: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    brainstem_segmentation: Optional[BrainstemSegmentation] = None

def write_manifest(output_dir: Path, case_id: str, subcommand: str, manifest: CompletionManifest) -> Path:
    """
    Write a completion manifest atomically.
    """
    manifest_path = output_dir / case_id / f"{subcommand}_manifest.json"
    
    with atomic_write(manifest_path) as f:
        json.dump(manifest.model_dump(mode='json'), f, indent=2)
        
    return manifest_path

def read_manifest(output_dir: Path, case_id: str, subcommand: str) -> Optional[CompletionManifest]:
    """
    Read a completion manifest if it exists.
    """
    manifest_path = output_dir / case_id / f"{subcommand}_manifest.json"
    if not manifest_path.exists():
        return None
        
    with open(manifest_path, 'r') as f:
        data = json.load(f)
        return CompletionManifest(**data)
