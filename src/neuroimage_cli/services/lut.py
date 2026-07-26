from pathlib import Path
from typing import Dict, Tuple
import re

def parse_freesurfer_lut(lut_path: Path) -> Dict[int, Tuple[int, int, int]]:
    """
    Parse a FreeSurfer-style color lookup table (LUT).
    Returns a dictionary mapping integer label IDs to (R, G, B) tuples.
    """
    lut = {}
    if not lut_path.exists():
        return lut
        
    with open(lut_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            parts = line.split()
            if len(parts) >= 5:
                try:
                    label_id = int(parts[0])
                    r = int(parts[2])
                    g = int(parts[3])
                    b = int(parts[4])
                    lut[label_id] = (r, g, b)
                except ValueError:
                    continue
                    
    return lut
