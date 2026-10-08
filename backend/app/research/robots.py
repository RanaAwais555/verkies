"""robots.txt policy for VROSBot (SECURITY.md §3). Missing robots.txt means allowed."""

from dataclasses import dataclass, field
from urllib.robotparser import RobotFileParser

BOT_NAME = "VROSBot"
MAX_CRAWL_DELAY_SECONDS = 10.0


@dataclass
class RobotsPolicy:
    parser: RobotFileParser | None = None
    sitemaps: list[str] = field(default_factory=list)
    # Why the policy is what it is: "missing", "parsed", "unreachable", "forbidden".
    source: str = "missing"

    @classmethod
    def parse(cls, text: str) -> "RobotsPolicy":
        parser = RobotFileParser()
        parser.parse(text.splitlines())
        return cls(parser=parser, sitemaps=list(parser.site_maps() or []), source="parsed")

    @classmethod
    def deny_all(cls, source: str) -> "RobotsPolicy":
        parser = RobotFileParser()
        parser.parse(["User-agent: *", "Disallow: /"])
        return cls(parser=parser, source=source)

    def allows(self, url: str) -> bool:
        return self.parser is None or self.parser.can_fetch(BOT_NAME, url)

    def crawl_delay(self) -> float | None:
        if self.parser is None:
            return None
        delay = self.parser.crawl_delay(BOT_NAME)
        return min(float(delay), MAX_CRAWL_DELAY_SECONDS) if delay is not None else None
