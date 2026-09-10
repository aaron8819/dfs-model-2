# Private deployment proposal — September 10, 2026

No resources have been provisioned. Weekly release is **not accepted**; see
[RELEASE_ACCEPTANCE.md](RELEASE_ACCEPTANCE.md). Recommend Render, Ohio, USD, Hobby workspace:

| Resource | Proposed configuration | Monthly estimate |
| --- | --- | ---: |
| Application | One paid web service, `1c-2g` (legacy Standard), 1 CPU / 2 GB; one Uvicorn worker | $25 |
| PostgreSQL | Version 17, `0.5c-1g` (legacy Basic-1gb), 1 GB RAM, 100 connections | $19 |
| Database storage | 10 GB; expand after reviewing growth | $3 |
| Total | Hobby workspace, no persistent app disk, Redis or background service | **$47** |

The [official pricing](https://render.com/pricing) lists database storage at $0.30/GB-month,
5 GB Hobby bandwidth then $0.15/GB, and additional build/usage charges. Taxes, domain/registry
fees, local/offsite archive storage, extra builds, bandwidth and temporary recovery instances
are excluded. Confirm the dashboard quote before spending. [Plan identifiers](https://render.com/docs/compute-plans)
and [Ohio/private-network availability](https://render.com/docs/regions) checked September 10.
This is a proposal supported by native ARM64 local measurements, not a hosted capacity guarantee.

Paid PostgreSQL includes PITR: Hobby retains three days; Pro retains seven. The newest selectable
restore point must be at least ten minutes old. Logical exports are retained seven days.
[Official recovery documentation](https://render.com/docs/postgresql-backups). Recommend a daily
downloaded logical archive and an extra archive after entered recording/before risky maintenance;
daily-only loss can reach 24 hours, with additional manual Yahoo changes outside the database.
PITR reduces this but has no zero-loss guarantee. No backup automation is provisioned here.

## Runtime and reproducible build

Python **3.13.15**, Node **24.21.0 LTS** (build only), Debian bookworm slim, PostgreSQL **17.11**
for local image/drill. Python 3.13 receives maintained patches; Node 24 is LTS. Sources:
[PSF release](https://blog.python.org/2026/08/python-3147-31315/),
[Node release](https://nodejs.org/en/blog/release/v24.21.0),
[PostgreSQL patches](https://www.postgresql.org/docs/release/).
Pinned libraries remain in `requirements.lock` and `web/package-lock.json`; Linux's previously
omitted `greenlet==3.5.5` is now explicit. Patch maintenance still requires rebuilding and testing.
No vulnerability scan or absence-of-CVE claim is made.

The Dockerfile builds frontend assets, installs locked wheels offline, runs UID 10001, and contains
neither private fixtures, local artifacts, secrets, synthetic launchers nor migrations in its runtime
stage. Only the admission lock file is writable under `/app`; child temporary files use `/tmp`.
Migration is a separate build target and command, never application startup. Base image identifiers
and the tested runtime image ID are recorded in `artifacts/increment6-image-identity.json`.

Verification follow-up removes Black/coverage/pytest/pytest-cov/Ruff from the runtime stage without
changing locked dependency versions or the migration target. Its new ARM64 smoke image is recorded
in [AMD64_VERIFICATION_REPORT.md](AMD64_VERIFICATION_REPORT.md); it is not the accepted historical
image and has not passed native AMD64 workflow verification. Use the
[native-machine procedure](docs/AMD64_VERIFICATION_PROCEDURE.md) before selecting a deployment digest.

From the repository, using a Python environment with pip:

```powershell
.venv/Scripts/python -m tools.prepare_image amd64
docker build --platform linux/amd64 --build-context wheelhouse=artifacts/local/wheels-amd64 --target runtime -t dfs-release:review .
docker build --platform linux/amd64 --build-context wheelhouse=artifacts/local/wheels-amd64 --target migration -t dfs-release:migration .
```

Use an actual AMD64 builder/runner. This machine runs native Linux ARM64; its AMD64 attempt failed
with `exec format error`. `compose.release.yml` provides the resource limits, private app env file,
readiness check and explicitly selected maintenance/migration profile for a local production-config
rehearsal. Its Compose syntax was validated; live secrets/HTTPS execution remain pending. Supply
`DFS_IMAGE` and `DFS_MIGRATION_IMAGE` as the corresponding verified immutable image digests.

Neither an AMD64 image build nor AMD64 execution passed. Do not upload
the ARM64 image: [Render requires linux/amd64](https://render.com/docs/deploying-an-image).
For local ARM64 review substitute `arm64` in both build-context folder and platform.
Host pip downloads were needed because Docker's direct Python package download hit a TLS handshake
failure; verification was not disabled. Wheel SHA-256 manifests are committed as build evidence.

## Deployment/startup sequence (requires separate authorization)

1. Confirm quote and native AMD64 acceptance. Use a private registry, immutable tested image digest,
   no automatic deploys. Create paid app and PostgreSQL 17 in Ohio. Restrict DB network access.
2. Using the provider administrative connection, create a distinct `dfs_runtime` login and a migration
   login/owner. Neither may be superuser; runtime gets no database/schema creation. Assign passwords
   through the provider/secure terminal, never command history. Revoke public schema CREATE.
   Database/schema owner executes Alembic; migrations issue the restricted runtime grants. Verify
   provider role-creation/ownership capabilities in the hosted environment before proceeding.
3. Run the migration image once with **only** `MIGRATION_DATABASE_URL` available via a secret env file:
   `docker run --rm --env-file <private-migration-env-file> dfs-release:migration`.
   Insert the verified issuer/subject into `owner` with a parameterized migration-role command.
4. Configure the app with the values below, `APP_ENV=production`, no `LOCAL_TEST_OIDC` and no migration
   secret. Use the Dockerfile command: port 8000, workers 1, proxy headers disabled, access log disabled,
   graceful shutdown 40 seconds. Render terminates HTTPS; URLs come only from configured origin.
   Forwarded host/proto headers are not trusted or used to construct callbacks or secure cookies.
5. Set health path `/ready`. `/health` is liveness only. Check DB/schema/grants/clock, normal owner
   login, second-account rejection, cookie attributes, CSRF, logout, expiry, request isolation and
   interrupted solving through actual Render HTTPS. No HTTPS topology pass is implied by local HTTP.
6. Run the weekly workflow with current user-confirmed Yahoo rules/game membership and real five-file
   projections. Verify freshness and actual-device review. Accept weekly release only after all gates.

| Setting | Exact value / how obtained |
| --- | --- |
| `OIDC_CLIENT_ID` | Google Cloud OAuth web application client ID from its credential record |
| `OIDC_CLIENT_SECRET` | Same client credential; store in Render secret configuration |
| `OWNER_SUBJECT` | `sub` from a cryptographically verified Google ID token for the intended owner; verify signature/JWKS, issuer, audience, expiry and nonce in an authorized code/PKCE flow. Email/display name is not an identity pin. Capture locally without logging token/secret. |
| `OIDC_ISSUER` | Exactly `https://accounts.google.com` |
| `APP_ORIGIN` | Exact allocated HTTPS origin, e.g. `https://<chosen-service>.onrender.com`, with no path/query/fragment |
| Callback | Exactly `${APP_ORIGIN}/auth/callback`, registered as the Google client's authorized redirect URI |
| `DATABASE_URL` | SQLAlchemy URL `postgresql+psycopg://dfs_runtime:<secret>@<private-host>:5432/<database>`; private same-region route |
| `MIGRATION_DATABASE_URL` | Separate owner connection; migration process only; never attached to app |

Google client setup, verified subject, chosen HTTPS origin, hosted role setup and native clock/capacity
checks are pending. No external OAuth setting was changed. Production startup validates required
identity values, exact origin shape/issuer, synthetic-mode exclusion, role/grants and schema marker.
Secure/HttpOnly/SameSite=Lax opaque cookies, nonce/PKCE, pinned owner, CSRF+origin and DB session expiry
remain active. A narrow viewport selects presentation only; it grants no server privileges.
