# Increment 6 — release preparation and acceptance

**Local preparation complete; weekly release not accepted.** Started with a clean tree at accepted
`72f67ab` on `codex/increment-5-late-swaps`; created `codex/increment-6-release` without resetting work.
No push, paid resources, external deployment, identity configuration changes or production data edits.
No increment-7 automation. The [acceptance matrix](RELEASE_ACCEPTANCE.md) is the release authority.

Follow-up: [AMD64 verification prepared; native execution pending](AMD64_VERIFICATION_REPORT.md).
The follow-up preserves this accepted evidence and records narrow packaging/harness fixes, local
smoke results and exact native-machine preparation. Native AMD64 and weekly acceptance remain pending.

Private Actions follow-up: [bounded sanitized verification preparation](docs/AMD64_ACTIONS_HANDOFF.md).
The current task authorizes private snapshot pushes and included-allowance verification;
no deployment is authorized. Native execution awaits confirmation of remaining included
minutes/storage. Original private fixture history is preserved locally and excluded from
transport. See the updated AMD64 report for exact preparation changes and pending gates.

## Implemented

- A separate mobile review screen with Briefing, Players, Lineup and Previews navigation. Saved source
  freshness, missing evidence, environments, research, exact entered/draft differences, fixed status,
  reconciliation blockers and saved candidate tradeoffs are readable without edit/Apply/Undo controls.
  Narrow presentation is not authorization. Owner, CSRF/origin and mutation protections remain server-side.
- A pinned multi-stage image: frontend build, locked Linux wheels, non-root application, static assets
  and API, a separately invoked migration target. Runtime excludes test launchers, private fixtures,
  artifacts, tests and migration files. Production is the image default; local OIDC explicitly selects
  development configuration. Linux's missing transitive `greenlet` dependency is now pinned.
- Strict origin/identity/runtime-role configuration, migration/grant startup checks, `/ready`, bounded DB
  connection waits and generic failure/clock logs. Secure cookie configuration remains independent of
  untrusted proxy headers. Live Google/HTTPS verification remains pending.
- Clock observations use a dedicated one-connection pool, avoiding nested borrowing from a saturated
  five-connection domain pool. Observations take only the clock row lock, sample after waiting and use
  atomic `greatest`; older samples cannot overwrite newer authority. Domain lock order is unchanged.
- Independent bound validation rejects nonfinite values before integer flooring. Flooring is confined
  to the exact `points` stage's 1/10000-point integer lattice. Below-objective bounds and bounds that
  permit a greater integer objective reject proof; raw diagnostics remain retained. Ties remain separate.
- Additive `0005_increment6` operational quarantine, immutable-to-runtime audit events and a restored
  request cutoff. Offline quarantine revokes restored sessions, expires leases and blocks mutations;
  explicit audited release cannot make old previews applicable. No clock lowering or lock override.
- Reproducible image, load, backup, recovery and HTTP probe tools; deployment proposal and fallbacks in
  [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md) and [OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md).

## Verification actually executed

| Evidence | Actual result |
| --- | --- |
| `artifacts/increment6-boundaries-final.xml` | 47 passed: clock/config/grants, independent validator and complete late-swap boundary suite |
| `artifacts/increment6-final-regressions.xml` | 55 passed: operational boundaries, application/OIDC, validator and real child lifecycle; serial execution |
| `artifacts/increment6-operations.xml` | 12 passed, including production cookie flags/readiness and migration-secret exclusion; config+operations measured coverage 88% |
| `artifacts/increment6-final-image-browser.json` | 3 passed in 43.3 seconds on final native ARM64 image: decisions, late swaps, mobile |
| `artifacts/increment6-image-browser-evidence.json` | Synthetic OIDC, fixed/remainder Apply, entered recording, historical reconciliation, second-tab conflict and zero unexpected browser errors |
| `artifacts/increment6-decisions-browser-evidence.json` | Game evidence/research, three candidate tradeoffs, exact Apply, Undo, entered recording and stale conflict |
| `artifacts/increment6-mobile-*.png` and mobile test | 320/390/430 widths, keyboard Tab/Enter, scrolling, no horizontal overflow and no mutation requests |
| `artifacts/increment6-migrations.json` | Fresh database migration; separate clone of populated accepted `0004_increment5` upgraded with all existing domain table content hashes unchanged |
| `artifacts/increment6-production-config.json` | Actual image refuses synthetic identity under production configuration |
| `artifacts/increment6-database-unavailable.json` | Separate TestClient app inside actual image, unreachable DB port: readiness503/liveness200; not a stopped-container outage |

Counts overlap; do not sum them as distinct tests. Black (55 files), Ruff, dependency consistency,
TypeScript/Vite build, strict browser-test TypeScript, generated OpenAPI/types and diff whitespace
checks passed. No historical benchmark suite was rerun. Existing historical artifacts remain intact.
Screenshots of narrow/wide briefing/lineup, previews and desktop fixed/reconciliation state were
inspected. This is browser emulation, not an actual phone test.

The complete synthetic workflow was exercised across the final three browser scenarios and image
drills: normal code/PKCE sign-in; dated setup; original-format Yahoo and five projection imports;
scoring/coverage activation; odds/research; completion/alternatives; exact Apply/Undo; entered recording;
synthetic early-game deadline; refreshed evidence with fixed players; remaining-slot Apply and updated
entered recording; explicit historical reconciliation; stale writes/second-tab conflicts; image restart;
mobile review; separate database restoration. Test infrastructure appends an earlier deadline only for
labeled synthetic games; the production app has no clock bypass. Synthetic dates/data are not current
Yahoo facts, and local test OIDC is not live Google acceptance.

## Whole-image measurements

Native Linux ARM64 under Docker/WSL2, PostgreSQL 17.11 ARM64. App limited to **1 CPU / 2 GiB**, database
to **0.5 CPU / 1 GiB**. Final image identity/base digests: `artifacts/increment6-image-identity.json`.
Resource/interruption evidence records a preceding image; later changes were base digest pinning,
a type annotation and production-only migration-secret rejection. Development runtime behavior is
unchanged. The final source also passed the real solver/two-tab workload and final-image browser checks.

| Measurement | Observed |
| --- | ---: |
| Container creation to readiness | 1.805 s |
| First authenticated session read | 0.013 s |
| Synthetic pool | 541 Yahoo entries / 541 admitted projections |
| Setup + Yahoo import/activation | 5.378 s |
| Five-file import, review and activation | 0.920 s |
| Complete including polling/read/busy checks | 5.372 s |
| Three alternatives, first/repeated request | 8.784 / 7.962 s |
| Container cgroup peak, parent plus children/cache | 150.11 MiB |
| Concurrent solve request | 409; reads continue |
| Workspace/read polling in main workload | 77 reads; mean 0.201 s, maximum 0.376 s |
| Two-tab workspace + research pair | 24 pairs; 0.326–0.756 s |
| Sampled runtime DB connections | Peak 4, 148 samples; configured ceiling 6 |
| Native child observed, then graceful SIGTERM | 1.196 s to exit0; no OOM; `interrupted` result rejects Apply |
| Additional three-candidate request DB growth | 32,768 bytes; source bytes unchanged |

Raw measurements: `increment6-image-resources.json`, `increment6-image-polling.json`,
`increment6-image-startup.json`. Child shutdown was verified after detecting `worker.py` in the
container, not inferred from sending a request. Restart preserved exact assignments. Source growth
is content-addressed, so identical imports do not add bytes; immutable revisions/results still grow.
Synthetic equal/similar projections are a workload sample, not a worst-case capacity guarantee.
No recommendation to shrink to 512 MB is justified solely by these measurements.

## Recovery evidence

`artifacts/increment6-recovery.json`: 12,408,499-byte populated database, 14 raw blobs totaling 117,300
bytes, six draft revisions and three entered revisions. Archive 695,465 bytes; backup 0.861 seconds;
fresh isolated restore **1.332 seconds**. Every restored table's content hash matched, including
references, active heads, receipts and fixed/salary evidence; raw SHA-256 and runtime grants passed.

Quarantine preserved all domain/lock/clock evidence, revoked sessions and invalidated prior requests.
Actual restored-image probes exercised normal OIDC, readable review, mutation423 while quarantined,
then old-preview409 after explicit synthetic recovery release, and logout revocation. See
`increment6-recovery-quarantine.json` and `increment6-recovery-release.json`. No original/development
database was overwritten. Generated archives remain ignored. Hosted recovery/PITR latency is untested.

Final recovery review added a monotone cutoff that also covers the latest existing request timestamp,
so a request recorded during an erroneous future sample cannot survive restoration. The disposable
clone probe `increment6-recovery-monotone-cutoff.json` verifies future-dated requests are invalidated
and a prior future cutoff cannot be lowered. It uses explicit administrative timestamp fixtures only
in the restored clone; the source database and archive remain unchanged.

## Material limitations and remaining actions

Recommended Render Ohio configuration is **$47/month USD**: one 1 CPU/2 GB app ($25), 1 GB PostgreSQL
($19), 10 GB storage ($3), before usage/tax/domain/registry/offsite archive costs. Official sources,
date, retention and exact startup/secret/migration configuration are in the deployment plan.

Native AMD64 execution/build could not run (`exec format error`); Render requires AMD64. Live Google
client/verified owner subject, HTTPS/cookies/proxy behavior, actual phone review, host time correctness,
hosted role setup/capacity/PITR and current Yahoo rules/schedule/source freshness remain unverified.
The minimum next step is a native AMD64 build-and-test environment and review of the concrete hosting
proposal, followed by explicit authorization for provisioning/deployment and the listed OAuth inputs.

No unresolved correctness defect was identified in completed checks. Erroneous future clock samples
remain deliberately fail-closed: preserve authority, quarantine, verify time and wait for real UTC to
catch up; use Yahoo if that is impractical. No automatic recovery can unlock games. Restored facts must
be checked against current Yahoo before administrative release, even when byte-level recovery succeeds.

Initial failures are retained/described rather than counted as passes: direct container package TLS
failure, missing Linux dependency, non-root lock-file permission, Python's unsupported `-infinity`
timestamp, the inherited local OIDC process occupying the test port, and test-harness fixture/child
detection issues. Each applicable defect was corrected and rechecked. Automatic approval review blocked
the requested stop of the isolated DB for an outage drill (“blocked by policy”); the safer unavailable-port
handler check passed, but an actual running-container DB outage/reconnection drill remains pending.

Local review remains at [http://127.0.0.1:8765](http://127.0.0.1:8765), normal synthetic sign-in.
Choose “Late swap browser verification” or “Synthetic image resource acceptance”; resize below 801px
for review mode. Docker containers `dfs-increment6-app`, `dfs-increment6-oidc`, and
`dfs-increment6-postgres` are isolated and labeled. The earlier launcher was stopped to free its ports;
its database was preserved. The local commit identifier is supplied in the delivery response.
