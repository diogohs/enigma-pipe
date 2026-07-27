class EnigmaPipeError(Exception):
    """Base exception for all CLI errors."""
    exit_code = 1

class InvalidSettingsError(EnigmaPipeError):
    """Raised when settings or arguments are invalid."""
    exit_code = 2

class MissingDependencyError(EnigmaPipeError):
    """Raised when a required external dependency or container runtime is missing."""
    exit_code = 3

class PartialBatchFailureError(EnigmaPipeError):
    """Raised when one or more cases in a batch fail, but the batch completes."""
    exit_code = 4

class InterruptedError(EnigmaPipeError):
    """Raised when the process is interrupted via SIGINT/Ctrl-C."""
    exit_code = 130
