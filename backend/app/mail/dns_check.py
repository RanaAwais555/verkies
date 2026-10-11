"""DNS checks for sending (master context §12B.1 and §12B.6, slice 3.4).

On connect VROS checks the sender's domain for SPF, DKIM and DMARC and an MX record, and says what
to fix; sending is allowed only when all four pass. Before each email it checks the recipient's
domain has an MX record. Lookups go through `DnsChecker`, so tests use a fake.
"""

from dataclasses import asdict, dataclass
from typing import Literal, Protocol

import dns.asyncresolver
import dns.exception
import dns.resolver

CheckStatus = Literal["pass", "fail", "unknown"]
CHECKS = ("mx", "spf", "dkim", "dmarc")
TIMEOUT = 4.0


class DnsUnavailable(Exception):
    """The lookup itself failed (timeout, no nameserver): the answer is unknown, not "no"."""


class DnsChecker(Protocol):
    async def txt(self, name: str) -> list[str]: ...
    async def mx(self, domain: str) -> list[str]: ...


class DnsPythonChecker:
    """Real lookups with dnspython. An empty list means the name has no such record."""

    def __init__(self) -> None:
        self.resolver = dns.asyncresolver.Resolver()
        self.resolver.lifetime = TIMEOUT

    async def _query(self, name: str, kind: str) -> list[str]:
        try:
            answer = await self.resolver.resolve(name, kind)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return []
        except (dns.exception.Timeout, dns.resolver.NoNameservers) as exc:
            raise DnsUnavailable(str(exc)) from exc
        if kind == "TXT":
            return [b"".join(r.strings).decode(errors="replace") for r in answer]
        return [str(r.exchange).rstrip(".") for r in answer]

    async def txt(self, name: str) -> list[str]:
        return await self._query(name, "TXT")

    async def mx(self, domain: str) -> list[str]:
        return await self._query(domain, "MX")


@dataclass
class Check:
    status: CheckStatus
    record: str | None = None
    advice: str | None = None


def domain_of(address: str) -> str:
    return address.rsplit("@", 1)[-1].strip().lower()


async def _txt_starting(checker: DnsChecker, name: str, prefix: str) -> list[str]:
    return [r for r in await checker.txt(name) if r.lower().startswith(prefix.lower())]


async def check_sender_domain(
    checker: DnsChecker, domain: str, dkim_selector: str | None
) -> dict[str, dict[str, str | None]]:
    """SPF, DKIM, DMARC and MX for the domain a mailbox sends from, each with advice to fix it."""
    results: dict[str, Check] = {}

    async def guarded(key: str, run: object) -> None:
        try:
            results[key] = await run  # type: ignore[misc]
        except DnsUnavailable:
            results[key] = Check("unknown", advice="The DNS lookup failed. Check again later.")

    async def mx() -> Check:
        hosts = await checker.mx(domain)
        if hosts:
            return Check("pass", ", ".join(sorted(hosts)))
        return Check("fail", advice=f"{domain} has no MX record, so replies cannot reach it.")

    async def spf() -> Check:
        found = await _txt_starting(checker, domain, "v=spf1")
        if not found:
            return Check(
                "fail",
                advice=f"Add a TXT record on {domain}: v=spf1 include:<your mail provider> ~all.",
            )
        if len(found) > 1:
            return Check(
                "fail", "; ".join(found), "There are several SPF records. Merge them into one."
            )
        if found[0].replace(" ", "").endswith("+all"):
            return Check("fail", found[0], "SPF ends in +all, which lets anyone send as you.")
        return Check("pass", found[0])

    async def dmarc() -> Check:
        found = await _txt_starting(checker, f"_dmarc.{domain}", "v=DMARC1")
        if not found:
            return Check(
                "fail",
                advice=f"Add a TXT record on _dmarc.{domain}: v=DMARC1; p=none; "
                "rua=mailto:<an address you read>.",
            )
        return Check("pass", found[0])

    async def dkim() -> Check:
        if not dkim_selector:
            return Check(
                "fail",
                advice="Enter your DKIM selector (your mail provider shows it, e.g. google or "
                "selector1) so VROS can check the key.",
            )
        name = f"{dkim_selector}._domainkey.{domain}"
        found = [r for r in await checker.txt(name) if "p=" in r.replace(" ", "")]
        if not found or found[0].replace(" ", "").rstrip(";").endswith("p="):
            return Check("fail", advice=f"No DKIM key at {name}. Turn on DKIM with your provider.")
        return Check("pass", found[0][:120])

    for key, run in (("mx", mx()), ("spf", spf()), ("dkim", dkim()), ("dmarc", dmarc())):
        await guarded(key, run)
    return {k: asdict(results[k]) for k in CHECKS}


def all_pass(checks: dict[str, dict[str, str | None]]) -> bool:
    return bool(checks) and all(checks.get(k, {}).get("status") == "pass" for k in CHECKS)


async def accepts_mail(checker: DnsChecker, domain: str) -> CheckStatus:
    """Whether a recipient's domain can receive email at all (it has an MX record)."""
    try:
        return "pass" if await checker.mx(domain) else "fail"
    except DnsUnavailable:
        return "unknown"
