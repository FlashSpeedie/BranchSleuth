from __future__ import annotations

import ipaddress
import socket
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlparse

from app.config import settings


class UrlValidationError(ValueError):
    pass


@dataclass
class ParsedRepoUrl:
    host: str
    owner: str
    repo: str
    https_url: str


_PRIVATE_NETWORKS = [
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
        "fd00::/8",
    )
]


def _resolve_all(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError:
        raise UrlValidationError(f"could not resolve host: {host}")
    return [str(i[4][0]) for i in infos]


def validate_git_url(raw_url: str, extra_hosts: set[str] | None = None) -> ParsedRepoUrl:
    allowed = settings.allowed_host_set | (extra_hosts or set())
    url = raw_url.strip()
    if not url:
        raise UrlValidationError("repository URL is empty")
    if any(ord(c) < 32 for c in url):
        raise UrlValidationError("repository URL contains control characters")
    if "\\" in url or ".." in url or "@file" in url.lower() or "url=" in url.lower():
        raise UrlValidationError("repository URL contains unsafe characters")
    try:
        parsed = urlparse(url)
    except ValueError as e:
        raise UrlValidationError(f"malformed repository URL: {e}") from e
    if parsed.scheme != "https":
        raise UrlValidationError("only https:// repository URLs are supported")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise UrlValidationError("repository URL has no host")
    if host not in allowed:
        raise UrlValidationError(f"host is not in the allowlist: {host}")
    if "@" in url.split("//", 1)[-1]:
        raise UrlValidationError("credentials in repository URLs are not accepted")
    if parsed.port not in (None, 443):
        raise UrlValidationError(f"non-standard ports are not allowed: {parsed.port}")
    if parsed.query or parsed.fragment or parsed.params:
        raise UrlValidationError("query strings and fragments are not allowed in repository URLs")
    if any(c.isspace() for c in url):
        raise UrlValidationError("repository URL contains whitespace")
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise UrlValidationError("IP-literal hosts are not accepted")
    for resolved_ip in set(_resolve_all(host)):
        try:
            addr = ipaddress.ip_address(resolved_ip)
        except ValueError:
            continue
        if any(addr in net for net in _PRIVATE_NETWORKS) or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_reserved:
            raise UrlValidationError("repository host resolves to a non-public address")
    norm_host = unicodedata.normalize("NFKC", host)
    if norm_host != host:
        raise UrlValidationError("repository host contains unexpected characters")
    path_parts = [p for p in parsed.path.split("/") if p]
    if len(path_parts) != 2:
        raise UrlValidationError("expected repository path like /owner/repo")
    owner, repo = path_parts
    if not all(p.replace("-", "").replace("_", "").replace(".", "").isalnum() for p in (owner, repo)):
        raise UrlValidationError("invalid repository path characters")
    repo = repo[:-4] if repo.endswith(".git") else repo
    return ParsedRepoUrl(host=host, owner=owner, repo=repo, https_url=f"https://{host}/{owner}/{repo}.git")
