import base64
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import binary_erosion


def normalize_image(img: np.ndarray) -> np.ndarray:
    """Min-max normalize image to 0-255."""
    min_val = img.min()
    max_val = img.max()
    if max_val - min_val == 0:
        return np.zeros_like(img, dtype=np.uint8)
    norm = (img - min_val) / (max_val - min_val) * 255
    return norm.astype(np.uint8)


def apply_overlay(
    bg: np.ndarray, seg: np.ndarray, lut: dict[int, tuple[int, int, int]], alpha: float = 0.5
) -> Image.Image:
    """Apply segmentation overlay with erosion and colors from LUT."""
    import colorsys
    h, w = bg.shape
    out = np.zeros((h, w, 3), dtype=np.uint8)

    # Background as RGB
    for i in range(3):
        out[:, :, i] = bg

    unique_labels = np.unique(seg)
    unique_labels = unique_labels[unique_labels != 0]  # exclude bg

    for idx, label in enumerate(unique_labels):
        if not lut:
            hue = (idx * 137.508) % 360 / 360.0
            r, g, b = colorsys.hls_to_rgb(hue, 0.6, 0.9)
            color = np.array([int(r*255), int(g*255), int(b*255)])
        else:
            if label not in lut:
                continue
            color = np.array(lut[label])

        mask = seg == label

        # 1-pixel erosion
        eroded = binary_erosion(mask, iterations=1)
        border = mask ^ eroded

        # Apply fill (alpha * 0.4 for fill, full alpha for border, as a heuristic)
        fill_alpha = alpha * 0.4
        border_alpha = alpha * 0.5

        for c in range(3):
            out[:, :, c] = np.where(
                eroded, out[:, :, c] * (1 - fill_alpha) + color[c] * fill_alpha, out[:, :, c]
            )
            out[:, :, c] = np.where(
                border, out[:, :, c] * (1 - border_alpha) + color[c] * border_alpha, out[:, :, c]
            )

    return Image.fromarray(out)


def generate_captures(
    t1_data: np.ndarray,
    seg_data: np.ndarray,
    output_dir: Path,
    case_id: str,
    seg_type_name: str,
    lut: dict[int, tuple[int, int, int]],
    skip_level: int = 1,
    padding: int = 10,
    skip_empty: bool = True,
    fmt: str = "jpeg",
    alpha: float = 0.5,
    max_longest_side: int = 240,
    neurological_orientation: bool = True,
) -> list[str]:
    """Generate and save PNG/JPEG captures and SVG matrices."""
    bg_norm = normalize_image(t1_data)

    # Dynamic FOV
    coords = np.where(seg_data != 0)
    if len(coords[0]) == 0:
        return []

    dim_x, dim_y, dim_z = t1_data.shape

    min_x = max(0, coords[0].min() - padding)
    max_x = min(dim_x, coords[0].max() + padding + 1)
    min_y = max(0, coords[1].min() - padding)
    max_y = min(dim_y, coords[1].max() + padding + 1)
    min_z = max(0, coords[2].min() - padding)
    max_z = min(dim_z, coords[2].max() + padding + 1)

    planes = [
        ("sagittal", 0, min_x, max_x),
        ("coronal", 1, min_y, max_y),
        ("axial", 2, min_z, max_z),
    ]

    generated_files = []
    
    step = 1 if skip_level == 0 else max(1, skip_level)

    for plane_name, axis, pmin, pmax in planes:
        # Sample slices based on skip_level
        if pmax <= pmin:
            continue
        
        indices = list(range(pmin, pmax, step))
        plane_images = []

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

            if skip_empty and not np.any(seg_slice) and not np.any(bg_slice):
                continue

            if neurological_orientation:
                # Neurological orientation (rotate 90 degrees)
                bg_slice = np.rot90(bg_slice)
                seg_slice = np.rot90(seg_slice)

            img = apply_overlay(bg_slice, seg_slice, lut, alpha)

            if max_longest_side > 0:
                img.thumbnail((max_longest_side, max_longest_side))

            filename = f"{plane_name}_{s}.{fmt}"
            if seg_type_name:
                out_path = output_dir / case_id / seg_type_name / filename
                rel_path = f"{seg_type_name}/{filename}"
            else:
                out_path = output_dir / case_id / filename
                rel_path = filename
                
            img.save(out_path)
            plane_images.append((img, s))
            generated_files.append(rel_path)

        if plane_images:
            svg_filename = f"{plane_name}.svg"
            if seg_type_name:
                svg_out_path = output_dir / case_id / seg_type_name / svg_filename
                rel_svg_path = f"{seg_type_name}/{svg_filename}"
            else:
                svg_out_path = output_dir / case_id / svg_filename
                rel_svg_path = svg_filename
                
            N = len(plane_images)
            ncols = min(10, int(np.ceil(np.sqrt(N))))
            if ncols == 0:
                ncols = 1
            nrows = int(np.ceil(N / ncols))
            
            img_w, img_h = plane_images[0][0].size
            grid_w = ncols * img_w
            grid_h = nrows * img_h
            
            svg_content = [
                f'<svg width="{grid_w}" height="{grid_h}" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
            ]
            
            for i, (p_img, p_idx) in enumerate(plane_images):
                row = i // ncols
                col = i % ncols
                x = col * img_w
                y = row * img_h
                
                buffered = BytesIO()
                p_img.save(buffered, format=fmt.upper() if fmt.lower() != "jpg" else "JPEG")
                img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
                b64 = f"data:image/{fmt.lower()};base64,{img_str}"
                
                svg_content.append(f'  <g transform="translate({x}, {y})">')
                svg_content.append(f'    <image href="{b64}" width="{img_w}" height="{img_h}" />')
                svg_content.append(f'    <rect x="{x}" y="{y}" width="60" height="25" fill="black" fill-opacity="0.5"/>')
                svg_content.append(f'    <text x="5" y="18" fill="white" font-size="14" font-family="sans-serif">Slice {p_idx}</text>')
                svg_content.append('  </g>')
            
            svg_content.append('</svg>')
            svg_out_path.write_text("\n".join(svg_content), encoding="utf-8")
            generated_files.append(rel_svg_path)

    return generated_files
