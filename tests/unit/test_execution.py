import pytest
from fastsurfer_pipeline.execution import build_fastsurfer_command, ExecutionConfig, ContainerType, DeviceType

def test_docker_gpu_execution():
    config = ExecutionConfig(container_type=ContainerType.DOCKER, device=DeviceType.GPU, use_3t=True)
    cmd = build_fastsurfer_command(config)
    
    assert "--gpus" in cmd
    assert "all" in cmd
    
    # Needs to handle --user $(id -u):$(id -g) which could be multiple args or one
    user_flag_found = any("--user" in arg for arg in cmd) or "--user" in cmd
    assert user_flag_found
    
    assert "--rm" in cmd
    assert "--3T" in cmd

def test_docker_cpu_execution():
    config = ExecutionConfig(container_type=ContainerType.DOCKER, device=DeviceType.CPU, use_3t=True)
    cmd = build_fastsurfer_command(config)
    
    assert "--gpus" not in cmd
    assert "all" not in cmd
    
    user_flag_found = any("--user" in arg for arg in cmd) or "--user" in cmd
    assert user_flag_found
    
    assert "--rm" in cmd
    assert "--3T" in cmd

def test_singularity_cpu_execution():
    config = ExecutionConfig(container_type=ContainerType.SINGULARITY, device=DeviceType.CPU, use_3t=True)
    cmd = build_fastsurfer_command(config)
    
    assert "--nv" not in cmd
    assert "--no-mount" in cmd
    assert "home,cwd" in cmd
    assert "-e" in cmd
    assert "--3T" in cmd

def test_singularity_gpu_execution():
    config = ExecutionConfig(container_type=ContainerType.SINGULARITY, device=DeviceType.GPU, use_3t=True)
    cmd = build_fastsurfer_command(config)
    
    assert "--nv" in cmd
    assert "--no-mount" in cmd
    assert "home,cwd" in cmd
    assert "-e" in cmd
    assert "--3T" in cmd
    
def test_apptainer_gpu_execution():
    config = ExecutionConfig(container_type=ContainerType.APPTAINER, device=DeviceType.GPU, use_3t=False)
    cmd = build_fastsurfer_command(config)
    
    assert "--nv" in cmd
    assert "--no-mount" in cmd
    assert "home,cwd" in cmd
    assert "-e" in cmd
    assert "--3T" not in cmd

def test_invalid_device():
    with pytest.raises(ValueError, match="Invalid"):
        config = ExecutionConfig(container_type=ContainerType.DOCKER, device="tpu")
        build_fastsurfer_command(config)
