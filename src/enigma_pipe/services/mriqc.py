from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from enigma_pipe.cli.formatting import print_info, print_warning
from enigma_pipe.core.exceptions import MissingDependencyError
from enigma_pipe.core.models import ExecutionMode
from enigma_pipe.services.container import ContainerRunner


_NIFTI_SUFFIXES = (".nii", ".nii.gz")
_GENERATED_BIDS_MARKER = ".enigma_pipe_generated_bids"
_EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    "__pycache__",
    "code",
    "derivatives",
    "sourcedata",
}


class MRIQCRunner(ContainerRunner):
    """Run MRIQC and prepare a minimal BIDS dataset when necessary.

    Existing BIDS datasets are used directly. If ``bids_dir`` contains loose
    NIfTI files instead, a minimal BIDS dataset is generated automatically
    before MRIQC is started.

    For Docker, the default image is ``nipreps/mriqc:latest``. For Singularity
    or Apptainer, the default is ``~/containers/mriqc_latest.sif``. A custom
    image can be supplied to the constructor or through the environment
    variable ``ENIGMA_PIPE_MRIQC_IMAGE``.
    """

    def __init__(
        self,
        mode: ExecutionMode,
        image: str | None = None,
    ):
        configured_image = image or os.environ.get("ENIGMA_PIPE_MRIQC_IMAGE")

        if configured_image is None:
            if mode == ExecutionMode.DOCKER:
                configured_image = "nipreps/mriqc:latest"
            else:
                configured_image = str(
                    Path.home() / "enigma-pipe" / "images" / "mriqc.sif"
                )

        configured_image = os.path.expandvars(
            os.path.expanduser(configured_image)
        )

        super().__init__(mode, configured_image)

        if self.mode in (
            ExecutionMode.SINGULARITY,
            ExecutionMode.APPTAINER,
        ):
            # URI images such as docker://nipreps/mriqc:latest are accepted.
            # Plain local image paths must exist before execution.
            if "://" not in self.image:
                image_path = Path(self.image)
                if not image_path.is_file():
                    raise MissingDependencyError(
                        "MRIQC Singularity/Apptainer image not found: "
                        f"{image_path}. Create it with:\n"
                        f'  mkdir -p "{image_path.parent}"\n'
                        f"  singularity pull --force "
                        f'"{image_path}" '
                        "docker://nipreps/mriqc:latest\n"
                        "Alternatively, set ENIGMA_PIPE_MRIQC_IMAGE to "
                        "another .sif image or pass --image-sif."
                    )
                self.image = str(image_path.resolve())

    def _entrypoint(self) -> list[str]:
        """Return the executable required by the selected runtime."""
        if self.mode == ExecutionMode.DOCKER:
            # The Docker image already defines MRIQC as its entrypoint.
            return []

        # ContainerRunner uses ``singularity/apptainer exec``, so the
        # executable must be stated explicitly.
        return ["mriqc"]

    @staticmethod
    def _is_nifti(path: Path) -> bool:
        name = path.name.lower()
        return name.endswith(_NIFTI_SUFFIXES)

    @staticmethod
    def _strip_nifti_suffix(filename: str) -> str:
        lower_name = filename.lower()
        if lower_name.endswith(".nii.gz"):
            return filename[:-7]
        if lower_name.endswith(".nii"):
            return filename[:-4]
        return Path(filename).stem

    @staticmethod
    def _sanitize_bids_label(value: str) -> str:
        """Convert a value to a legal BIDS participant label."""
        value = re.sub(r"^sub-", "", value, flags=re.IGNORECASE)
        label = re.sub(r"[^A-Za-z0-9]", "", value)
        return label or "case"

    @classmethod
    def _suggest_subject_label(cls, image: Path) -> str:
        """Derive a BIDS subject label from a source image name."""
        stem = cls._strip_nifti_suffix(image.name)

        # Preserve a pre-existing BIDS subject ID when one is present.
        match = re.match(
            r"^sub-([A-Za-z0-9]+)(?:_|$)",
            stem,
            flags=re.IGNORECASE,
        )
        if match:
            return cls._sanitize_bids_label(match.group(1))

        return cls._sanitize_bids_label(stem)

    @classmethod
    def _discover_nifti_images(cls, input_dir: Path) -> list[Path]:
        """Recursively discover candidate T1-weighted NIfTI images."""
        images: list[Path] = []

        for path in input_dir.rglob("*"):
            if not path.is_file() or not cls._is_nifti(path):
                continue

            relative_parts = path.relative_to(input_dir).parts[:-1]
            if any(part.startswith(".") for part in relative_parts):
                continue
            if any(
                part.lower() in _EXCLUDED_DIRECTORY_NAMES
                for part in relative_parts
            ):
                continue

            images.append(path.resolve())

        return sorted(images, key=lambda item: str(item).lower())

    @classmethod
    def _find_bids_t1w_images(cls, bids_dir: Path) -> list[Path]:
        """Find T1w files in a BIDS-like directory tree."""
        images: list[Path] = []

        for path in bids_dir.rglob("*"):
            if not path.is_file() or not cls._is_nifti(path):
                continue
            if not cls._strip_nifti_suffix(path.name).endswith("_T1w"):
                continue
            if not any(
                part.startswith("sub-")
                for part in path.relative_to(bids_dir).parts
            ):
                continue
            images.append(path.resolve())

        return sorted(images, key=lambda item: str(item).lower())

    @classmethod
    def _looks_like_bids_dataset(cls, input_dir: Path) -> bool:
        """Return True when a minimal structural BIDS dataset is present."""
        return (
            (input_dir / "dataset_description.json").is_file()
            and bool(cls._find_bids_t1w_images(input_dir))
        )

    @staticmethod
    def _source_json_sidecar(image: Path) -> Path:
        if image.name.lower().endswith(".nii.gz"):
            return image.with_name(image.name[:-7] + ".json")
        return image.with_suffix(".json")

    @staticmethod
    def _link_or_copy(source: Path, destination: Path) -> str:
        """Hard-link a file when possible; otherwise copy it."""
        destination.parent.mkdir(parents=True, exist_ok=True)

        try:
            os.link(source, destination)
            return "hardlink"
        except OSError:
            shutil.copy2(source, destination)
            return "copy"

    @staticmethod
    def _staging_directory(
        output_dir: Path,
        work_dir: Path | None,
    ) -> Path:
        if work_dir is not None:
            return work_dir.resolve() / "enigma_pipe_mriqc_bids"

        return (
            output_dir.resolve().parent
            / f".{output_dir.resolve().name}_enigma_pipe_mriqc_bids"
        )

    @classmethod
    def _reset_generated_bids_directory(cls, staging_dir: Path) -> None:
        """Safely reset a directory previously generated by this module."""
        if staging_dir.exists():
            marker = staging_dir / _GENERATED_BIDS_MARKER
            if not marker.is_file():
                raise RuntimeError(
                    "Refusing to replace a non-generated directory: "
                    f"{staging_dir}"
                )
            shutil.rmtree(staging_dir)

        staging_dir.mkdir(parents=True, exist_ok=True)
        (staging_dir / _GENERATED_BIDS_MARKER).write_text(
            "Generated automatically by enigma-pipe MRIQC service.\n",
            encoding="utf-8",
        )

    @classmethod
    def _prepare_bids_dataset(
        cls,
        input_dir: Path,
        output_dir: Path,
        work_dir: Path | None,
    ) -> tuple[Path, dict[str, str]]:
        """Create a minimal BIDS dataset from loose NIfTI files.

        Each source image is represented as one BIDS participant. This avoids
        making unsupported assumptions about visits or sessions encoded in
        arbitrary filenames.

        Returns
        -------
        staging_dir
            Path to the generated BIDS dataset.
        aliases
            Mapping from original/source labels to generated BIDS labels.
        """
        images = cls._discover_nifti_images(input_dir)
        if not images:
            raise FileNotFoundError(
                "No .nii or .nii.gz images were found under "
                f"{input_dir.resolve()}."
            )

        staging_dir = cls._staging_directory(output_dir, work_dir)
        cls._reset_generated_bids_directory(staging_dir)

        dataset_description = {
            "Name": "ENIGMA Pipe temporary MRIQC input",
            "BIDSVersion": "1.9.0",
            "DatasetType": "raw",
        }
        (staging_dir / "dataset_description.json").write_text(
            json.dumps(dataset_description, indent=2) + "\n",
            encoding="utf-8",
        )

        aliases: dict[str, str] = {}
        used_labels: set[str] = set()
        participant_rows: list[list[str]] = []
        hardlinked = 0
        copied = 0

        for image in images:
            relative_path = image.relative_to(input_dir.resolve())
            base_label = cls._suggest_subject_label(image)
            label = base_label

            if label in used_labels:
                digest = hashlib.sha1(
                    str(relative_path).encode("utf-8")
                ).hexdigest()[:8]
                label = f"{base_label}{digest}"

            # Guard against the extremely unlikely event of a repeated digest.
            collision_index = 2
            while label in used_labels:
                label = f"{base_label}{collision_index}"
                collision_index += 1

            used_labels.add(label)

            extension = (
                ".nii.gz"
                if image.name.lower().endswith(".nii.gz")
                else ".nii"
            )
            anat_dir = staging_dir / f"sub-{label}" / "anat"
            destination = anat_dir / f"sub-{label}_T1w{extension}"

            transfer_mode = cls._link_or_copy(image, destination)
            if transfer_mode == "hardlink":
                hardlinked += 1
            else:
                copied += 1

            source_json = cls._source_json_sidecar(image)
            if source_json.is_file():
                destination_json = (
                    anat_dir / f"sub-{label}_T1w.json"
                )
                shutil.copy2(source_json, destination_json)

            participant_rows.append([f"sub-{label}"])

            source_stem = cls._strip_nifti_suffix(image.name)
            alias_values = {
                label,
                f"sub-{label}",
                base_label,
                image.name,
                source_stem,
                cls._sanitize_bids_label(source_stem),
                str(relative_path),
            }
            for alias in alias_values:
                aliases.setdefault(alias, label)
                aliases.setdefault(alias.lower(), label)

        with (staging_dir / "participants.tsv").open(
            "w",
            encoding="utf-8",
            newline="",
        ) as stream:
            writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
            writer.writerow(["participant_id"])
            writer.writerows(participant_rows)

        readme = (
            "This BIDS dataset was generated automatically by enigma-pipe "
            "from loose NIfTI files for MRIQC processing.\n"
            "Each source image was assigned to a separate BIDS participant.\n"
        )
        (staging_dir / "README").write_text(readme, encoding="utf-8")

        print_info(
            "Prepared temporary BIDS dataset with "
            f"{len(images)} T1w image(s): {staging_dir}"
        )
        print_info(
            f"BIDS staging used {hardlinked} hard link(s) and "
            f"{copied} copied file(s)."
        )

        return staging_dir, aliases

    @classmethod
    def _translate_participant_labels(
        cls,
        participant_labels: list[str] | None,
        aliases: dict[str, str] | None,
    ) -> list[str] | None:
        """Normalize or translate requested participant labels."""
        if not participant_labels:
            return None

        translated: list[str] = []

        for requested in participant_labels:
            without_prefix = re.sub(
                r"^sub-",
                "",
                requested,
                flags=re.IGNORECASE,
            )

            if aliases is None:
                label = cls._sanitize_bids_label(without_prefix)
            else:
                label = (
                    aliases.get(requested)
                    or aliases.get(requested.lower())
                    or aliases.get(without_prefix)
                    or aliases.get(without_prefix.lower())
                    or aliases.get(cls._sanitize_bids_label(without_prefix))
                )

                if label is None:
                    label = cls._sanitize_bids_label(without_prefix)
                    print_warning(
                        "Could not match participant label "
                        f"'{requested}' to an input filename; MRIQC will "
                        f"receive '{label}'."
                    )

            if label not in translated:
                translated.append(label)

        return translated

    def run_bids_dataset(
        self,
        bids_dir: Path,
        output_dir: Path,
        work_dir: Path | None = None,
        participant_label: list[str] | None = None,
        n_procs: int | None = None,
    ) -> int:
        """Run MRIQC participant level on BIDS or loose T1w NIfTI files.

        Despite the historical parameter name ``bids_dir``, this method now
        accepts either:

        1. an existing BIDS dataset; or
        2. a directory containing loose ``.nii``/``.nii.gz`` T1w images.

        Loose images are converted into a minimal intermediate BIDS dataset
        before MRIQC is executed.
        """
        input_dir = bids_dir.resolve()
        output_dir = output_dir.resolve()
        resolved_work_dir = work_dir.resolve() if work_dir else None

        output_dir.mkdir(parents=True, exist_ok=True)

        aliases: dict[str, str] | None = None

        if self._looks_like_bids_dataset(input_dir):
            effective_bids_dir = input_dir
            print_info(
                "Existing BIDS dataset detected; automatic conversion "
                "is not required."
            )
        else:
            print_info(
                "Input is not a complete BIDS dataset. Preparing a "
                "temporary structural BIDS dataset for MRIQC."
            )
            try:
                effective_bids_dir, aliases = self._prepare_bids_dataset(
                    input_dir=input_dir,
                    output_dir=output_dir,
                    work_dir=resolved_work_dir,
                )
            except (FileNotFoundError, OSError, RuntimeError) as exc:
                print_warning(f"Could not prepare MRIQC BIDS input: {exc}")
                return 2

        selected_participants = self._translate_participant_labels(
            participant_label,
            aliases,
        )

        binds = [
            (effective_bids_dir.resolve(), Path("/data")),
            (output_dir, Path("/out")),
        ]

        args = self._entrypoint() + [
            "/data",
            "/out",
            "participant",
            "--no-sub",
            "-m",
            "T1w",
            "--no-datalad-get",
        ]

        if resolved_work_dir:
            resolved_work_dir.mkdir(parents=True, exist_ok=True)
            binds.append((resolved_work_dir, Path("/work")))
            args.extend(["-w", "/work"])

        if selected_participants:
            args.extend(
                ["--participant-label", *selected_participants]
            )

        if n_procs:
            args.extend(["--nprocs", str(n_procs)])

        return self.run(binds, args)
