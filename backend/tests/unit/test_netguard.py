import pytest

from app.providers.fetch.netguard import check_ip, parse_networks, parse_url, resolve_target
from app.providers.fetch.types import FetchBlocked, FetchFailed

PORTS = frozenset({80, 443})


class FakeResolver:
    def __init__(self, answers: dict[str, list[str]]) -> None:
        self.answers = answers
        self.calls: list[str] = []

    async def resolve(self, host: str, port: int) -> list[str]:
        self.calls.append(host)
        return self.answers.get(host, [])


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.1.2.3",
        "172.16.5.4",
        "192.168.1.1",
        "169.254.169.254",  # cloud metadata
        "100.64.0.1",  # carrier-grade NAT
        "0.0.0.0",  # noqa: S104 - an address under test, not a bind
        "224.0.0.1",  # multicast
        "240.0.0.1",  # reserved
        "::1",
        "fc00::1",  # unique local
        "fe80::1",  # link local
        "::ffff:127.0.0.1",  # IPv4-mapped loopback
        "::ffff:169.254.169.254",
        "2002:7f00:1::",  # 6to4 wrapping 127.0.0.1
        "::",
    ],
)
def test_non_public_addresses_are_refused(ip: str) -> None:
    with pytest.raises(FetchBlocked) as caught:
        check_ip(ip)
    assert caught.value.code == "non_public_address"


@pytest.mark.parametrize("ip", ["93.184.216.34", "1.1.1.1", "2606:4700:4700::1111"])
def test_public_addresses_pass(ip: str) -> None:
    check_ip(ip)


def test_allowlist_opens_only_listed_networks() -> None:
    allow = parse_networks(["127.0.0.0/8"])
    check_ip("127.0.0.1", allow)
    with pytest.raises(FetchBlocked):
        check_ip("169.254.169.254", allow)


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("ftp://example.com/", "bad_scheme"),
        ("file:///etc/passwd", "bad_scheme"),
        ("gopher://example.com/", "bad_scheme"),
        ("https://user:pw@example.com/", "credentials_in_url"),
        ("https://example.com:8080/", "bad_port"),
        ("https://example.com:22/", "bad_port"),
        ("https:///nohost", "bad_url"),
        ("http://[::1/", "bad_url"),
    ],
)
def test_url_policy(url: str, code: str) -> None:
    with pytest.raises(FetchBlocked) as caught:
        parse_url(url, allowed_ports=PORTS)
    assert caught.value.code == code


def test_unicode_hosts_are_idna_encoded() -> None:
    _, _, host, port = parse_url("https://bücher.example/", allowed_ports=PORTS)
    assert host == "xn--bcher-kva.example" and port == 443


async def test_a_single_private_answer_blocks_the_host() -> None:
    resolver = FakeResolver({"mixed.test": ["93.184.216.34", "10.0.0.5"]})
    with pytest.raises(FetchBlocked):
        await resolve_target("https://mixed.test/", resolver=resolver, allowed_ports=PORTS)


async def test_literal_ip_urls_are_checked_without_dns() -> None:
    resolver = FakeResolver({})
    with pytest.raises(FetchBlocked):
        await resolve_target(
            "http://169.254.169.254/latest/", resolver=resolver, allowed_ports=PORTS
        )
    with pytest.raises(FetchBlocked):
        await resolve_target("http://[::1]/", resolver=resolver, allowed_ports=PORTS)
    assert resolver.calls == []


async def test_no_dns_answer_fails() -> None:
    with pytest.raises(FetchFailed):
        await resolve_target("https://nx.test/", resolver=FakeResolver({}), allowed_ports=PORTS)


async def test_target_pins_ip_and_keeps_host() -> None:
    resolver = FakeResolver({"example.com": ["93.184.216.34"]})
    target = await resolve_target(
        "https://Example.com/a/b?q=1#frag", resolver=resolver, allowed_ports=PORTS
    )
    assert target.ip_url == "https://93.184.216.34/a/b?q=1"
    assert target.host_header == "example.com"
