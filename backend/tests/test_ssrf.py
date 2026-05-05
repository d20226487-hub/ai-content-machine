"""Coverage for app.core.ssrf — the SSRF guard rail.

We can't ship a security check that admits ``http://169.254.169.254`` ever, so
the table-driven test below pins both the allow and deny lists.
"""
from __future__ import annotations

import socket
from typing import Iterable
from unittest.mock import patch

import httpx
import pytest

from app.core.ssrf import (
    SafeAsyncTransport,
    UnsafeUrlError,
    stream_to_buffer,
    validate_public_url,
)


def _resolve(addrs: Iterable[str]):
    """Return a fake getaddrinfo result that yields the given addrs."""

    def _fake(host, port, *args, **kwargs):
        out = []
        for a in addrs:
            family = socket.AF_INET6 if ":" in a else socket.AF_INET
            out.append((family, socket.SOCK_STREAM, 0, "", (a, port or 0)))
        return out

    return _fake


# --- pure URL/IP validation ---


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # AWS IMDS
        "http://169.254.169.254",
        "http://[fd00::1]/x",  # IPv6 ULA
        "http://[::1]",  # IPv6 loopback
        "http://127.0.0.1:8000",
        "http://10.0.0.5/",
        "http://192.168.1.1",
        "http://172.16.0.1",
        "http://0.0.0.0",
    ],
)
def test_literal_private_ip_rejected(url):
    with pytest.raises(UnsafeUrlError):
        validate_public_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/x",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "",
        "http://",
    ],
)
def test_bad_scheme_or_empty_rejected(url):
    with pytest.raises(UnsafeUrlError):
        validate_public_url(url)


def test_metadata_hostname_blocked_even_when_dns_lies():
    # If GCP metadata DNS resolved to a public IP somehow, the hostname check
    # must still bounce it.
    with patch("socket.getaddrinfo", _resolve(["8.8.8.8"])):
        with pytest.raises(UnsafeUrlError):
            validate_public_url("http://metadata.google.internal/x")


def test_resolves_private_ip_rejected():
    with patch("socket.getaddrinfo", _resolve(["10.1.2.3"])):
        with pytest.raises(UnsafeUrlError):
            validate_public_url("http://example.com/x")


def test_resolves_public_ip_allowed():
    with patch("socket.getaddrinfo", _resolve(["8.8.8.8"])):
        validate_public_url("https://example.com/x")  # no raise


def test_dns_failure_rejected():
    with patch(
        "socket.getaddrinfo", side_effect=socket.gaierror("no such host")
    ):
        with pytest.raises(UnsafeUrlError):
            validate_public_url("https://nonexistent.invalid/x")


def test_mixed_resolution_rejected_if_any_private():
    # If one of A/AAAA records is private, treat it as unsafe — DNS rebind /
    # split-horizon defense.
    with patch(
        "socket.getaddrinfo",
        _resolve(["8.8.8.8", "192.168.1.1"]),
    ):
        with pytest.raises(UnsafeUrlError):
            validate_public_url("http://example.com/x")


# --- SafeAsyncTransport revalidates each request, including redirects ---


@pytest.mark.asyncio
async def test_safe_transport_blocks_redirect_to_private(monkeypatch):
    """A 302 from a public origin pointing at IMDS must NOT be followed."""

    # First request goes to evil.example.com (public), responds with 302 to IMDS.
    # The transport's handle_async_request runs validate_public_url on each
    # request. First call passes (public DNS), second is the IMDS literal — raises.
    request_count = {"n": 0}

    class FakeInner(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            request_count["n"] += 1
            return httpx.Response(
                302,
                headers={"location": "http://169.254.169.254/latest/meta-data/"},
            )

        async def aclose(self):
            pass

    transport = SafeAsyncTransport(inner=FakeInner())

    # Make DNS for evil.example.com resolve public so the first request passes.
    with patch("socket.getaddrinfo", _resolve(["8.8.8.8"])):
        async with httpx.AsyncClient(
            transport=transport, follow_redirects=True
        ) as client:
            with pytest.raises(UnsafeUrlError):
                await client.get("http://evil.example.com/")

    # The redirect was attempted but blocked at the transport before send.
    assert request_count["n"] == 1


# --- stream_to_buffer aborts oversized bodies ---


class _ChunkedResponse:
    """Minimal stand-in for httpx.Response.aiter_bytes()."""

    def __init__(self, chunks):
        self._chunks = chunks

    async def aiter_bytes(self):
        for c in self._chunks:
            yield c


@pytest.mark.asyncio
async def test_stream_to_buffer_aborts_when_too_large():
    resp = _ChunkedResponse([b"x" * 1000, b"y" * 1000, b"z" * 1000])
    with pytest.raises(UnsafeUrlError):
        await stream_to_buffer(resp, max_bytes=1500)


@pytest.mark.asyncio
async def test_stream_to_buffer_returns_under_cap():
    resp = _ChunkedResponse([b"abc", b"def"])
    out = await stream_to_buffer(resp, max_bytes=1024)
    assert out == b"abcdef"
