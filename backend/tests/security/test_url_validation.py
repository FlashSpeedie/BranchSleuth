import pytest

import app.services.security as security
from app.services.security import UrlValidationError, validate_git_url


@pytest.fixture(autouse=True)
def no_dns(monkeypatch):
    def fake_resolve(host):
        public = {
            "github.com": ["140.82.112.4"],
            "gitlab.com": ["104.192.141.1"],
            "bitbucket.org": ["104.192.143.10"],
        }
        if host in public:
            return public[host]
        if host == "private-host.example":
            return ["192.168.1.10"]
        if host == "metadata-host.example":
            return ["169.254.169.254"]
        if host == "ipv6-private.example":
            return ["::1"]
        if host == "link-local.example":
            return ["fe80::1"]
        raise UrlValidationError(f"could not resolve host: {host}")

    monkeypatch.setattr(security, "_resolve_all", fake_resolve)


def test_accepts_valid_github_url():
    parsed = validate_git_url("https://github.com/acme/widgets")
    assert parsed.owner == "acme"
    assert parsed.repo == "widgets"
    assert parsed.https_url == "https://github.com/acme/widgets.git"


def test_accepts_git_suffix_and_trailing_slash():
    parsed = validate_git_url("https://github.com/acme/widgets.git/")
    assert parsed.repo == "widgets"


def test_rejects_non_https():
    with pytest.raises(UrlValidationError):
        validate_git_url("http://github.com/acme/widgets")
    with pytest.raises(UrlValidationError):
        validate_git_url("git@github.com:acme/widgets.git")
    with pytest.raises(UrlValidationError):
        validate_git_url("ssh://git@github.com/acme/widgets.git")
    with pytest.raises(UrlValidationError):
        validate_git_url("ftp://github.com/acme/widgets")


def test_rejects_credentials_in_url():
    with pytest.raises(UrlValidationError):
        validate_git_url("https://user:pass@github.com/acme/widgets")
    with pytest.raises(UrlValidationError):
        validate_git_url("https://token@github.com/acme/widgets")


def test_rejects_unknown_host():
    with pytest.raises(UrlValidationError):
        validate_git_url("https://evil.example/acme/widgets")


def test_rejects_localhost_and_ip_literals():
    with pytest.raises(UrlValidationError):
        validate_git_url("https://localhost/acme/widgets")
    with pytest.raises(UrlValidationError):
        validate_git_url("https://127.0.0.1/acme/widgets")
    with pytest.raises(UrlValidationError):
        validate_git_url("https://192.168.0.1/acme/widgets")


def test_rejects_non_standard_port():
    with pytest.raises(UrlValidationError):
        validate_git_url("https://github.com:8443/acme/widgets")


def test_rejects_host_resolving_to_private_network(monkeypatch):
    monkeypatch.setattr("app.config.settings.allowed_git_hosts", "github.com,private-host.example,metadata-host.example,ipv6-private.example,link-local.example")
    with pytest.raises(UrlValidationError):
        validate_git_url("https://private-host.example/acme/widgets")
    with pytest.raises(UrlValidationError):
        validate_git_url("https://metadata-host.example/latest/meta-data")
    with pytest.raises(UrlValidationError):
        validate_git_url("https://ipv6-private.example/acme/widgets")
    with pytest.raises(UrlValidationError):
        validate_git_url("https://link-local.example/acme/widgets")


def test_rejects_unusual_paths():
    with pytest.raises(UrlValidationError):
        validate_git_url("https://github.com/acme/widgets/extra")
    with pytest.raises(UrlValidationError):
        validate_git_url("https://github.com/..")
    with pytest.raises(UrlValidationError):
        validate_git_url("https://github.com/acme/wi dgets")
    with pytest.raises(UrlValidationError):
        validate_git_url("https://github.com/acme/widgets?x=1")


def test_rejects_empty_and_control_characters():
    with pytest.raises(UrlValidationError):
        validate_git_url("")
    with pytest.raises(UrlValidationError):
        validate_git_url("https://github.com/acme/w\x00idgets")
