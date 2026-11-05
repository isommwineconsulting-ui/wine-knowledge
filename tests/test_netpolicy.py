"""Network policy negative and positive contract tests."""
import socket

import pytest

from wine_knowledge.netpolicy import validate_source_url, validated_redirect


def _public_dns(*args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", 443))]


def _private_dns(*args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]


@pytest.mark.parametrize("url", [
    "http://example.org/a.pdf",
    "https://127.0.0.1/a.pdf",
    "https://example.org.evil.test/a.pdf",
    "https://user:pw@example.org/a.pdf",
    "https://example.org:8443/a.pdf",
    "file:///etc/passwd",
])
def test_rejects_unapproved_or_unsafe_urls(monkeypatch, url):
    monkeypatch.setattr(socket, "getaddrinfo", _public_dns)
    with pytest.raises(ValueError):
        validate_source_url(url, ("example.org",))


def test_rejects_private_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _private_dns)
    with pytest.raises(ValueError):
        validate_source_url("https://example.org/a.pdf", ("example.org",))


def test_validates_redirect_target(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _public_dns)
    assert validate_source_url("https://example.org/a.pdf", ("example.org",))
    with pytest.raises(ValueError):
        validated_redirect("https://example.org/a.pdf",
                           "https://internal.example/b.pdf", ("example.org",))
