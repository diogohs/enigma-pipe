import os
import signal
import subprocess
import tempfile
from pathlib import Path

import nibabel as nib


class ITKSnapLauncher:
    def __init__(self, executable_path: Path | None = None):
        # Look in PATH if not provided
        self.executable = executable_path or "itksnap"
        self._current_process: subprocess.Popen | None = None
        self._temp_dir: tempfile.TemporaryDirectory | None = None

    def _convert_mgz_to_nii(self, mgz_path: Path) -> Path:
        """Convert .mgz to .nii.gz in a temporary directory."""
        if self._temp_dir is None:
            self._temp_dir = tempfile.TemporaryDirectory()

        nii_name = mgz_path.with_suffix("").with_suffix(".nii.gz").name
        nii_path = Path(self._temp_dir.name) / nii_name

        if not nii_path.exists():
            img = nib.load(mgz_path)
            nib.save(img, nii_path)
        return nii_path

    def launch(self, image_path: Path, overlay_paths: list[Path] = []) -> None:
        """Launch ITK-SNAP non-blocking."""
        self.close()  # Attempt to close previous window

        # Convert inputs if needed
        if image_path.name.endswith(".mgz"):
            image_path = self._convert_mgz_to_nii(image_path)

        processed_overlays = []
        for p in overlay_paths:
            if p.name.endswith(".mgz"):
                processed_overlays.append(self._convert_mgz_to_nii(p))
            else:
                processed_overlays.append(p)

        cmd = [str(self.executable), "-g", str(image_path)]
        if processed_overlays:
            cmd.extend(["-o"] + [str(p) for p in processed_overlays])

        try:
            # Use preexec_fn=os.setsid to create a process group (Linux/macOS)
            # This allows us to kill it robustly
            if os.name == "posix":
                self._current_process = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid
                )
            else:
                self._current_process = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
        except Exception:
            # If ITK-SNAP is missing, it's non-blocking, so we'll log it in the caller or just proceed
            pass

    def close(self):
        """Close the currently running ITK-SNAP process if any."""
        if self._current_process and self._current_process.poll() is None:
            try:
                if os.name == "posix":
                    os.killpg(os.getpgid(self._current_process.pid), signal.SIGTERM)
                else:
                    self._current_process.terminate()
            except Exception:
                pass  # Fail silently as per spec
        self._current_process = None

        if self._temp_dir is not None:
            self._temp_dir.cleanup()
            self._temp_dir = None
