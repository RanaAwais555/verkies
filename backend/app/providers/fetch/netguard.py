"""SSRF protection: decide whether a URL may be fetched and which IP to connect to.

The fetcher resolves a hostname once, refuses it unless every address is public, then
connects to that exact address. A second DNS answer (rebinding) is never consulted.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import SplitResult, urlsplit

from app.providers.fetch.types import FetchBlocked, FetchFailed

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

ALLOWED_SCHEMES = frozenset({"http", "https"})
DEFAULT_PORTS = {"http": 80, "https": 443}


class Resolver(Protocol):
    async def resolve(self, host: str, port: int) -> list[str]: ...


class SystemResolver:
    async def resolve(self, host: str, port: int) -> list[str]:
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise FetchFailed(f"DNS lookup failed for {host}", code="dns_failed") from exc
        return list(dict.fromkeys(str(info[4][0]) for info in infos))


@dataclass(frozen=True)
class Target:
    """A URL that passed the policy, with the address to connect to."""

    url: SplitResult
    scheme: str
    host: str  # IDNA-encoded, lower case
    port: int
    ip: str

    @property
    def ip_url(self) -> str:
        """The same URL with the host replaced by the pinned IP."""
        host = f"[{self.ip}]" if ":" in self.ip else self.ip
        default = DEFAULT_PORTS[self.scheme]
        netloc = host if self.port == default else f"{host}:{self.port}"
        return self.url._replace(netloc=netloc, fragment="").geturl()

    @property
    def host_header(self) -> str:
        default = DEFAULT_PORTS[self.scheme]
        return self.host if self.port == default else f"{self.host}:{self.port}"


def is_public_ip(ip: IPAddress) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return is_public_ip(ip.ipv4_mapped)
    if isinstance(ip, ipaddress.IPv6Address) and ip.sixtofour is not None:
        return is_public_ip(ip.sixtofour)
    return ip.is_global and not ip.is_multicast and not ip.is_reserved


def parse_networks(cidrs: Iterable[str]) -> tuple[IPNetwork, ...]:
    return tuple(ipaddress.ip_network(c, strict=False) for c in cidrs)


def check_ip(raw: str, allowlist: tuple[IPNetwork, ...] = ()) -> IPAddress:
    try:
        ip = ipaddress.ip_address(raw.split("%", 1)[0])  # drop IPv6 zone id
    except ValueError as exc:
        raise FetchBlocked(f"Not an IP address: {raw}", code="bad_address") from exc
    if any(ip in net for net in allowlist):
        return ip
    if not is_public_ip(ip):
        raise FetchBlocked(
            "Refused: the address is private, local or reserved.", code="non_public_address"
        )
    return ip


def parse_url(url: str, *, allowed_ports: frozenset[int]) -> tuple[SplitResult, str, str, int]:
    """Policy checks that need no network: scheme, credentials, host, port."""
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError as exc:
        raise FetchBlocked("Malformed URL.", code="bad_url") from exc
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise FetchBlocked("Only http and https URLs can be fetched.", code="bad_scheme")
    if parts.username is not None or parts.password is not None:
        raise FetchBlocked("URLs with credentials are not allowed.", code="credentials_in_url")
    if not parts.hostname:
        raise FetchBlocked("The URL has no host.", code="bad_url")
    try:
        host = parts.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise FetchBlocked("The host name is not valid.", code="bad_url") from exc
    port = port or DEFAULT_PORTS[scheme]
    if port not in allowed_ports:
        raise FetchBlocked(f"Port {port} is not allowed.", code="bad_port")
    return parts._replace(scheme=scheme), scheme, host, port


async def resolve_target(
    url: str,
    *,
    resolver: Resolver,
    allowed_ports: frozenset[int],
    allowlist: tuple[IPNetwork, ...] = (),
) -> Target:
    parts, scheme, host, port = parse_url(url, allowed_ports=allowed_ports)
    try:
        literal: IPAddress | None = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    addresses = [str(literal)] if literal else await resolver.resolve(host, port)
    if not addresses:
        raise FetchFailed(f"DNS returned no addresses for {host}", code="dns_failed")
    # Every address must pass, or an attacker could mix a public and a private answer.
    for address in addresses:
        check_ip(address, allowlist)
    return Target(url=parts, scheme=scheme, host=host, port=port, ip=addresses[0])
