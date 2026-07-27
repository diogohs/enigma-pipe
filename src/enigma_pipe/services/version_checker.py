import re
from enum import Enum
from typing import Tuple
from enigma_pipe.core.constants import MIN_FASTSURFER_VERSION

class VersionCheckResult(Enum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNPARSEABLE = "UNPARSEABLE"
    SKIPPED = "SKIPPED"

def check_fastsurfer_version(version_str: str) -> Tuple[VersionCheckResult, str]:
    """
    Parse a FastSurfer version string and compare it against the minimum supported version.
    Returns a tuple of (VersionCheckResult, extracted_version_or_error)
    """
    if not version_str or version_str == "unknown":
        return VersionCheckResult.UNPARSEABLE, "could not verify"
        
    match = re.search(r"v?(\d+)\.(\d+)\.(\d+)", version_str)
    if not match:
        return VersionCheckResult.UNPARSEABLE, "could not verify"
        
    detected_tuple = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    extracted_version = f"{match.group(1)}.{match.group(2)}.{match.group(3)}"
    
    if detected_tuple >= MIN_FASTSURFER_VERSION:
        return VersionCheckResult.SUPPORTED, extracted_version
    else:
        return VersionCheckResult.UNSUPPORTED, extracted_version
