from pathlib import Path

import ants
import numpy as np


def register_to_mni(moving_path: Path, fixed_template_path: Path) -> str:
    """
    Perform rigid registration (6 DOF) of moving image to fixed template.
    Returns the path to the temporary transform file.
    """
    moving = ants.image_read(str(moving_path))
    fixed = ants.image_read(str(fixed_template_path))

    # Rigid registration
    reg = ants.registration(fixed=fixed, moving=moving, type_of_transform="Rigid")

    # Return the forward transform path
    return reg["fwdtransforms"][0]


def apply_transform(
    image_path: Path, transform_path: str, reference_path: Path, is_labels: bool = False
) -> np.ndarray:
    """
    Apply transform to an image (or segmentation) and return the resulting numpy array.
    """
    img = ants.image_read(str(image_path))
    ref = ants.image_read(str(reference_path))

    interp = "nearestNeighbor" if is_labels else "linear"

    warped = ants.apply_transforms(
        fixed=ref, moving=img, transformlist=[transform_path], interpolator=interp
    )

    return warped.numpy()
