from pathlib import Path
from typing import List, Optional

from enigma_pipe.core.models import ExecutionMode
from enigma_pipe.services.container import ContainerRunner

class FastSurferRunner(ContainerRunner):
    def __init__(self, mode: ExecutionMode, image: str = "deepmi/fastsurfer:latest"):
        super().__init__(mode, image)
        
    def check_version(self) -> str:
        """Get the FastSurfer version from the container."""
        cmd = self.build_command(binds=[], extra_args=["--version"])
        import subprocess
        try:
            result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return "unknown"

    def run_case(self, case_id: str, input_path: Path, output_dir: Path, fs_license: Path, 
                 device: str = "cpu", threads: Optional[int] = None, 
                 no_asegdkt: bool = False, no_cc: bool = False, no_cereb: bool = False, no_hypothal: bool = True) -> int:
        """Run FastSurfer for a single case."""
        case_out = output_dir / case_id
        case_out.mkdir(parents=True, exist_ok=True)
        
        binds = [
            (input_path.parent.resolve(), Path("/data")),
            (output_dir.resolve(), Path("/output")),
            (fs_license.resolve(), Path("/fs_license.txt"))
        ]
        
        args = [
            "--t1", f"/data/{input_path.name}",
            "--sid", case_id,
            "--sd", "/output",
            "--fs_license", "/fs_license.txt",
            "--device", device
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
            
        return self.run(binds, args)
