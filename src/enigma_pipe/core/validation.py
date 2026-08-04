from enigma_pipe.core.exceptions import InvalidSettingsError


def validate_threads(threads: str | int | None) -> str | int:
    """Validate thread count input.

    Accepts positive integers (e.g. 4, "4") or strictly "max" (case-insensitive).
    If -1, it is set to "max".
    If None, it defaults to 1.
    Raises InvalidSettingsError for any invalid input (e.g. 0, negative integers other than -1, floats, arbitrary strings).
    """
    if threads is None:
        return 1

    if isinstance(threads, int):
        if threads == -1:
            return "max"
        if threads <= 0:
            raise InvalidSettingsError(
                f"Invalid --threads value '{threads}'. Must be a positive integer, -1, or 'max'."
            )
        return threads

    val = str(threads).strip()
    if val.lower() == "max":
        return "max"

    try:
        num = int(val)
        if num == -1:
            return "max"
        if num <= 0:
            raise InvalidSettingsError(
                f"Invalid --threads value '{threads}'. Must be a positive integer, -1, or 'max'."
            )
        return num
    except ValueError:
        raise InvalidSettingsError(
            f"Invalid --threads value '{threads}'. Must be a positive integer, -1, or 'max'."
        )
