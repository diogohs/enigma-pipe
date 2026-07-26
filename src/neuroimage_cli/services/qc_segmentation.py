import csv
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from neuroimage_cli.services.atomic import atomic_write
from neuroimage_cli.core.models import SegmentationType

def write_segmentation_qc_csv(
    output_dir: Path, 
    case_id: str, 
    image_path: Path, 
    segmentation_path: Path, 
    seg_type: SegmentationType, 
    rating: int, 
    reviewer_id: str,
    fastsurfer_version: str = "",
    comment: Optional[str] = None
):
    """Write the Segmentation QC CSV file for a specific segmentation type."""
    csv_path = output_dir / case_id / f"{case_id}__{seg_type.value}__qc.csv"
    
    with atomic_write(csv_path) as f:
        writer = csv.writer(f)
        writer.writerow([
            "image_filename", "image_path", "segmentation_filename", 
            "segmentation_path", "segmentation_type", "quality_score", 
            "comments", "fastsurfer_version", "reviewed_at", "reviewer_id"
        ])
        writer.writerow([
            image_path.name,
            str(image_path.absolute()),
            segmentation_path.name,
            str(segmentation_path.absolute()),
            seg_type.value,
            str(rating),
            comment or "",
            fastsurfer_version,
            datetime.now(timezone.utc).isoformat(),
            reviewer_id
        ])
    return csv_path
