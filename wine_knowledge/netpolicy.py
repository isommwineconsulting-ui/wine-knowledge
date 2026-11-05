"""Restrict outbound fetches to approved public HTTPS endpoints.

Defense in depth, not proof against DNS rebinding without network egress rules.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit, urljoin

MAX_REDIRECTS = 4


def validate_source_url(url: str, allowed_hosts: tuple[str, ...]) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme.lower() != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or host not in allowed_hosts
    ):
        raise ValueError("Source URL must be HTTPS on an explicitly approved host")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP-literal hosts are not permitted")

    try:
        answers = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Source hostname does not resolve") from exc
    if not answers or any(
        not ipaddress.ip_address(answer[4][0]).is_global for answer in answers
    ):
        raise ValueError("Source host resolves to a non-public address")
    return url


def validated_redirect(current: str, location: str, allowed_hosts: tuple[str, ...]) -> str:
    if not location:
        raise ValueError("Redirect missing Location")
    return validate_source_url(urljoin(current, location), allowed_hosts)
