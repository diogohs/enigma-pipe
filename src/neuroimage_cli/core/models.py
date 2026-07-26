from enum import Enum
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

class ExecutionMode(str, Enum):
    DOCKER = "docker"
    SINGULARITY = "singularity"
    APPTAINER = "apptainer"

class ProcessingMode(str, Enum):
    ALL = "all"
    CONTINUE = "continue"
    FILE = "file"

class ExistingOutputPolicy(str, Enum):
    ERROR = "error"
    SKIP = "skip"
    RESUME = "resume"
    REPLACE = "replace"

class TerminalStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    SKIPPED = "skipped"

class SegmentationType(str, Enum):
    ASEG = "aseg"
    BRAINSTEM = "brainstem"
    CEREBNET = "cerebnet"
    ENIGMA_SC = "enigma-sc"

@dataclass
class CaseIdentifier:
    """Stable identifier for a case."""
    id: str
    original_path: Path
    
@dataclass
class CaseOutcome:
    """The terminal outcome of a case processing."""
    case_id: str
    status: TerminalStatus
    error_message: Optional[str] = None
