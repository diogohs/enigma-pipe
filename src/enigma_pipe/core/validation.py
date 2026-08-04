from enigma_pipe.core.exceptions import InvalidSettingsError


def validate_threads(threads: str | int | None) -> str | int | None:
    """Validate thread count input.

    Accepts positive integers (e.g. 4, "4") or strictly "max" (case-insensitive).
    Raises InvalidSettingsError for any invalid input (e.g. 0, negative integers, floats, arbitrary strings).
    """
    if threads is None:
        return None

    if isinstance(threads, int):
        if threads <= 0:
            raise InvalidSettingsError(
                f"Invalid --threads value '{threads}'. Must be a positive integer or 'max'."
            )
        return threads

    val = str(threads).strip()
    if val.lower() == "max":
        return "max"

    try:
        num = int(val)
        if num <= 0:
            raise InvalidSettingsError(
                f"Invalid --threads value '{threads}'. Must be a positive integer or 'max'."
            )
        return num
    except ValueError:
        raise InvalidSettingsError(
            f"Invalid --threads value '{threads}'. Must be a positive integer or 'max'."
        )
