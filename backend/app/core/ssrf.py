"""SSRF guards for outbound HTTP.

Any admin/manager can save a domain whose ``base_url`` resolves to an internal
host (cloud metadata, Redis, Postgres, RFC1918 LANs). When the app makes a
request to that URL — Test connection, publish, /wp-json/* discovery, or media
download — it would happily exfiltrate or reach into the network from the
backend container's perspective.

This module supplies:

- ``validate_public_url(url)`` — sync URL+DNS pre-check used at form-submit
  time and right before each outbound request. Rejects non-http(s), unknown
  hosts, and any host that resolves to a private / loopback / link-local /
  multicast / reserved IP, including the AWS IMDS, GCP metadata, and IPv6
  ULA / link-local equivalents.

- ``SafeAsyncTransport`` — an httpx ``AsyncBaseTransport`` that revalidates
  every redirected URL before sending. Even with ``follow_redirects=True``
  set on a client, an attacker can't bounce us to ``http://169.254.169.254``
  via a 302 from an external host, because the transport's ``handle_async_request``
  re-runs ``validate_public_url`` on the per-request URL.

- ``stream_to_buffer(response, max_bytes)`` — read an httpx response in chunks
  and abort once the byte count exceeds the cap, instead of letting
  ``response.content`` buffer the entire body before the size check.

Use these consistently anywhere outbound HTTP touches a user-controlled URL.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

import httpx


class UnsafeUrlError(ValueError):
    """Raised when a URL targets a non-public address or is malformed."""


_DENY_HOSTNAMES = {
    # Cloud metadata services. The IPs are caught by IP checks; we also block
    # the well-known DNS names defensively in case DNS is intercepted in some
    # exotic deployment.
    "metadata.google.internal",
    "metadata",
    "metadata.goog",
    "instance-data",
    "instance-data.ec2.internal",
}


def _ip_is_public(ip: ipaddress._BaseAddress) -> bool:
    """Reject anything that isn't a routable, public-internet address."""
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return False
    # IPv6 unique-local addresses (fc00::/7) — `is_private` already covers
    # them in stdlib's IPv6Address, but make the intent explicit.
    if isinstance(ip, ipaddress.IPv6Address):
        # IPv4-mapped (::ffff:0:0/96) — re-check the embedded v4 address.
        if ip.ipv4_mapped is not None:
            return _ip_is_public(ip.ipv4_mapped)
        # Site-local (fec0::/10) — deprecated but still treated as private.
        if int(ip) >> (128 - 10) == 0xFEC >> 2:
            return False
    return True


def validate_public_url(url: str) -> None:
    """Raise :class:`UnsafeUrlError` if ``url`` doesn't target a public host.

    Checks performed:
      - scheme is http or https
      - host is present
      - host is not a known cloud-metadata hostname
      - host's resolved A/AAAA records all map to public addresses
        (DNS rebind is mitigated because the same check runs again at
        request time via :class:`SafeAsyncTransport`).
    """
    if not url or not isinstance(url, str):
        raise UnsafeUrlError("url must be a non-empty string")
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https"):
        raise UnsafeUrlError(f"unsupported scheme {parts.scheme!r}")
    host = parts.hostname
    if not host:
        raise UnsafeUrlError("url has no host")
    if host.lower() in _DENY_HOSTNAMES:
        raise UnsafeUrlError(f"host {host!r} is denied")

    # Try interpreting the host as a literal IP first — skip DNS in that case
    # so an attacker can't slide a numeric IPv4/IPv6 past a DNS-only check.
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None

    if ip is not None:
        if not _ip_is_public(ip):
            raise UnsafeUrlError(f"host {host!r} resolves to a non-public address")
        return

    # DNS resolution. socket.getaddrinfo returns A and AAAA records together.
    try:
        infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80))
    except socket.gaierror as e:
        raise UnsafeUrlError(f"could not resolve host {host!r}: {e}") from e

    if not infos:
        raise UnsafeUrlError(f"could not resolve host {host!r}")

    for info in infos:
        sockaddr = info[4]
        addr_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(addr_str)
        except ValueError:
            raise UnsafeUrlError(f"unparseable address {addr_str!r} for {host!r}")
        if not _ip_is_public(addr):
            raise UnsafeUrlError(
                f"host {host!r} resolves to a non-public address ({addr_str})"
            )


class SafeAsyncTransport(httpx.AsyncBaseTransport):
    """httpx transport that re-runs SSRF checks on every request.

    Wrap with this whenever ``follow_redirects=True`` is set on an httpx client
    that may receive a user-controlled URL. Each followed redirect arrives here
    as a fresh request and is re-validated before bytes go out.
    """

    def __init__(self, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self._inner = inner or httpx.AsyncHTTPTransport()

    async def handle_async_request(
        self, request: httpx.Request
    ) -> httpx.Response:
        validate_public_url(str(request.url))
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


async def stream_to_buffer(
    response: httpx.Response, *, max_bytes: int
) -> bytes:
    """Read an httpx streaming response and abort if it exceeds ``max_bytes``.

    The caller must open the response with ``client.stream(...)`` (or
    ``send(stream=True)``) for this to actually stream. Using it on a buffered
    response works but defeats the size protection.

    Raises :class:`UnsafeUrlError` if the body grows past the cap.
    """
    buf = bytearray()
    async for chunk in response.aiter_bytes():
        if len(buf) + len(chunk) > max_bytes:
            raise UnsafeUrlError(
                f"response body exceeds {max_bytes} bytes"
            )
        buf.extend(chunk)
    return bytes(buf)


__all__ = [
    "UnsafeUrlError",
    "validate_public_url",
    "SafeAsyncTransport",
    "stream_to_buffer",
]
