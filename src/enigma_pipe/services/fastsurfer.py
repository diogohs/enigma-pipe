from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess

from enigma_pipe.cli.formatting import print_info
from enigma_pipe.core.exceptions import MissingDependencyError
from enigma_pipe.core.models import ExecutionMode
from enigma_pipe.services.container import ContainerRunner


class FastSurferRunner(ContainerRunner):
    """Run FastSurfer with Docker, Singularity, or Apptainer.

    Docker uses the official Docker image directly. Singularity and Apptainer
    use a local SIF image and explicitly invoke FastSurfer's main script,
    because ``singularity exec`` does not automatically use the Docker
    entrypoint.
    """

    DOCKER_IMAGE = "deepmi/fastsurfer:latest"
    DEFAULT_SIF_IMAGE = (
        Path.home() / "enigma-pipe" / "images" / "fastsurfer.sif"
    )
    FASTSURFER_ENTRYPOINT = "/fastsurfer/run_fastsurfer.sh"

    def __init__(self, mode: ExecutionMode, image: str | None = None):
        configured_image = image or os.environ.get(
            "ENIGMA_PIPE_FASTSURFER_IMAGE"
        )

        if configured_image is None:
            if mode == ExecutionMode.DOCKER:
                configured_image = self.DOCKER_IMAGE
            else:
                configured_image = str(self.DEFAULT_SIF_IMAGE)

        configured_image = os.path.expandvars(
            os.path.expanduser(configured_image)
        )

        # For Singularity/Apptainer, the default is a local SIF file. A URI
        # such as docker://... is also accepted when explicitly supplied.
        if mode in (ExecutionMode.SINGULARITY, ExecutionMode.APPTAINER):
            if "://" not in configured_image:
                image_path = Path(configured_image)
                if not image_path.is_file():
                    raise MissingDependencyError(
                        "FastSurfer Singularity/Apptainer image not found "
                        f"at {image_path}. Create it with:\n"
                        f'  mkdir -p "{image_path.parent}"\n'
                        f"  singularity pull --force "
                        f'"{image_path}" '
                        "docker://deepmi/fastsurfer:latest\n"
                        "Alternatively, set ENIGMA_PIPE_FASTSURFER_IMAGE "
                        "to another .sif image or pass --image-sif."
                    )
                configured_image = str(image_path.resolve())

        super().__init__(mode, configured_image)

    def _entrypoint(self) -> list[str]:
        """Return the command that must run inside the container."""
        if self.mode == ExecutionMode.DOCKER:
            # The Docker image already defines the FastSurfer entrypoint.
            return []
        return [self.FASTSURFER_ENTRYPOINT]

    def check_version(self) -> str:
        """Get the FastSurfer version from the container."""
        cmd = self.build_command(
            binds=[],
            extra_args=self._entrypoint() + ["--version"],
        )
        print_info(f"Executing command: {shlex.join(cmd)}")
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return "unknown"

    def run_case(
        self,
        case_id: str,
        input_path: Path,
        output_dir: Path,
        fs_license: Path,
        device: str = "cpu",
        threads: int | str | None = None,
        no_asegdkt: bool = False,
        no_cc: bool = False,
        no_cereb: bool = False,
        no_hypothal: bool = True,
    ) -> int:
        """Run FastSurfer for a single case."""
        case_out = output_dir / case_id
        case_out.mkdir(parents=True, exist_ok=True)

        binds = [
            (input_path.parent.resolve(), Path("/data")),
            (output_dir.resolve(), Path("/output")),
            (fs_license.resolve(), Path("/fs_license.txt")),
        ]

        container_opts: list[str] = []
        if device.lower() in ("gpu", "cuda"):
            if self.mode == ExecutionMode.DOCKER:
                container_opts.extend(["--gpus", "all"])
            elif self.mode in (
                ExecutionMode.SINGULARITY,
                ExecutionMode.APPTAINER,
            ):
                container_opts.append("--nv")

        fs_device = "cuda" if device.lower() in ("gpu", "cuda") else device

        args = self._entrypoint() + [
            "--t1",
            f"/data/{input_path.name}",
            "--sid",
            case_id,
            "--sd",
            "/output",
            "--fs_license",
            "/fs_license.txt",
            "--device",
            fs_device,
        ]

        if threads:
            args.extend(["--threads", str(threads)])
        else:
            args.extend(["--threads", "max"])

        if no_asegdkt:
            args.append("--no_asegdkt")
        if no_cc:
            args.append("--no_cc")
        if no_cereb:
            args.append("--no_cereb")
        if no_hypothal:
            args.append("--no_hypothal")

        return self.run(binds, args, container_opts=container_opts)
