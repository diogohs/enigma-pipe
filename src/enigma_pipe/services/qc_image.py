import csv
from datetime import datetime, timezone
from pathlib import Path

from enigma_pipe.services.atomic import atomic_write


def write_image_qc_csv(
    output_dir: Path,
    case_id: str,
    image_path: Path,
    rating: int,
    reviewer_id: str,
    comment: str | None = None,
):
    """Write the Image QC CSV file for a case."""
    csv_path = output_dir / case_id / "qc_image.csv"

    with atomic_write(csv_path) as f:
        writer = csv.writer(f)
        writer.writerow(
            ["filename", "image_path", "quality_score", "comments", "reviewed_at", "reviewer_id"]
        )
        writer.writerow(
            [
                image_path.name,
                str(image_path.absolute()),
                str(rating),
                comment or "",
                datetime.now(timezone.utc).isoformat(),
                reviewer_id,
            ]
        )
    return csv_path
