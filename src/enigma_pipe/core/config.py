import getpass
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from enigma_pipe.core.models import ExecutionMode, SegmentationType


def default_reviewer_id() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "unknown_reviewer"


class AppSettings(BaseSettings):
    fs_license: Path | None = None
    execution_mode: ExecutionMode | None = None
    itksnap_path: Path | None = None
    reviewer_id: str = Field(default_factory=default_reviewer_id)
    segmentation_to_eval: list[SegmentationType] = Field(
        default_factory=lambda: [
            SegmentationType.ASEG,
            SegmentationType.BRAINSTEM,
            SegmentationType.CEREBNET,
        ]
    )

    model_config = SettingsConfigDict(
        env_prefix="ENIGMA_PIPE_", env_nested_delimiter="__", extra="forbid"
    )


def load_settings(yaml_path: Path | None = None) -> AppSettings:
    """Load settings from YAML file (if provided) and environment variables."""
    # In a full implementation, we'd parse the YAML file and pass it to the constructor.
    # For now, we rely on pydantic-settings to handle env vars and defaults.
    import yaml

    settings_dict = {}
    if yaml_path and yaml_path.exists():
        with open(yaml_path, "r") as f:
            yaml_data = yaml.safe_load(f)
            if yaml_data:
                settings_dict.update(yaml_data)

    return AppSettings(**settings_dict)
