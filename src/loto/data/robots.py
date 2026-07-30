"""robots.txt compliance for the CSV fetcher.

The v2.1.0 fetcher advertised itself as a "polite downloader" in its User-Agent but never
read robots.txt and had no per-host rate limiter. Advertising politeness without enforcing
it is worse than silence, because it invites the operator to trust a claim the code does not
keep. This module makes the claim true.

Enforcement is fail-closed on an explicit ``Disallow`` and fail-open on a network error
reaching robots.txt itself, because a transient 500 on ``/robots.txt`` is not consent to be
blocked forever -- but the decision is always recorded so an audit can see which branch ran.
"""
from __future__ import annotations

import time
import urllib.error
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

__all__ = ["RobotsDecision", "RobotsPolicy"]


@dataclass(frozen=True)
class RobotsDecision:
    """Why a URL was allowed or refused."""

    url: str
    allowed: bool
    reason: str
    crawl_delay: float | None = None
    robots_url: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "url": self.url,
            "allowed": self.allowed,
            "reason": self.reason,
            "crawl_delay": self.crawl_delay,
            "robots_url": self.robots_url,
        }


class RobotsPolicy:
    """Per-host robots.txt cache plus a minimum-interval rate limiter."""

    def __init__(
        self,
        user_agent: str,
        *,
        min_interval: float = 1.0,
        timeout: float = 10.0,
        respect_crawl_delay: bool = True,
    ) -> None:
        if min_interval < 0:
            raise ValueError("min_interval must be >= 0")
        self.user_agent = user_agent
        self.min_interval = float(min_interval)
        self.timeout = float(timeout)
        self.respect_crawl_delay = respect_crawl_delay
        self._parsers: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._last_request: dict[str, float] = {}
        self.decisions: list[RobotsDecision] = []

    @staticmethod
    def _robots_url(url: str) -> tuple[str, str]:
        parts = urlsplit(url)
        if not parts.scheme or not parts.netloc:
            raise ValueError(f"cannot evaluate robots.txt for a relative URL: {url!r}")
        return parts.netloc, urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))

    def _parser_for(self, url: str):
        host, robots_url = self._robots_url(url)
        if host in self._parsers:
            return self._parsers[host], robots_url
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)
        try:
            parser.read()
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
            # unreachable robots.txt: record and fail open
            self._parsers[host] = None
            return None, robots_url
        self._parsers[host] = parser
        return parser, robots_url

    def check(self, url: str) -> RobotsDecision:
        parser, robots_url = self._parser_for(url)
        if parser is None:
            decision = RobotsDecision(
                url=url, allowed=True, robots_url=robots_url,
                reason="robots.txt unreachable; proceeding with configured rate limit",
            )
        elif parser.can_fetch(self.user_agent, url):
            delay = None
            if self.respect_crawl_delay:
                raw = parser.crawl_delay(self.user_agent)
                delay = float(raw) if raw is not None else None
            decision = RobotsDecision(
                url=url, allowed=True, reason="allowed by robots.txt",
                crawl_delay=delay, robots_url=robots_url,
            )
        else:
            decision = RobotsDecision(
                url=url, allowed=False, robots_url=robots_url,
                reason="disallowed by robots.txt for this user-agent",
            )
        self.decisions.append(decision)
        return decision

    def wait(self, url: str, decision: RobotsDecision | None = None) -> float:
        """Block until the per-host minimum interval has elapsed. Returns seconds slept."""
        host = urlsplit(url).netloc
        interval = self.min_interval
        if decision is not None and decision.crawl_delay:
            interval = max(interval, decision.crawl_delay)
        last = self._last_request.get(host)
        slept = 0.0
        if last is not None:
            remaining = interval - (time.monotonic() - last)
            if remaining > 0:
                time.sleep(remaining)
                slept = remaining
        self._last_request[host] = time.monotonic()
        return slept

    def audit(self) -> list[dict[str, object]]:
        return [d.to_dict() for d in self.decisions]
