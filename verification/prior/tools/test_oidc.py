"""Isolated test provider. Never mounted by the application; loopback startup only.

Ephemeral RSA signing key and one-use codes exercise the real client callback.
The provider is intentionally a test identity authority, not a production login service.
"""

import base64
import hashlib
import os
import secrets
import time
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from joserfc import jwt
from joserfc.jwk import RSAKey

app = FastAPI(docs_url=None, openapi_url=None)
ISSUER = "http://127.0.0.1:8766"
REDIRECT = "http://127.0.0.1:8765/auth/callback"
key = RSAKey.generate_key(2048, parameters={"kid": "local-ephemeral"})
codes: dict[str, dict] = {}


@app.get("/.well-known/openid-configuration")
def metadata() -> dict:
    return {
        "issuer": ISSUER,
        "authorization_endpoint": ISSUER + "/authorize",
        "token_endpoint": ISSUER + "/token",
        "jwks_uri": ISSUER + "/jwks",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "code_challenge_methods_supported": ["S256"],
    }


@app.get("/jwks")
def keys() -> dict:
    return {"keys": [key.as_dict(private=False)]}


@app.get("/authorize")
def authorize(request: Request) -> HTMLResponse:
    import html

    q = dict(request.query_params)
    if (
        q.get("redirect_uri") != REDIRECT
        or q.get("client_id") != "dfs-local-test"
        or q.get("code_challenge_method") != "S256"
        or not q.get("nonce")
        or not q.get("state")
        or q.get("response_type") != "code"
    ):
        raise HTTPException(400, "Invalid test authorization request")
    fields = "".join(
        f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(v)}">'
        for k, v in q.items()
    )
    return HTMLResponse(
        "<h1>Isolated test identity provider</h1><p>Synthetic local owner only.</p>"
        '<form method="post" action="/authorize">'
        + fields
        + "<button>Continue as synthetic owner</button></form>"
    )


@app.post("/authorize")
async def approve(request: Request) -> RedirectResponse:
    q = dict(await request.form())
    if q.get("redirect_uri") != REDIRECT or q.get("client_id") != "dfs-local-test":
        raise HTTPException(400)
    code = secrets.token_urlsafe(32)
    codes[code] = {**q, "issued": time.time()}
    return RedirectResponse(REDIRECT + "?" + urlencode({"code": code, "state": q["state"]}), 303)


@app.post("/token")
async def token(request: Request) -> dict:
    form = await request.form()
    expected = base64.b64encode(
        ("dfs-local-test:" + os.environ["OIDC_CLIENT_SECRET"]).encode()
    ).decode()
    if not secrets.compare_digest(request.headers.get("authorization", ""), "Basic " + expected):
        raise HTTPException(401)
    q = codes.pop(str(form.get("code")), None)
    challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(str(form.get("code_verifier", "")).encode()).digest()
        )
        .rstrip(b"=")
        .decode()
    )
    if (
        not q
        or time.time() - q["issued"] > 60
        or q.get("code_challenge") != challenge
        or form.get("redirect_uri") != REDIRECT
    ):
        raise HTTPException(400, "Invalid, expired, or replayed code/PKCE")
    now = int(time.time())
    # Fault injection exists only in this separate local test process, never in app configuration.
    mode = os.getenv("TEST_OIDC_FAULT", "")
    claims = {
        "iss": ISSUER,
        "sub": "synthetic-owner",
        "aud": "dfs-local-test",
        "iat": now,
        "exp": now + 120,
        "nonce": q["nonce"],
    }
    if mode == "expired":
        claims["exp"] = now - 120
    if mode in {"iss", "aud", "nonce", "sub"}:
        claims[mode] = "wrong"
    signing_key = key if mode != "signature" else RSAKey.generate_key(2048)
    encoded = jwt.encode({"alg": "RS256", "kid": "local-ephemeral"}, claims, signing_key)
    return {
        "access_token": secrets.token_urlsafe(32),
        "token_type": "Bearer",
        "expires_in": 120,
        "id_token": encoded,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8766, access_log=False)
