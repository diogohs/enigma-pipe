from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List
from pathlib import Path

from neuroimage_cli.core.models import ExecutionMode, SegmentationType
import getpass

def default_reviewer_id() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "unknown_reviewer"

class SlicerSettings(BaseModel):
    alpha: float = Field(default=0.5, ge=0.0, le=1.0)
    slices_per_plane: int = 8
    max_longest_side: int = 240
    format: str = "jpeg"
    orientation: str = "neurological"
    skip_empty: bool = True
    image_source: str = "mri/brainmask.mgz"
    model_config = ConfigDict(extra="forbid")

class AppSettings(BaseSettings):
    fs_license: Optional[Path] = None
    execution_mode: Optional[ExecutionMode] = None
    itksnap_path: Optional[Path] = None
    reviewer_id: str = Field(default_factory=default_reviewer_id)
    segmentation_to_eval: List[SegmentationType] = Field(
        default_factory=lambda: [SegmentationType.ASEG, SegmentationType.BRAINSTEM, SegmentationType.CEREBNET]
    )
    slicer: SlicerSettings = Field(default_factory=SlicerSettings)

    model_config = SettingsConfigDict(
        env_prefix="NEUROIMAGE_",
        env_nested_delimiter="__",
        extra="forbid"
    )

def load_settings(yaml_path: Optional[Path] = None) -> AppSettings:
    """Load settings from YAML file (if provided) and environment variables."""
    # In a full implementation, we'd parse the YAML file and pass it to the constructor.
    # For now, we rely on pydantic-settings to handle env vars and defaults.
    import yaml
    
    settings_dict = {}
    if yaml_path and yaml_path.exists():
        with open(yaml_path, 'r') as f:
            yaml_data = yaml.safe_load(f)
            if yaml_data:
                settings_dict.update(yaml_data)
                
    return AppSettings(**settings_dict)
