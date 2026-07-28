import os
import shlex
import subprocess
from pathlib import Path

from enigma_pipe.cli.formatting import print_info
from enigma_pipe.core.exceptions import MissingDependencyError
from enigma_pipe.core.models import ExecutionMode


class ContainerRunner:
    def __init__(self, mode: ExecutionMode, image: str):
        self.mode = mode
        self.image = image
        self._check_runtime()

    def _check_runtime(self):
        """Check if container runtime is available."""
        cmd = (
            ["docker", "--version"]
            if self.mode == ExecutionMode.DOCKER
            else [self.mode.value, "--version"]
        )
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            # For singularity, fall back to apptainer if not found, and vice-versa
            if self.mode == ExecutionMode.SINGULARITY:
                try:
                    subprocess.run(["apptainer", "--version"], check=True, capture_output=True)
                    self.mode = ExecutionMode.APPTAINER
                except (subprocess.CalledProcessError, FileNotFoundError):
                    raise MissingDependencyError("Singularity/Apptainer not found on PATH.")
            else:
                raise MissingDependencyError(f"{self.mode.value} not found on PATH.")

    def build_command(
        self,
        binds: list[tuple[Path, Path]],
        extra_args: list[str] = [],
        container_opts: list[str] = [],
    ) -> list[str]:
        cmd = []
        if self.mode == ExecutionMode.DOCKER:
            cmd = ["docker", "run", "--rm", "-t"]
            if hasattr(os, "getuid") and hasattr(os, "getgid") and "--user" not in container_opts:
                cmd.extend(["--user", f"{os.getuid()}:{os.getgid()}"])
            for src, dst in binds:
                cmd.extend(["-v", f"{src}:{dst}"])
            cmd.extend(container_opts)
            cmd.append(self.image)
        elif self.mode in (ExecutionMode.SINGULARITY, ExecutionMode.APPTAINER):
            cmd = [self.mode.value, "exec", "--cleanenv"]
            for src, dst in binds:
                cmd.extend(["-B", f"{src}:{dst}"])
            cmd.extend(container_opts)
            cmd.append(self.image)
        cmd.extend(extra_args)
        return cmd

    def run(
        self,
        binds: list[tuple[Path, Path]],
        extra_args: list[str] = [],
        container_opts: list[str] = [],
    ) -> int:
        cmd = self.build_command(binds, extra_args, container_opts)
        print_info(f"Executing command: {shlex.join(cmd)}")
        try:
            result = subprocess.run(cmd, check=False)
            return result.returncode
        except Exception as e:
            raise MissingDependencyError(f"Failed to start container: {e}")
