"""Tests for the PyPI update-check module (BOFS/update_check.py).

Uses ``unittest.mock`` to avoid real network calls and to control the
installed-distribution environment.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from BOFS.update_check import (
    UpdateInfo,
    check_for_update,
    fetch_latest_version,
    get_install_info,
    is_newer,
)


# =========================================================================
# is_newer
# =========================================================================


class TestIsNewer:
    def test_newer(self):
        assert is_newer("2.0.0.61", "2.0.0.60") is True

    def test_older(self):
        assert is_newer("2.0.0.59", "2.0.0.60") is False

    def test_equal(self):
        assert is_newer("2.0.0.60", "2.0.0.60") is False

    def test_different_segment_count(self):
        assert is_newer("1.0", "1.0.0") is False

    def test_more_segments_newer(self):
        assert is_newer("1.0.1", "1.0") is True

    def test_non_numeric_segment_no_crash(self):
        # Non-numeric segments are treated as 0, so both sides equal.
        assert is_newer("2.0.0.rc1", "2.0.0") is False

    def test_non_numeric_segment_both_sides(self):
        assert is_newer("2.0.0.rc2", "2.0.0.rc1") is False

    def test_major_version_bump(self):
        assert is_newer("3.0.0", "2.9.9") is True

    def test_patch_version_bump(self):
        assert is_newer("2.0.1", "2.0.0") is True

    def test_same_major_different_minor(self):
        assert is_newer("2.1.0", "2.0.9") is True


# =========================================================================
# get_install_info
# =========================================================================


def _make_dist(name, version, top_level_lines=None):
    """Build a minimal ``Distribution`` stand-in.

    *top_level_lines* is an iterable of lines (without newlines) to
    serve via ``read_text('top_level.txt')``.  ``metadata`` is a real
    dict so ``.get('Name')`` / ``.get('Version')`` behave like
    ``importlib.metadata``'s PackageMetadata (works on Python 3.9+,
    where ``Distribution.name`` / ``.version`` don't exist).
    """
    dist = MagicMock()
    dist.metadata = {"Name": name, "Version": version}

    if top_level_lines is not None:
        dist.read_text.return_value = "\n".join(top_level_lines)
    else:
        dist.read_text.return_value = None

    return dist


class TestGetInstallInfo:
    @patch("importlib.metadata.distributions")
    def test_finds_by_top_level(self, mock_distributions):
        """Finds the distribution that owns the ``BOFS`` package via
        ``top_level.txt``."""
        mock_distributions.return_value = [
            _make_dist("some-other-pkg", "1.0",
                       top_level_lines=["other"]),
            _make_dist("bride-of-frankensystem-dev", "2.0.0.60",
                       top_level_lines=["BOFS", "BOFSFlask"]),
        ]
        result = get_install_info()
        assert result == ("bride-of-frankensystem-dev", "2.0.0.60")

    @patch("importlib.metadata.distributions")
    def test_fallback_by_dist_name(self, mock_distributions):
        """Falls back to matching by distribution name when
        ``top_level.txt`` is missing or doesn't contain ``BOFS``."""
        mock_distributions.return_value = [
            _make_dist("bride-of-frankensystem", "2.0.0.11"),
        ]
        result = get_install_info()
        assert result == ("bride-of-frankensystem", "2.0.0.11")

    @patch("importlib.metadata.distributions")
    def test_none_when_not_found(self, mock_distributions):
        """Returns ``None`` when no distribution matches."""
        mock_distributions.return_value = [
            _make_dist("unrelated", "1.0",
                       top_level_lines=["unrelated"]),
        ]
        result = get_install_info()
        assert result is None

    @patch("importlib.metadata.distributions")
    def test_handles_read_text_exception(self, mock_distributions):
        """Silently skips distributions whose ``top_level.txt`` can't be
        read."""
        broken = _make_dist("broken", "1.0")
        broken.read_text.side_effect = OSError("permission denied")

        good = _make_dist("bride-of-frankensystem-dev", "2.0.0.60",
                          top_level_lines=["BOFS"])

        mock_distributions.return_value = [broken, good]
        result = get_install_info()
        assert result == ("bride-of-frankensystem-dev", "2.0.0.60")


# =========================================================================
# fetch_latest_version
# =========================================================================


class TestFetchLatestVersion:
    @patch("BOFS.update_check.urllib.request.urlopen")
    def test_success(self, mock_urlopen):
        """Returns the version string from a successful PyPI response."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"info": {"version": "2.0.0.61"}}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = fetch_latest_version("bride-of-frankensystem-dev")
        assert result == "2.0.0.61"
        mock_urlopen.assert_called_once_with(
            "https://pypi.org/pypi/bride-of-frankensystem-dev/json",
            timeout=3,
        )

    @patch("BOFS.update_check.urllib.request.urlopen")
    def test_non_200_returns_none(self, mock_urlopen):
        """Non-200 HTTP status silently returns None."""
        mock_resp = MagicMock()
        mock_resp.status = 404
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = fetch_latest_version("bride-of-frankensystem-dev")
        assert result is None

    @patch("BOFS.update_check.urllib.request.urlopen")
    def test_timeout_returns_none(self, mock_urlopen):
        """A timeout exception silently returns None."""
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("timed out")

        result = fetch_latest_version("bride-of-frankensystem-dev")
        assert result is None

    @patch("BOFS.update_check.urllib.request.urlopen")
    def test_malformed_json_returns_none(self, mock_urlopen):
        """Malformed JSON body silently returns None."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"not json"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = fetch_latest_version("bride-of-frankensystem-dev")
        assert result is None

    @patch("BOFS.update_check.urllib.request.urlopen")
    def test_dns_failure_returns_none(self, mock_urlopen):
        """DNS failure silently returns None."""
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError(
            "[Errno -2] Name or service not known"
        )

        result = fetch_latest_version("bride-of-frankensystem-dev")
        assert result is None

    @patch("BOFS.update_check.urllib.request.urlopen")
    def test_custom_timeout(self, mock_urlopen):
        """Passes a custom timeout value."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"info": {"version": "1.0"}}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = fetch_latest_version("bride-of-frankensystem-dev",
                                      timeout=5)
        assert result == "1.0"
        # Verify the timeout was passed to urlopen
        _call_kwargs = mock_urlopen.call_args[1]
        assert _call_kwargs.get("timeout") == 5

    @patch("BOFS.update_check.urllib.request.urlopen")
    def test_no_version_key_returns_none(self, mock_urlopen):
        """Response missing the 'version' key returns None."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"info": {}}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = fetch_latest_version("bride-of-frankensystem-dev")
        assert result is None


# =========================================================================
# check_for_update
# =========================================================================


class TestCheckForUpdate:
    @patch("BOFS.update_check.fetch_latest_version")
    @patch("BOFS.update_check.get_install_info")
    def test_update_available(self, mock_get_install, mock_fetch):
        """Returns UpdateInfo with available=True when newer version
        exists."""
        mock_get_install.return_value = (
            "bride-of-frankensystem-dev", "2.0.0.60"
        )
        mock_fetch.return_value = "2.0.0.61"

        result = check_for_update()
        assert result is not None
        assert result.available is True
        assert result.current == "2.0.0.60"
        assert result.latest == "2.0.0.61"
        assert result.dist_name == "bride-of-frankensystem-dev"

    @patch("BOFS.update_check.fetch_latest_version")
    @patch("BOFS.update_check.get_install_info")
    def test_up_to_date(self, mock_get_install, mock_fetch):
        """Returns UpdateInfo with available=False when versions match."""
        mock_get_install.return_value = (
            "bride-of-frankensystem-dev", "2.0.0.60"
        )
        mock_fetch.return_value = "2.0.0.60"

        result = check_for_update()
        assert result is not None
        assert result.available is False

    @patch("BOFS.update_check.fetch_latest_version")
    @patch("BOFS.update_check.get_install_info")
    def test_network_failure_returns_none(self, mock_get_install,
                                          mock_fetch):
        """Returns None when the network check fails."""
        mock_get_install.return_value = (
            "bride-of-frankensystem-dev", "2.0.0.60"
        )
        mock_fetch.return_value = None

        result = check_for_update()
        assert result is None

    @patch("BOFS.update_check.get_install_info")
    def test_unresolvable_dist_returns_none(self, mock_get_install):
        """Returns None when no distribution is found."""
        mock_get_install.return_value = None

        result = check_for_update()
        assert result is None

    @patch("BOFS.update_check.fetch_latest_version")
    @patch("BOFS.update_check.get_install_info")
    def test_available_with_stable_dist(self, mock_get_install, mock_fetch):
        """Works with the stable distribution name."""
        mock_get_install.return_value = (
            "bride-of-frankensystem", "2.0.0.10"
        )
        mock_fetch.return_value = "2.0.0.11"

        result = check_for_update()
        assert result is not None
        assert result.available is True
        assert result.dist_name == "bride-of-frankensystem"
        assert result.latest == "2.0.0.11"
