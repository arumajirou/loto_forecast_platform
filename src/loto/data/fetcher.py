from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from loto.data.lotteries import LotterySpec


@dataclass
class FetchResult:
    game: str
    url: str
    status_code: int
    content_type: str | None
    raw_path: str
    meta_path: str
    sha256: str
    bytes: int
    fetched_at: str
    etag: str | None = None
    last_modified: str | None = None
    reused: bool = False


class PoliteHttpClient:
    def __init__(
        self,
        *,
        user_agent: str = "loto-forecast-platform/1.1 (+research; polite downloader)",
        timeout: float = 30.0,
        retries: int = 3,
        sleep_sec: float = 1.0,
    ) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.retries = retries
        self.sleep_sec = sleep_sec

    def fetch_one(self, spec: LotterySpec, raw_dir: str | Path, force: bool = False) -> FetchResult:
        out_dir = Path(raw_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        raw_path = out_dir / f"{spec.key}.csv"
        meta_path = out_dir / f"{spec.key}.meta.json"
        prior = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        if raw_path.exists() and prior and not force:
            prior["reused"] = True
            return FetchResult(**prior)
        headers = {"User-Agent": self.user_agent, "Accept": "text/csv,*/*;q=0.8"}
        if prior and not force:
            if prior.get("etag"):
                headers["If-None-Match"] = prior["etag"]
            if prior.get("last_modified"):
                headers["If-Modified-Since"] = prior["last_modified"]
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                req = Request(spec.url, headers=headers)
                with urlopen(req, timeout=self.timeout) as response:  # noqa: S310 - configured public CSV source
                    data = response.read()
                    status = int(getattr(response, "status", 200))
                    sha = hashlib.sha256(data).hexdigest()
                    tmp = raw_path.with_suffix(".csv.tmp")
                    tmp.write_bytes(data)
                    tmp.replace(raw_path)
                    result = FetchResult(
                        spec.key,
                        spec.url,
                        status,
                        response.headers.get("content-type"),
                        str(raw_path),
                        str(meta_path),
                        sha,
                        len(data),
                        datetime.now(UTC).isoformat(),
                        response.headers.get("etag"),
                        response.headers.get("last-modified"),
                        False,
                    )
                    meta_path.write_text(
                        json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    return result
            except HTTPError as exc:
                if exc.code == 304 and raw_path.exists() and prior:
                    prior["reused"] = True
                    return FetchResult(**prior)
                last_error = exc
            except (URLError, TimeoutError, OSError) as exc:
                last_error = exc
            if attempt < self.retries:
                time.sleep(self.sleep_sec * attempt)
        raise RuntimeError(f"fetch failed game={spec.key} url={spec.url}: {last_error}")
