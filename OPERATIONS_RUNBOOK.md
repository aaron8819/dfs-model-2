# Operations and recovery

Release state and evidence: [RELEASE_ACCEPTANCE.md](RELEASE_ACCEPTANCE.md).
Hosted configuration/cost: [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md).

Native verification handoff: [AMD64 procedure](docs/AMD64_VERIFICATION_PROCEDURE.md).
Existing image drills assume fixed increment-6 container names/ports and cgroup v2; use a dedicated
disposable machine and abort on collisions. The late-swap browser helper accepts `DFS_TEST_PYTHON`
or selects the platform venv. Run late-swap evidence before mobile review. Resource drill interruption
passes only when the observed child yields an interrupted result, restart regains readiness and
Apply rejects that result; a solve that completed before shutdown does not pass this check.
The previously rejected DB stop remains unperformed; no alternative injection is authorized by
this runbook. Live reconnection requires the separately permitted method and positive recovery
controls described in the procedure.

## Checks and logs

`GET /health` checks process liveness. `GET /ready` checks DB reachability, schema `0005_increment6`,
production runtime privileges, recovery quarantine and clock regression. It returns generic 503 when
blocked/unavailable. Recovery review remains readable through owner-authenticated APIs. Startup fails
on incompatible schema or unsafe production configuration/grants. Do not supply migrations to startup.

One process uses at most five domain connections plus one independent clock connection. Domain
checkout wait is 8 seconds; connect timeout 3 seconds; statement/lock timeouts 15/7 seconds. Clock
transactions use 2/1-second statement/lock timeouts and acquire no domain locks. They sample after
their singleton lock and use `greatest` on write. Every observation remains durable even if its
command rolls back. Fifty observations while all five domain connections were occupied passed.
This is bounded cost, not proof of arbitrarily high polling capacity. Keep ordinary polling at its
existing rate; do not create multiple app workers or replicas without another admission design review.

Logs contain generic HTTP rejection status/method, clock-regression notices, startup failures and
existing completion/interruption diagnostics. Access logging is off to avoid OAuth code/query leakage.
Do not enable request body, cookies, tokens or raw-file logging. Investigate recurring 409/423/503 via
authenticated state and immutable evidence; never retry a stale write with a new revision silently.

Clock correctness is separate from regression detection. Before hosted release and after host incidents,
record app UTC, `SELECT clock_timestamp()`, trusted external UTC, measured network uncertainty and
provider time-sync status. Request Render confirmation of host time synchronization/incident health
where host NTP tooling is inaccessible. Local Docker shares the WSL host clock and does not prove
independent time accuracy. Any discrepancy large enough to affect the next lock means use Yahoo and
quarantine while investigating; an increasing clock is not proof of correct wall time.

## Backup / single-owner workspace export

All raw source bytes, source captures, immutable revisions, active heads, entered/reconciliation
records, preferences, solver requests/results, receipts, lock decisions and clock authority are in
PostgreSQL. Export the entire single-owner database as one linked archive. Store an encrypted copy
outside the provider. Keep image digest, app commit, lockfiles, migration version, owner issuer/subject,
role/grant setup and secret configuration separately in secured configuration storage. Database dumps
contain session material and private sources: never commit them. `artifacts/local/` is ignored.

Use PostgreSQL client tools matching server major 17. Configure `PGHOST`, `PGPORT`, `PGDATABASE`,
`PGUSER`, SSL settings and `PGPASSFILE` in a secure process, rather than placing a password URL in argv:

```text
pg_dump --format=custom --file=<private-archive.dump>
```

For the exact local drill: `.venv/Scripts/python -m tools.recovery_drill`. It checks the increment-6
container label, archives `dfs_release`, creates a uniquely named empty database and never overwrites
the development database. It compares all table contents, verifies source hashes, restores constraints
and checks runtime grants before quarantining. Archive and timing evidence are separate.

Proposed frequency: daily and immediately after entered recording/maintenance. Daily-only RPO is up to
24 hours. Provider PITR and export retention are described in the deployment plan. Do not assume the
archive includes Yahoo submissions made after its capture. Hosted restore duration remains untested.

## Restore into quarantine — required before network access

1. Stop the application. Preserve the failing database and newest available archives/lock observations;
   do not restore over them. Create an empty isolated database with the correct migration owner and
   runtime role. Restore with `pg_restore --no-owner --exit-on-error --dbname=<empty-db> <archive>`.
   Connection passwords belong in `PGPASSFILE`. Never use `--clean` against a valuable database.
2. Point **only the offline administrative process** at the restored database using
   `MIGRATION_DATABASE_URL`. Apply compatible migrations explicitly. Run:

   ```text
   python -m tools.recovery quarantine --operator <operator> --evidence "<archive hash, incident and durable evidence reference>"
   ```

   This appends an operational event, sets `recovery_required`, monotonically advances a recommendation invalidation
   cutoff to cover every existing request (including future timestamps), revokes restored sessions,
   deletes ephemeral sign-in flows and expires the solver lease.
   It never rewrites raw/history/receipts, clock high-water or existing lock decisions. Runtime has
   SELECT only on operational state/events, so ordinary commands cannot release quarantine.
3. Verify source SHA-256, all FK relationships, active heads, exact working/entered slots, fixed salary,
   source-row identity, preferences, receipts and immutable results. Require a new normal OIDC login.
   Old requests never resume automatically; pre-cutoff previews remain stale even after release.
4. Check real current UTC, game schedule and Yahoo's actual entered lineup for **every restored
   workspace**. Compare earlier/surviving lock evidence from incident sources with restored evidence.
   If newer retained evidence is missing, preserve/import it via an audited domain procedure or keep
   quarantine. A successful database restore does not establish entered authority or reopen locks.
5. If actual Yahoo assignments differ, or a later lock/schedule observation cannot be established,
   **do not release**. Prefer a newer verified archive/PITR point. If a historical correction is needed,
   use an offline maintenance process invoking the existing `DecisionService.reconcile` with validated
   `ReconcileInput`, first `preview=True`, then the exact reviewed preview hash, reason and Yahoo
   reference. It must run with normal runtime grants, retain all clock/lock policy and fixed source-row
   validation, and keep the HTTP app stopped. Missing source/clock evidence is not repairable by an
   attestation alone; remain quarantined and work in Yahoo. No generic bypass endpoint exists.
6. Only after all restored entered facts agree with Yahoo and retained lock evidence is accounted for,
   with the app stopped, explicitly attest the checks:

   ```text
   python -m tools.recovery release --operator <operator> --evidence "<dated clock, schedule, entered and retained-lock verification record>" --verified-clock-schedule-entered-and-retained-locks
   ```

   Release refuses an observed clock still ahead of current DB time. This is a privileged operational
   attestation, not automatic Yahoo verification. Restart, check `/ready`, sign in, and generate fresh
   previews. Never reuse a pre-restore candidate. Keep incident evidence and the original database.

## Erroneous future clock sample

The next correct sample below the retained high-water mark blocks actionable operations and readiness.
An initially future sample may conservatively fix games early; it cannot establish correct time.
Stop the app, archive evidence, record the incident and quarantine. Correct host/database clock health
with the provider. **Never lower `clock_observation`, rewind `decision_at`, delete decisions or move an
established deadline later.** The supported recovery is to wait until independently verified UTC has
caught up with the retained authority, then complete all restore checks above. Locks remain retained.
If the erroneous value is far in the future, keep the app unavailable for actionable use and use Yahoo
for this slate/season. A more permissive recovery requires a separately designed and reviewed migration;
this increment deliberately has no automatic unlock, clock override, or lock-bypass command.

## User fallbacks

- Unavailable near kickoff: use Yahoo directly; preserve actual submitted slots and confirmation time.
  Reconcile explicitly when the app returns. The app never submits on your behalf.
- Missing/stale projections: inspect source publication time; refresh all five files as one batch or
  use Yahoo/manual research. Import time is not publication freshness. Do not manufacture forecasts.
- Unresolved entered facts or restore in progress: review remains available; make changes directly in
  Yahoo and retain evidence. Do not act on an old app preview while quarantine/reconciliation is open.
- Yahoo postponement/unlock exception: follow Yahoo's actual interface/rules directly. The app retains
  established locks and cannot adjudicate an exceptional unlock. Do not change clocks to force access.
