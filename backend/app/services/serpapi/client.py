"""SerpApi HTTP client: timeout, bounded retries, error mapping. Pure transport, no caching.

Network access goes through an injected `SerpTransport`, so tests and CI use a scripted fake and
never touch the network. The default `UrllibTransport` uses only the standard library (no new
dependency). The client refuses to run unless `allow_live=True`, as a second line of defence
behind `usage.MonthlyQuota.check_live` (ALLOW_LIVE_SERPAPI is false by default).

The API key is only ever placed in the outgoing request. It never appears in exceptions, `repr`
output or logs.
"""

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from app.schemas.serp import QuerySpec
from app.services.serpapi.parsers.common import is_no_results_error, response_error
from app.services.serpapi.sanitize import redact_text

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search.json"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_RETRIES = 2
_MAX_BACKOFF_SECONDS = 30.0
_MAX_ERROR_CHARS = 200


@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    body: Any  # parsed JSON, or None when the body was not JSON
    retry_after: float | None = None


class SerpTransport(Protocol):
    def get(self, url: str, params: Mapping[str, str], timeout: float) -> TransportResponse: ...


# --- errors ------------------------------------------------------------------------------------


class SerpApiClientError(Exception):
    """Base class. `retryable` errors are retried with backoff; the rest surface immediately."""

    code = "serpapi_error"
    retryable = False

    def __init__(self, message: str, *, http_status: int | None = None) -> None:
        super().__init__(redact_text(message))
        self.http_status = http_status
        self.attempts = 0


class SerpApiLiveDisabled(SerpApiClientError):
    code = "live_data_disabled"


class SerpApiNotConfigured(SerpApiClientError):
    code = "serpapi_not_configured"


class SerpApiAuthError(SerpApiClientError):
    """401/403: bad or revoked key. Never retried; the caller stops all live calls."""

    code = "serpapi_auth_failed"


class SerpApiAccountQuotaExhausted(SerpApiClientError):
    """SerpApi says the account is out of searches. Not transient: never retried."""

    code = "serpapi_account_quota_exhausted"


class SerpApiBadRequest(SerpApiClientError):
    code = "serpapi_bad_request"


class SerpApiResponseError(SerpApiClientError):
    """A 2xx response that is not a usable JSON object or carries an error payload."""

    code = "serpapi_bad_response"


class SerpApiRateLimited(SerpApiClientError):
    code = "serpapi_rate_limited"
    retryable = True

    def __init__(
        self, message: str, *, http_status: int | None = 429, retry_after: float | None = None
    ) -> None:
        super().__init__(message, http_status=http_status)
        self.retry_after = retry_after


class SerpApiServerError(SerpApiClientError):
    code = "serpapi_server_error"
    retryable = True


class SerpApiTimeout(SerpApiClientError):
    code = "serpapi_timeout"
    retryable = True


class SerpApiNetworkError(SerpApiClientError):
    code = "serpapi_network_error"
    retryable = True


# --- transport ---------------------------------------------------------------------------------


class UrllibTransport:
    """Standard-library transport. The only place in the codebase that opens a connection."""

    def get(self, url: str, params: Mapping[str, str], timeout: float) -> TransportResponse:
        if not url.startswith("https://"):
            raise SerpApiBadRequest("SerpApi requests must use https")
        request = urllib.request.Request(
            f"{url}?{urllib.parse.urlencode(params)}",
            headers={"Accept": "application/json", "User-Agent": "brandpulse-backend"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as handle:
                return TransportResponse(handle.status, _decode(handle.read()))
        except urllib.error.HTTPError as exc:
            header = exc.headers.get("Retry-After") if exc.headers else None
            return TransportResponse(exc.code, _decode(exc.read()), _parse_retry_after(header))
        except TimeoutError as exc:
            raise SerpApiTimeout("SerpApi request timed out") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise SerpApiTimeout("SerpApi request timed out") from exc
            raise SerpApiNetworkError("SerpApi request failed (network error)") from exc
        except OSError as exc:
            raise SerpApiNetworkError("SerpApi request failed (network error)") from exc


def _decode(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None


def _parse_retry_after(value: str | None) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


# --- client ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ClientResult:
    response: dict[str, Any]
    http_status: int
    attempts: int


class SerpApiClient:
    def __init__(
        self,
        *,
        api_key: str,
        allow_live: bool,
        transport: SerpTransport | None = None,
        base_url: str = SERPAPI_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._allow_live = allow_live
        self._transport: SerpTransport = transport or UrllibTransport()
        self._base_url = base_url
        self._timeout = timeout
        self._max_retries = max(0, max_retries)
        self._backoff_base = backoff_base
        self._sleep = sleep

    def __repr__(self) -> str:
        return f"SerpApiClient(allow_live={self._allow_live}, api_key=<hidden>)"

    def fetch(self, spec: QuerySpec) -> ClientResult:
        """Run one request. Raises `SerpApiClientError` subclasses; never returns an error body.

        A "no results" payload is a valid (empty) result, not an error.
        """
        if not self._allow_live:
            raise SerpApiLiveDisabled("live SerpApi calls are disabled (ALLOW_LIVE_SERPAPI=false)")
        if not self._api_key:
            raise SerpApiNotConfigured("SERPAPI_API_KEY is not set")

        params = {key: _to_param(value) for key, value in spec.params.items()}
        params["engine"] = str(spec.engine)
        params["api_key"] = self._api_key

        attempts = 0
        while True:
            attempts += 1
            try:
                raw = self._transport.get(self._base_url, params, self._timeout)
                body, status = self._interpret(raw)
                return ClientResult(body, status, attempts)
            except SerpApiClientError as exc:
                exc.attempts = attempts
                if not exc.retryable or attempts > self._max_retries:
                    raise
                delay = self._delay(exc, attempts)
                logger.warning(
                    "serpapi_retry",
                    extra={"engine": str(spec.engine), "code": exc.code, "attempt": attempts},
                )
                self._sleep(delay)

    def _delay(self, exc: SerpApiClientError, attempt: int) -> float:
        hinted = exc.retry_after if isinstance(exc, SerpApiRateLimited) else None
        delay = hinted if hinted is not None else self._backoff_base * 2 ** (attempt - 1)
        return min(max(delay, 0.0), _MAX_BACKOFF_SECONDS)

    @staticmethod
    def _interpret(raw: TransportResponse) -> tuple[dict[str, Any], int]:
        status = raw.status_code
        body = raw.body if isinstance(raw.body, dict) else None
        message = _error_text(body)

        if 200 <= status < 300:
            if body is None:
                raise SerpApiResponseError(
                    "SerpApi returned a non-JSON or non-object body", http_status=status
                )
            error = response_error(body)
            if error is not None and not is_no_results_error(error):
                raise SerpApiResponseError(f"SerpApi error payload: {message}", http_status=status)
            return body, status
        if status in (401, 403):
            raise SerpApiAuthError(f"SerpApi rejected the API key: {message}", http_status=status)
        if status == 429:
            if _is_account_exhausted(message):
                raise SerpApiAccountQuotaExhausted(message, http_status=status)
            raise SerpApiRateLimited(message, retry_after=raw.retry_after)
        if status >= 500:
            raise SerpApiServerError(f"SerpApi server error: {message}", http_status=status)
        raise SerpApiBadRequest(f"SerpApi rejected the request: {message}", http_status=status)


def _to_param(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _error_text(body: Mapping[str, Any] | None) -> str:
    error = response_error(body) if body is not None else None
    return redact_text(error or "no error message")[:_MAX_ERROR_CHARS]


def _is_account_exhausted(message: str) -> bool:
    lowered = message.casefold()
    return "run out of searches" in lowered or "searches per month" in lowered
