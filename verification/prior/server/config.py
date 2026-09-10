import os
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class Settings:
    database_url: str
    origin: str
    issuer: str
    client_id: str
    client_secret: str
    owner_subject: str
    local_test: bool = False
    session_seconds: int = 28800

    def __post_init__(self) -> None:
        if not all(
            (
                self.database_url,
                self.origin,
                self.issuer,
                self.client_id,
                self.client_secret,
                self.owner_subject,
            )
        ):
            raise ValueError("Database, OIDC client and pinned owner configuration are required")
        if self.local_test:
            if any(
                urlparse(u).hostname not in {"127.0.0.1", "localhost"}
                for u in (self.origin, self.issuer)
            ):
                raise ValueError("Test OIDC requires loopback app and provider origins")
        elif self.issuer != "https://accounts.google.com" or not self.origin.startswith("https://"):
            raise ValueError("Production requires Google issuer and an HTTPS app origin")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ["DATABASE_URL"],
            origin=os.environ["APP_ORIGIN"].rstrip("/"),
            issuer=os.getenv("OIDC_ISSUER", "https://accounts.google.com"),
            client_id=os.environ["OIDC_CLIENT_ID"],
            client_secret=os.environ["OIDC_CLIENT_SECRET"],
            owner_subject=os.environ["OWNER_SUBJECT"],
            local_test=os.getenv("LOCAL_TEST_OIDC") == "1",
        )
