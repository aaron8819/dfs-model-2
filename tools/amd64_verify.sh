#!/usr/bin/env bash
# Canonical native procedure; invoked only on a fresh private Actions VM.
set -euo pipefail
test "${GITHUB_ACTIONS:-}" = true
test "${RUNNER_ARCH:-}" = X64
test "${GITHUB_REPOSITORY:-}" = aaron8819/dfs-model-2
python -m tools.amd64_evidence verify-source
mkdir -p artifacts/local/amd64-run
git rev-parse HEAD > artifacts/local/amd64-run/source.txt
cp SOURCE_EQUIVALENCE.json artifacts/local/amd64-run/source-equivalence.json
uname -a > artifacts/local/amd64-run/host.txt
lscpu >> artifacts/local/amd64-run/host.txt
systemd-detect-virt >> artifacts/local/amd64-run/host.txt || true
printf '%s\n' "ImageOS=${ImageOS:-unknown}" "ImageVersion=${ImageVersion:-unknown}" \
  "RUNNER_ARCH=$RUNNER_ARCH" "GITHUB_SHA=$GITHUB_SHA" > artifacts/local/amd64-run/runner.txt
# GitHub documents ubuntu-24.04 as an x64 VM. Reject registered CPU emulators as well.
if compgen -G '/proc/sys/fs/binfmt_misc/qemu-*' >/dev/null; then exit 1; fi
printf '%s\n' 'Standard GitHub ubuntu-24.04 x64 VM; no CPU emulation configured.' \
  > artifacts/local/amd64-run/native-attestation.txt
docker context ls > artifacts/local/amd64-run/contexts.txt
docker info --format '{{.Architecture}} {{.OperatingSystem}} {{.KernelVersion}} {{.NCPU}} {{.MemTotal}}' \
  > artifacts/local/amd64-run/daemon.txt
test "$(uname -m)" = x86_64
case "$(docker info --format '{{.Architecture}}')" in x86_64|amd64) ;; *) exit 1;; esac
test -f /sys/fs/cgroup/cgroup.controllers
df -h . >> artifacts/local/amd64-run/host.txt
{
  python --version
  node --version
  npm --version
  sha256sum Dockerfile requirements.lock web/package-lock.json
  docker buildx imagetools inspect node:24.21.0-bookworm-slim@sha256:2fe369e969550cde8e867afc3fe370b260140cab4a23d467074295b42163d553
  docker buildx imagetools inspect python:3.13.15-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e
} > artifacts/local/amd64-run/build-inputs.txt
for name in dfs-increment6-app dfs-increment6-postgres dfs-amd64-tests dfs-amd64-oidc; do
  if docker container inspect "$name" >/dev/null 2>&1; then exit 1; fi
done
if docker network inspect dfs-amd64-verification >/dev/null 2>&1; then exit 1; fi
if ss -ltnH | awk '{print $4}' | grep -Eq ':(55432|55436|8765|8766)$'; then exit 1; fi

python3.13 -m venv .venv
.venv/bin/python -m tools.prepare_image amd64
.venv/bin/python -m pip install --no-index --find-links=artifacts/local/wheels-amd64 -r requirements.lock
.venv/bin/python -m pip check
docker build --platform linux/amd64 --progress plain \
  --build-context wheelhouse=artifacts/local/wheels-amd64 --target runtime \
  -t dfs-amd64:runtime . 2>&1 | tee artifacts/local/amd64-run/build-runtime.log
docker build --platform linux/amd64 --progress plain \
  --build-context wheelhouse=artifacts/local/wheels-amd64 --target migration \
  -t dfs-amd64:migration . 2>&1 | tee artifacts/local/amd64-run/build-migration.log
docker build --platform linux/amd64 --build-context wheelhouse=artifacts/local/wheels-amd64 \
  --target base -t dfs-amd64:test-base .
docker image inspect dfs-amd64:runtime dfs-amd64:migration \
  > artifacts/local/amd64-run/images.json
docker run --rm --network none dfs-amd64:runtime python -m pip list --format=json \
  > artifacts/local/amd64-run/runtime-packages.json
docker run --rm --network none dfs-amd64:runtime python -m pip check
docker run --rm --network none dfs-amd64:runtime python -c \
"import os,platform,pathlib,importlib.util as u; print(platform.machine(),platform.python_version(),os.getuid()); assert os.getuid()==10001; assert platform.machine()=='x86_64'; assert all(u.find_spec(m) is None for m in ['pytest','pytest_cov','coverage','black','ruff']); assert pathlib.Path('/app/web/dist/index.html').is_file(); assert not any(pathlib.Path('/app').glob('**/*_test.py')); assert not any(pathlib.Path('/app',p).exists() for p in ['tools','fixtures','migrations','.env.local.json']); print('runtime contents and non-root checks passed')" \
  | tee artifacts/local/amd64-run/runtime-checks.txt

# Existing permitted unreachable-endpoint handler control; no previously connected app is disrupted.
docker run --rm -i --network none dfs-amd64:runtime python - <<'PY' \
  | tee artifacts/local/amd64-run/unavailable-handler.json
import asyncio, json, time
import httpx
from server.app import create_app
from server.config import Settings
app = create_app(Settings(
    'postgresql+psycopg://dfs_runtime@127.0.0.1:1/unavailable',
    'https://dfs.example.com', 'https://accounts.google.com',
    'synthetic-client', 'synthetic-placeholder', 'synthetic-subject'))
async def main():
    # Deliberately no lifespan: readiness/error handlers only, not startup or live reconnection.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://dfs.example.com') as client:
        started = time.perf_counter()
        ready, health = await client.get('/ready'), await client.get('/health')
        assert ready.status_code == 503 and health.status_code == 200
        print(json.dumps({'ready': ready.status_code, 'health': health.status_code,
                          'seconds': time.perf_counter()-started, 'live_reconnection': False}))
    app.state.engine.dispose()
asyncio.run(main())
PY

docker network create --label dfs.scope=amd64-verification dfs-amd64-verification
docker pull --platform linux/amd64 postgres:17.11-bookworm
docker image inspect postgres:17.11-bookworm > artifacts/local/amd64-run/postgres-image.json
docker run -d --name dfs-increment6-postgres --label dfs.scope=increment6 \
  --label dfs.verification=amd64 --network dfs-amd64-verification \
  --cpus 0.5 --memory 1g -p 127.0.0.1:55436:5432 \
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=dfs_release postgres:17.11-bookworm
docker run -d --name dfs-amd64-tests --label dfs.scope=amd64-verification \
  --network dfs-amd64-verification --cpus 0.5 --memory 1g -p 127.0.0.1:55432:5432 \
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=dfs_increment2_test postgres:17.11-bookworm
for name in dfs-increment6-postgres dfs-amd64-tests; do
  for attempt in $(seq 1 60); do
    if docker exec "$name" pg_isready -U postgres; then break; fi
    sleep 1
  done
  docker exec "$name" pg_isready -U postgres
done
for pair in dfs-increment6-postgres:dfs_release dfs-amd64-tests:dfs_increment2_test; do
  name=${pair%%:*}; database=${pair#*:}
  docker exec -i "$name" psql -v ON_ERROR_STOP=1 -U postgres -d "$database" <<SQL
CREATE ROLE dfs_migration LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE dfs_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
ALTER DATABASE $database OWNER TO dfs_migration;
ALTER SCHEMA public OWNER TO dfs_migration;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SQL
done
docker run --rm --network host \
  -e MIGRATION_DATABASE_URL=postgresql+psycopg://dfs_migration@127.0.0.1:55436/dfs_release \
  dfs-amd64:migration
docker run --rm --network host \
  -e MIGRATION_DATABASE_URL=postgresql+psycopg://dfs_migration@127.0.0.1:55432/dfs_increment2_test \
  dfs-amd64:migration upgrade 0004_increment5
for pair in dfs-increment6-postgres:dfs_release dfs-amd64-tests:dfs_increment2_test; do
  name=${pair%%:*}; database=${pair#*:}
  docker exec "$name" psql -v ON_ERROR_STOP=1 -U dfs_migration -d "$database" -c \
    "INSERT INTO owner VALUES (gen_random_uuid(),'http://127.0.0.1:8766','synthetic-owner');"
done
mkdir -p artifacts/local/prior-increment5
cp -a verification/prior/. artifacts/local/prior-increment5/
mkdir -p artifacts/local/prior-increment5/artifacts
docker run --rm --network host -w /verify \
  --mount "type=bind,source=$PWD/artifacts/local/prior-increment5,target=/verify" \
  dfs-amd64:test-base python -m pytest server/application_test.py server/completion_test.py \
  server/decision_test.py -q \
  --deselect=server/application_test.py::test_historical_import_through_postgres \
  --deselect=server/completion_test.py::test_historical_import_and_server_objectives \
  --junitxml=/verify/prior-synthetic.xml
cp artifacts/local/prior-increment5/prior-synthetic.xml artifacts/local/amd64-run/

cat > artifacts/local/amd64-run/inventory.py <<'PY'
import hashlib, json
import psycopg
from psycopg import sql
with psycopg.connect('host=127.0.0.1 port=55432 dbname=dfs_increment2_test user=dfs_migration') as db:
    result = {}
    for (name,) in db.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").fetchall():
        rows = db.execute(sql.SQL('SELECT to_jsonb(t)::text FROM {} t ORDER BY to_jsonb(t)::text').format(sql.Identifier(name))).fetchall()
        result[name] = {'rows': len(rows), 'sha256': hashlib.sha256(json.dumps(rows).encode()).hexdigest()}
    print(json.dumps(result, indent=2))
PY
.venv/bin/python artifacts/local/amd64-run/inventory.py > artifacts/local/amd64-run/before.json
docker run --rm --network host \
  -e MIGRATION_DATABASE_URL=postgresql+psycopg://dfs_migration@127.0.0.1:55432/dfs_increment2_test \
  dfs-amd64:migration
.venv/bin/python artifacts/local/amd64-run/inventory.py > artifacts/local/amd64-run/after.json
.venv/bin/python - <<'PY'
import json
from pathlib import Path
p = Path('artifacts/local/amd64-run')
a, b = (json.loads((p / f'{n}.json').read_text()) for n in ('before', 'after'))
assert all(b[k] == v for k, v in a.items() if k != 'alembic_version')
assert set(b) - set(a) == {'operational_state', 'operational_event'}
assert a['raw_blob']['rows'] and a['draft_revision']['rows'] and a['recommendation_request']['rows']
print('Existing domain contents unchanged')
PY
docker run --rm --network host -w /verify --mount "type=bind,source=$PWD,target=/verify" \
  dfs-amd64:test-base python -m pytest server/recommendation/solver_test.py \
  server/recommendation/runner_test.py server/validator/lineup_test.py server/operations_test.py \
  server/application_test.py server/completion_test.py server/decision_test.py server/late_swap_test.py \
  tools/amd64_evidence_test.py \
  -q --deselect=server/application_test.py::test_historical_import_through_postgres \
  --deselect=server/completion_test.py::test_historical_import_and_server_objectives \
  --junitxml=artifacts/local/amd64-run/regressions.xml

.venv/bin/python - <<'PY'
from pathlib import Path
import secrets
secret = secrets.token_urlsafe(32)
Path('.env.amd64-oidc').write_text(f'OIDC_CLIENT_SECRET={secret}\n')
Path('.env.amd64-synthetic').write_text(
    'APP_ENV=development\nLOCAL_TEST_OIDC=1\n'
    'DATABASE_URL=postgresql+psycopg://dfs_runtime@127.0.0.1:55436/dfs_release\n'
    'APP_ORIGIN=http://127.0.0.1:8765\nOIDC_ISSUER=http://127.0.0.1:8766\n'
    'OIDC_CLIENT_ID=dfs-local-test\nOWNER_SUBJECT=synthetic-owner\n'
    f'OIDC_CLIENT_SECRET={secret}\n')
for name in ('.env.amd64-oidc', '.env.amd64-synthetic'):
    Path(name).chmod(0o600)
PY
docker run -d --name dfs-amd64-oidc --label dfs.scope=amd64-verification --network host \
  --env-file .env.amd64-oidc --mount "type=bind,source=$PWD/tools,target=/app/tools,readonly" \
  dfs-amd64:test-base python -m uvicorn tools.test_oidc:app --host 127.0.0.1 --port 8766 --no-access-log
# Expected failure: production must reject synthetic identity before database access.
if docker run --rm --network none --env-file .env.amd64-synthetic -e APP_ENV=production \
  dfs-amd64:runtime python -c 'from server.config import Settings; Settings.from_env()' \
  > artifacts/local/amd64-run/production-rejection.txt 2>&1; then exit 1; fi
grep -q 'Production cannot enable synthetic identity' artifacts/local/amd64-run/production-rejection.txt
date -u +%s.%N > artifacts/local/amd64-run/start-time.txt
docker run -d --name dfs-increment6-app --label dfs.scope=increment6 \
  --label dfs.verification=amd64 --network host --cpus 1 --memory 2g --pids-limit 128 \
  --stop-timeout 40 --env-file .env.amd64-synthetic dfs-amd64:runtime \
  python -m uvicorn server.app:create_app --factory --host 127.0.0.1 --port 8765 \
  --workers 1 --no-proxy-headers --no-access-log --timeout-graceful-shutdown 40
for attempt in $(seq 1 100); do
  if curl -fsS http://127.0.0.1:8765/ready; then break; fi
  sleep 0.1
done
curl -fsS http://127.0.0.1:8765/ready
date -u +%s.%N > artifacts/local/amd64-run/ready-time.txt
curl -fsS http://127.0.0.1:8765/ > artifacts/local/amd64-run/frontend.html
docker inspect --format '{{json .HostConfig}}' dfs-increment6-app \
  > artifacts/local/amd64-run/app-limits.json
docker exec dfs-increment6-app python -c "import os; assert 'MIGRATION_DATABASE_URL' not in os.environ"
.venv/bin/python -m tools.image_acceptance
.venv/bin/python -m tools.image_polling
.venv/bin/python -m tools.decision_demo
cd web
npm ci
npx playwright install --with-deps chromium
RELEASE_DRILL=1 DFS_TEST_PYTHON="$PWD/../.venv/bin/python" \
  PLAYWRIGHT_JSON_OUTPUT_NAME=../artifacts/local/amd64-run/browser.json \
  npx playwright test e2e/decision.spec.ts e2e/late-swap.spec.ts --reporter=json --trace=off
RELEASE_DRILL=1 PLAYWRIGHT_JSON_OUTPUT_NAME=../artifacts/local/amd64-run/mobile.json \
  npx playwright test e2e/mobile.spec.ts --reporter=json --trace=off
cd ..
cp artifacts/increment6-image-resources.json artifacts/increment6-image-polling.json \
  artifacts/increment6-image-browser-evidence.json artifacts/local/amd64-run/

docker exec dfs-amd64-tests createdb -U postgres -O dfs_migration \
  -T dfs_increment2_test dfs_amd64_bad
cat > artifacts/local/amd64-run/startup.py <<'PY'
import asyncio, os
from server.app import create_app
from server.config import Settings
app = create_app(Settings(
    'postgresql+psycopg://dfs_runtime@127.0.0.1:55432/dfs_amd64_bad',
    'https://dfs.example.com', 'https://accounts.google.com',
    'synthetic-client', 'synthetic-placeholder', 'synthetic-subject'))
async def main():
    try:
        async with app.router.lifespan_context(app):
            pass
    except ValueError as exc:
        assert str(exc) == os.environ['EXPECTED'], str(exc)
        print(str(exc))
    else:
        assert os.environ['EXPECTED'] == 'pass'
        print('startup positive control passed')
asyncio.run(main())
PY
startup_probe() {
  docker run --rm --network host -e EXPECTED="$1" \
    --mount "type=bind,source=$PWD/artifacts/local/amd64-run/startup.py,target=/tmp/startup.py,readonly" \
    dfs-amd64:runtime python -c "exec(open('/tmp/startup.py').read())" \
    | tee -a artifacts/local/amd64-run/startup-controls.txt
}
startup_probe pass
docker exec dfs-amd64-tests psql -v ON_ERROR_STOP=1 -U dfs_migration -d dfs_amd64_bad \
  -c "UPDATE operational_state SET schema_version='incompatible-synthetic';"
startup_probe 'Migration compatibility check failed'
docker exec dfs-amd64-tests psql -v ON_ERROR_STOP=1 -U dfs_migration -d dfs_amd64_bad \
  -c "UPDATE operational_state SET schema_version='0005_increment6'; GRANT UPDATE ON draft_revision TO dfs_runtime;"
startup_probe 'Runtime database grants are unsafe'
docker exec dfs-amd64-tests psql -v ON_ERROR_STOP=1 -U dfs_migration -d dfs_amd64_bad \
  -c "REVOKE UPDATE ON draft_revision FROM dfs_runtime;"
startup_probe pass
for statement in 'UPDATE raw_blob SET media_type=media_type' 'DELETE FROM operational_event'; do
  if docker exec dfs-amd64-tests psql -v ON_ERROR_STOP=1 -U dfs_runtime -d dfs_amd64_bad \
    -c "BEGIN; $statement; ROLLBACK;" > artifacts/local/amd64-run/denial.txt 2>&1; then exit 1; fi
  grep -q 'permission denied' artifacts/local/amd64-run/denial.txt
  cat artifacts/local/amd64-run/denial.txt >> artifacts/local/amd64-run/grant-denials.txt
done

# Do not stop/pause/disconnect either database: live outage/reconnection remains pending.
.venv/bin/python -m tools.amd64_evidence final
