import numpy as np
from PIL import Image
from scipy.ndimage import binary_erosion
from pathlib import Path
from typing import Dict, Tuple, List

def normalize_image(img: np.ndarray) -> np.ndarray:
    """Min-max normalize image to 0-255."""
    min_val = img.min()
    max_val = img.max()
    if max_val - min_val == 0:
        return np.zeros_like(img, dtype=np.uint8)
    norm = (img - min_val) / (max_val - min_val) * 255
    return norm.astype(np.uint8)

def apply_overlay(bg: np.ndarray, seg: np.ndarray, lut: Dict[int, Tuple[int, int, int]], alpha: float = 0.5) -> Image.Image:
    """Apply segmentation overlay with erosion and colors from LUT."""
    h, w = bg.shape
    out = np.zeros((h, w, 3), dtype=np.uint8)
    
    # Background as RGB
    for i in range(3):
        out[:,:,i] = bg
        
    unique_labels = np.unique(seg)
    unique_labels = unique_labels[unique_labels != 0] # exclude bg
    
    for label in unique_labels:
        if label not in lut:
            continue
            
        color = np.array(lut[label])
        mask = (seg == label)
        
        # 1-pixel erosion
        eroded = binary_erosion(mask, iterations=1)
        border = mask ^ eroded
        
        # Apply fill (alpha * 0.4 for fill, full alpha for border, as a heuristic)
        fill_alpha = alpha * 0.4
        border_alpha = alpha * 0.5
        
        for c in range(3):
            out[:,:,c] = np.where(eroded, out[:,:,c] * (1 - fill_alpha) + color[c] * fill_alpha, out[:,:,c])
            out[:,:,c] = np.where(border, out[:,:,c] * (1 - border_alpha) + color[c] * border_alpha, out[:,:,c])
            
    return Image.fromarray(out)

def generate_captures(t1_data: np.ndarray, seg_data: np.ndarray, output_dir: Path, 
                     case_id: str, lut: Dict[int, Tuple[int, int, int]], 
                     slices_per_plane: int = 8, fmt: str = "jpeg", alpha: float = 0.5) -> List[str]:
    """Generate and save PNG/JPEG captures."""
    bg_norm = normalize_image(t1_data)
    
    # Dynamic FOV
    coords = np.where(seg_data != 0)
    if len(coords[0]) == 0:
        return []
        
    min_x, max_x = coords[0].min(), coords[0].max()
    min_y, max_y = coords[1].min(), coords[1].max()
    min_z, max_z = coords[2].min(), coords[2].max()
    
    planes = [
        ("sagittal", 0, min_x, max_x),
        ("coronal", 1, min_y, max_y),
        ("axial", 2, min_z, max_z)
    ]
    
    generated_files = []
    
    for plane_name, axis, pmin, pmax in planes:
        # Sample evenly spaced slices
        if pmax <= pmin:
            continue
        step = max(1, (pmax - pmin) // (slices_per_plane + 1))
        indices = list(range(pmin + step, pmax, step))[:slices_per_plane]
        
        for idx, s in enumerate(indices):
            if axis == 0:
                bg_slice = bg_norm[s, :, :]
                seg_slice = seg_data[s, :, :]
            elif axis == 1:
                bg_slice = bg_norm[:, s, :]
                seg_slice = seg_data[:, s, :]
            else:
                bg_slice = bg_norm[:, :, s]
                seg_slice = seg_data[:, :, s]
                
            # Neurological orientation (rotate 90 degrees)
            bg_slice = np.rot90(bg_slice)
            seg_slice = np.rot90(seg_slice)
            
            img = apply_overlay(bg_slice, seg_slice, lut, alpha)
            
            # max longest side
            img.thumbnail((240, 240))
            
            filename = f"{plane_name}_{idx+1}.{fmt}"
            out_path = output_dir / case_id / filename
            img.save(out_path)
            generated_files.append(filename)
            
    return generated_files
