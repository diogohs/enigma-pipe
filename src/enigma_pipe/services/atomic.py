import os
import tempfile
import shutil
from pathlib import Path
from contextlib import contextmanager

@contextmanager
def atomic_write(file_path: Path, mode: str = 'w', encoding: str = 'utf-8'):
    """
    Context manager for atomic file writing.
    Writes to a temporary file in the same directory and renames it on success.
    """
    file_path = Path(file_path)
    parent_dir = file_path.parent
    parent_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a temporary file in the same directory
    fd, temp_path_str = tempfile.mkstemp(dir=parent_dir, prefix=f".{file_path.name}.tmp")
    temp_path = Path(temp_path_str)
    
    try:
        if 'b' in mode:
            with os.fdopen(fd, mode) as f:
                yield f
        else:
            with os.fdopen(fd, mode, encoding=encoding) as f:
                yield f
                
        # Atomic rename (replace existing if needed)
        os.replace(temp_path, file_path)
    except Exception:
        # Clean up temporary file on failure
        if temp_path.exists():
            os.remove(temp_path)
        raise
