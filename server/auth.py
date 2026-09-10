"""Code/PKCE OIDC and opaque, revocable PostgreSQL sessions."""

import secrets

import httpx
from authlib.integrations.httpx_client import OAuth2Client
from authlib.oidc.core import CodeIDToken
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from joserfc import jwt
from joserfc.jwk import KeySet
from sqlalchemy.engine import Engine

from server.config import Settings
from server.persistence import digest, one, run


class Auth:
    def __init__(self, settings: Settings, engine: Engine) -> None:
        self.settings = settings
        self.engine = engine

    def metadata(self) -> dict:
        with httpx.Client(timeout=10) as client:
            response = client.get(self.settings.issuer + "/.well-known/openid-configuration")
            response.raise_for_status()
            metadata = response.json()
        if metadata["issuer"] != self.settings.issuer:
            raise ValueError("OIDC issuer mismatch")
        return metadata

    def client(self) -> OAuth2Client:
        return OAuth2Client(
            self.settings.client_id,
            self.settings.client_secret,
            scope="openid",
            redirect_uri=self.settings.origin + "/auth/callback",
            code_challenge_method="S256",
            timeout=10,
        )

    def cookie(self, response: RedirectResponse, name: str, token: str, seconds: int) -> None:
        response.set_cookie(
            name,
            token,
            max_age=seconds,
            httponly=True,
            secure=not self.settings.local_test,
            samesite="lax",
            path="/",
        )

    def login(self) -> RedirectResponse:
        metadata = self.metadata()
        token, nonce, verifier = (secrets.token_urlsafe(48) for _ in range(3))
        with self.client() as client:
            url, state = client.create_authorization_url(
                metadata["authorization_endpoint"], nonce=nonce, code_verifier=verifier
            )
        with self.engine.begin() as db:
            run(
                db,
                "INSERT INTO auth_flow VALUES (:hash,:state,:nonce,:verifier,"
                "clock_timestamp()+interval '10 minutes')",
                hash=digest(token.encode()),
                state=state,
                nonce=nonce,
                verifier=verifier,
            )
        response = RedirectResponse(url, status_code=303)
        self.cookie(response, "dfs_flow", token, 600)
        return response

    def callback(self, request: Request) -> RedirectResponse:
        with self.engine.begin() as db:
            flow = one(
                db,
                "DELETE FROM auth_flow WHERE token_hash=:hash "
                "AND expires_at>clock_timestamp() RETURNING *",
                hash=digest(request.cookies.get("dfs_flow", "").encode()),
            )
        if not flow or not secrets.compare_digest(
            flow["state"], request.query_params.get("state", "")
        ):
            raise HTTPException(401, "Invalid or expired sign-in state")
        try:
            metadata = self.metadata()
            with self.client() as client:
                token = client.fetch_token(
                    metadata["token_endpoint"],
                    code=request.query_params.get("code", ""),
                    code_verifier=flow["verifier"],
                )
                keys = client.request("GET", metadata["jwks_uri"], withhold_token=True).json()
            decoded = jwt.decode(
                token["id_token"], KeySet.import_key_set(keys), algorithms=["RS256"]
            )
            claims = CodeIDToken(
                decoded.claims,
                decoded.header,
                options={
                    "iss": {"essential": True, "value": self.settings.issuer},
                    "aud": {"essential": True, "value": self.settings.client_id},
                    "exp": {"essential": True},
                    "sub": {"essential": True},
                },
                params={
                    "nonce": flow["nonce"],
                    "client_id": self.settings.client_id,
                    "access_token": token["access_token"],
                },
            )
            claims.validate(leeway=0)
        except Exception as exc:
            raise HTTPException(401, "OIDC validation failed; start sign-in again") from exc
        if claims["sub"] != self.settings.owner_subject:
            raise HTTPException(403, "This account is not the configured owner")
        opaque, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        with self.engine.begin() as db:
            owner = one(
                db,
                "SELECT * FROM owner WHERE issuer=:issuer AND subject=:subject",
                issuer=claims["iss"],
                subject=claims["sub"],
            )
            if not owner:
                raise HTTPException(403, "Owner must be configured out of band")
            run(
                db,
                "INSERT INTO session VALUES (:hash,:owner,:csrf,"
                "clock_timestamp()+:seconds * interval '1 second',false)",
                hash=digest(opaque.encode()),
                owner=owner["id"],
                csrf=csrf,
                seconds=self.settings.session_seconds,
            )
        response = RedirectResponse("/", status_code=303)
        response.delete_cookie("dfs_flow")
        self.cookie(response, "dfs_session", opaque, self.settings.session_seconds)
        return response

    def require(self, request: Request) -> dict:
        with self.engine.connect() as db:
            session = one(
                db,
                "SELECT s.*,o.issuer,o.subject FROM session s JOIN owner o "
                "ON o.id=s.owner_id WHERE token_hash=:hash AND NOT revoked "
                "AND expires_at>clock_timestamp()",
                hash=digest(request.cookies.get("dfs_session", "").encode()),
            )
        if (
            not session
            or session["issuer"] != self.settings.issuer
            or session["subject"] != self.settings.owner_subject
        ):
            raise HTTPException(401, "Sign in to continue")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("origin") != self.settings.origin or not secrets.compare_digest(
                request.headers.get("x-csrf-token", ""), session["csrf"]
            ):
                raise HTTPException(403, "Origin or CSRF validation failed")
            if request.url.path != "/auth/logout":
                with self.engine.connect() as db:
                    state = one(db, "SELECT recovery_required FROM operational_state")
                if state["recovery_required"]:
                    raise HTTPException(
                        423, "Recovery review in progress; actionable use is blocked"
                    )
        return session
