"""Concurrency-safe Oura OAuth token handling.

Oura refresh tokens are single-use. The service can issue several API requests at once,
so multiple workers must never refresh the same token concurrently.
"""
from __future__ import annotations

import threading
import time
from typing import Any

import httpx

import oura_service


_REFRESH_LOCK = threading.Lock()


def _refresh_tokens_safe(tokens: dict[str, Any]) -> str:
    """Refresh once and preserve Oura's rotated refresh token."""
    refresh_token = str(tokens.get("refresh_token") or "")
    if not refresh_token:
        raise RuntimeError("No Oura refresh token is available. Re-authorize the application.")

    refreshed = oura_service._token_request({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": oura_service.CLIENT_ID,
        "client_secret": oura_service.CLIENT_SECRET,
    })

    # Oura rotates refresh tokens. Never discard the previous token if a response
    # happens to omit it.
    if not refreshed.get("refresh_token"):
        refreshed["refresh_token"] = refresh_token
    refreshed["obtained_at"] = time.time()
    oura_service._save_tokens(refreshed)
    return str(refreshed["access_token"])


def access_token(force_refresh: bool = False) -> str:
    tokens = oura_service._load_tokens()
    if not tokens or not tokens.get("access_token"):
        raise RuntimeError("Oura is not connected. Open /oauth/start or call authorize_oura first.")

    expires_at = float(tokens.get("obtained_at", 0)) + float(tokens.get("expires_in", 0))
    if not force_refresh and expires_at - time.time() >= 90:
        return str(tokens["access_token"])

    with _REFRESH_LOCK:
        # Another worker may have refreshed while we waited.
        latest = oura_service._load_tokens() or tokens
        latest_expires = float(latest.get("obtained_at", 0)) + float(latest.get("expires_in", 0))
        if not force_refresh and latest_expires - time.time() >= 90:
            return str(latest["access_token"])
        return _refresh_tokens_safe(latest)


def request(url: str, params: dict[str, Any] | None = None) -> httpx.Response:
    """Make an Oura request with safe 401 recovery and bounded 429 retry."""
    token = access_token()
    params = params or {}

    for attempt in range(3):
        response = httpx.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )

        if response.status_code == 401:
            # Serialize refreshes. If another request already refreshed the token,
            # reuse its new access token instead of consuming the refresh token again.
            with _REFRESH_LOCK:
                latest = oura_service._load_tokens() or {}
                latest_access = str(latest.get("access_token") or "")
                if latest_access and latest_access != token:
                    token = latest_access
                else:
                    token = _refresh_tokens_safe(latest)
            continue

        if response.status_code == 429:
            if attempt >= 2:
                retry_after = response.headers.get("Retry-After", "unknown")
                raise RuntimeError(f"Oura rate limit reached. Retry-After: {retry_after}")
            try:
                delay = min(max(float(response.headers.get("Retry-After", "1")), 0.5), 15.0)
            except ValueError:
                delay = 2.0 * (attempt + 1)
            time.sleep(delay)
            continue

        response.raise_for_status()
        return response

    raise RuntimeError("Oura request failed after authentication recovery attempts.")


def install() -> None:
    """Install the hardened implementations into the existing Oura service."""
    oura_service._access_token = access_token
    oura_service._request = request
