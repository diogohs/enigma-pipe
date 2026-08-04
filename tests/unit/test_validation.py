import pytest
from enigma_pipe.core.exceptions import InvalidSettingsError
from enigma_pipe.core.validation import validate_threads


def test_validate_threads_valid():
    assert validate_threads(None) is None
    assert validate_threads("max") == "max"
    assert validate_threads("MAX") == "max"
    assert validate_threads("Max") == "max"
    assert validate_threads(4) == 4
    assert validate_threads("4") == 4
    assert validate_threads(1) == 1
    assert validate_threads("1") == 1


def test_validate_threads_invalid():
    invalid_inputs = [0, "0", -1, "-5", "abc", "maximum", "1.5", "  ", "max_threads"]
    for val in invalid_inputs:
        with pytest.raises(InvalidSettingsError) as exc_info:
            validate_threads(val)
        assert exc_info.value.exit_code == 2
        assert "Must be a positive integer or 'max'" in str(exc_info.value)
