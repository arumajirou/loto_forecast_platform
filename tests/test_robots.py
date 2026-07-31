"""robots.txt must actually be enforced, not merely advertised in a User-Agent."""

import urllib.error
import urllib.robotparser

import pytest

from loto.data.robots import RobotsPolicy


class _FakeParser:
    """Stand-in for RobotFileParser with scripted answers."""

    def __init__(self, allow=True, delay=None, raise_on_read=None):
        self._allow = allow
        self._delay = delay
        self._raise = raise_on_read
        self.url = ""

    def set_url(self, url):
        self.url = url

    def read(self):
        if self._raise is not None:
            raise self._raise

    def can_fetch(self, agent, url):
        del agent, url
        return self._allow

    def crawl_delay(self, agent):
        del agent
        return self._delay


@pytest.fixture()
def patched(monkeypatch):
    def _install(**kwargs):
        monkeypatch.setattr(urllib.robotparser, "RobotFileParser", lambda: _FakeParser(**kwargs))

    return _install


def test_allowed_url_is_permitted(patched):
    patched(allow=True)
    policy = RobotsPolicy("agent/1.0")
    decision = policy.check("https://example.invalid/csv/loto7")
    assert decision.allowed
    assert decision.robots_url == "https://example.invalid/robots.txt"


def test_disallowed_url_is_refused(patched):
    patched(allow=False)
    policy = RobotsPolicy("agent/1.0")
    decision = policy.check("https://example.invalid/csv/loto7")
    assert not decision.allowed
    assert "disallowed" in decision.reason


def test_crawl_delay_is_captured(patched):
    patched(allow=True, delay=5.0)
    decision = RobotsPolicy("agent/1.0").check("https://example.invalid/a")
    assert decision.crawl_delay == 5.0


def test_crawl_delay_can_be_ignored_explicitly(patched):
    patched(allow=True, delay=5.0)
    policy = RobotsPolicy("agent/1.0", respect_crawl_delay=False)
    assert policy.check("https://example.invalid/a").crawl_delay is None


def test_unreachable_robots_fails_open_but_records_why(patched):
    patched(raise_on_read=urllib.error.URLError("boom"))
    decision = RobotsPolicy("agent/1.0").check("https://example.invalid/a")
    assert decision.allowed
    assert "unreachable" in decision.reason


def test_oserror_on_read_also_fails_open(patched):
    patched(raise_on_read=OSError("socket"))
    assert RobotsPolicy("agent/1.0").check("https://example.invalid/a").allowed


def test_parser_is_cached_per_host(patched, monkeypatch):
    calls = []

    class _Counting(_FakeParser):
        def read(self):
            calls.append(self.url)

    monkeypatch.setattr(urllib.robotparser, "RobotFileParser", lambda: _Counting())
    policy = RobotsPolicy("agent/1.0")
    policy.check("https://example.invalid/a")
    policy.check("https://example.invalid/b")
    policy.check("https://other.invalid/c")
    assert len(calls) == 2  # one read per host, not per URL


def test_relative_url_is_rejected():
    with pytest.raises(ValueError, match="relative URL"):
        RobotsPolicy("agent/1.0").check("/csv/loto7")


def test_negative_interval_is_rejected():
    with pytest.raises(ValueError, match="min_interval"):
        RobotsPolicy("agent/1.0", min_interval=-1.0)


def test_first_request_does_not_sleep(patched):
    patched(allow=True)
    policy = RobotsPolicy("agent/1.0", min_interval=0.05)
    assert policy.wait("https://example.invalid/a") == 0.0


def test_second_request_waits_the_minimum_interval(patched):
    patched(allow=True)
    policy = RobotsPolicy("agent/1.0", min_interval=0.05)
    policy.wait("https://example.invalid/a")
    slept = policy.wait("https://example.invalid/b")
    assert slept > 0.0


def test_crawl_delay_overrides_a_smaller_minimum(patched):
    patched(allow=True, delay=0.08)
    policy = RobotsPolicy("agent/1.0", min_interval=0.01)
    decision = policy.check("https://example.invalid/a")
    policy.wait("https://example.invalid/a", decision)
    slept = policy.wait("https://example.invalid/a", decision)
    assert slept >= 0.05


def test_rate_limit_is_tracked_per_host(patched):
    patched(allow=True)
    policy = RobotsPolicy("agent/1.0", min_interval=0.05)
    policy.wait("https://a.invalid/x")
    assert policy.wait("https://b.invalid/x") == 0.0


def test_every_decision_is_auditable(patched):
    patched(allow=False)
    policy = RobotsPolicy("agent/1.0")
    policy.check("https://example.invalid/a")
    policy.check("https://example.invalid/b")
    audit = policy.audit()
    assert len(audit) == 2
    assert all(row["allowed"] is False for row in audit)
    assert all("robots_url" in row for row in audit)
