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
        origin = urlparse(self.origin)
        if (
            not origin.hostname
            or origin.username
            or origin.password
            or origin.query
            or origin.fragment
            or origin.path
            or origin.scheme not in {"http", "https"}
        ):
            raise ValueError(
                "APP_ORIGIN must be an origin without path, credentials, query or fragment"
            )
        if self.session_seconds <= 0 or self.session_seconds > 28800:
            raise ValueError("Session lifetime must be between 1 and 28800 seconds")
        if os.getenv("APP_ENV") == "production" and self.local_test:
            raise ValueError("Production cannot enable synthetic identity")
        if not self.local_test:
            from sqlalchemy.engine import make_url

            if os.getenv("MIGRATION_DATABASE_URL"):
                raise ValueError("Migration credentials must not be supplied to the application")
            if make_url(self.database_url).username != "dfs_runtime":
                raise ValueError("Application requires the restricted dfs_runtime database role")
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
