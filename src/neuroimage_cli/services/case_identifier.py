import re
from pathlib import Path

def derive_case_id(file_path: Path) -> str:
    """
    Derive a stable case identifier from a file path.
    Strips .nii.gz or .nii extensions, replaces unsupported characters with underscores,
    preserves BIDS naming entities. Uses only the filename.
    """
    name = file_path.name
    
    # Strip extensions
    if name.endswith('.nii.gz'):
        name = name[:-7]
    elif name.endswith('.nii'):
        name = name[:-4]
    elif name.endswith('.mgz'):
        name = name[:-4]
        
    # Replace unsupported characters with underscores (allow alphanumeric, dashes, and underscores)
    name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    
    return name
