from enigma_pipe.services.version_checker import VersionCheckResult, check_fastsurfer_version


def test_check_fastsurfer_version_supported():
    # Exact minimum
    res, ver = check_fastsurfer_version("FastSurfer v2.4.0")
    assert res == VersionCheckResult.SUPPORTED
    assert ver == "2.4.0"

    # Newer
    res, ver = check_fastsurfer_version("FastSurfer v2.5.3")
    assert res == VersionCheckResult.SUPPORTED

    # Major update
    res, ver = check_fastsurfer_version("3.0.0")
    assert res == VersionCheckResult.SUPPORTED

    # Pre-release
    res, ver = check_fastsurfer_version("2.5.0-dev")
    assert res == VersionCheckResult.SUPPORTED
    assert ver == "2.5.0"


def test_check_fastsurfer_version_unsupported():
    # Older
    res, ver = check_fastsurfer_version("FastSurfer v2.3.9")
    assert res == VersionCheckResult.UNSUPPORTED
    assert ver == "2.3.9"


def test_check_fastsurfer_version_unparseable():
    # Non-numeric
    res, msg = check_fastsurfer_version("FastSurfer dev-branch")
    assert res == VersionCheckResult.UNPARSEABLE
    assert msg == "could not verify"

    res, msg = check_fastsurfer_version("unknown")
    assert res == VersionCheckResult.UNPARSEABLE

    res, msg = check_fastsurfer_version("")
    assert res == VersionCheckResult.UNPARSEABLE
