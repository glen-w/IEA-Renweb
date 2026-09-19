"""HTTP JSON helper for the optional World Bank and IRENA extras."""

from __future__ import annotations

import time
from typing import Any

from renweb.ingest.pipeline import IngestError

_ATTEMPTS = 3
_TIMEOUT = 60.0


def _load_httpx() -> Any:
    try:
        import httpx
    except ImportError as exc:
        raise IngestError("httpx is not installed") from exc
    return httpx


def request_json(
    extra: str,
    extra_label: str,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    """GET or POST JSON. Raises ``IngestError`` when the extra is missing."""
    try:
        httpx = _load_httpx()
    except IngestError as exc:
        raise IngestError(
            f"{extra_label} ingest needs the {extra} extra: uv sync --extra {extra}"
        ) from exc
    last_error: Exception | None = None
    for attempt in range(_ATTEMPTS):
        try:
            response = httpx.request(
                method,
                url,
                params=params,
                json=json_body,
                timeout=_TIMEOUT,
                follow_redirects=True,
            )
            if response.status_code == 429 and attempt < _ATTEMPTS - 1:
                time.sleep(2**attempt)
                continue
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt < _ATTEMPTS - 1:
                time.sleep(2**attempt)
                continue
            raise IngestError(f"{extra_label} request failed: {exc}") from exc
    raise IngestError(f"{extra_label} request failed: {last_error}") from last_error
