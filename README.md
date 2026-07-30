# enigma-pipe

A CLI tool for running containerized neuroimaging pipelines.

## Commands

### `fastsurfer`
Runs the FastSurfer structural processing pipeline.
```bash
enigma-pipe fastsurfer /path/to/input /path/to/output --fs-license /path/to/license.txt
```
**Options**:
- `--no-brainstem`: Skips the brainstem subsegmentation step (runs by default).

### `brainstem`
Runs standalone brainstem subsegmentation on an existing FastSurfer output directory.
```bash
enigma-pipe brainstem /path/to/output/case_id --overwrite
```
