from pathlib import Path

from enigma_pipe.core.models import ExecutionMode
from enigma_pipe.services.container import ContainerRunner


class MRIQCRunner(ContainerRunner):
    def __init__(self, mode: ExecutionMode, image: str = "nipreps/mriqc:latest"):
        super().__init__(mode, image)

    def run_bids_dataset(
        self,
        bids_dir: Path,
        output_dir: Path,
        work_dir: Path,
        participant_label: list[str] | None = None,
        n_procs: int | None = None,
    ) -> int:
        """Run MRIQC participant level on a BIDS dataset."""
        output_dir.mkdir(parents=True, exist_ok=True)
        work_dir.mkdir(parents=True, exist_ok=True)

        binds = [
            (bids_dir.resolve(), Path("/data")),
            (output_dir.resolve(), Path("/out")),
            (work_dir.resolve(), Path("/work")),
        ]

        args = [
            "/data",
            "/out",
            "participant",
            "-w",
            "/work",
            "--no-sub",  # don't submit telemetry
            "-m",
            "T1w",
            "--no-datalad-get",
        ]

        if participant_label:
            args.extend(["--participant-label"] + participant_label)

        if n_procs:
            args.extend(["--nprocs", str(n_procs)])

        return self.run(binds, args)
