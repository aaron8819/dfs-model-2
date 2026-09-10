# Native AMD64 verification passed

September 10, 2026. **Native AMD64: PASS. Weekly release: UNACCEPTED.**
The actual private Actions artifacts were downloaded and inspected. Native image, database,
application/solver and browser checks passed after one narrow synthetic-harness correction.
No application portability defect was found. No deployment, paid runner, registry publication,
Google configuration change, historical benchmark suite or live outage injection occurred.

## Source, destination and budget

Private personal repository: [aaron8819/dfs-model-2](https://github.com/aaron8819/dfs-model-2).
Branch/default branch: `codex/increment-6-amd64-verification`.
Successful [run 34511914132](https://github.com/aaron8819/dfs-model-2/actions/runs/34511914132)
tested snapshot **`ecf145eb6b1355b0a15933787ea266cf73c13a29`**, equivalent to local source
**`5b54e88ae792e4875b4d5ce34555c9463f554b81`** under its `SOURCE_EQUIVALENCE.json`.
Prior code derives from `72f67ab`; its full commit and all file hashes are in that manifest.

The snapshot contains 95 reviewed current files and 33 prior files plus the manifest.
Original private history/fixtures were never pushed. CI checked every tracked snapshot
file before building; downloaded current/prior SHA-256 and byte counts were independently
compared with the corresponding original local Git blobs. These are different commit IDs,
not a claim that a sanitized snapshot equals the original Git commit. Production Dockerfile,
lockfiles, application, migrations and solver bytes did not change in this execution task.

The user confirmed 2,000 included minutes and 0.5 GB included storage via the billing dashboard.
The task's stricter total cap was 60 Linux runner minutes and 20 MiB artifacts for one day.
Two jobs consumed 147 + 378 = **525 seconds (8m45s)**; rounding each job upward reserves
**10 of 60 minutes**. This is a conservative task accounting figure, not a billing API reading.
No further runs were dispatched. Artifact metadata reports **2,539,896 bytes total (2.42 MiB)**,
one-day retention, below the 20 MiB cap. No billing settings or credential scopes changed.

| Attempt | Snapshot | Job duration | Result | Artifact bytes / expiry UTC |
| --- | --- | --- | --- | --- |
| [34511464239](https://github.com/aaron8819/dfs-model-2/actions/runs/34511464239) | `d65e36c` | 2m27s | Native image checks pass; prior tests 62 pass / 1 fail | 18,398 / September 11 18:00:58 |
| [34511914132](https://github.com/aaron8819/dfs-model-2/actions/runs/34511914132) | `ecf145e` | 6m18s | Full selected procedure pass | 2,521,498 / September 11 18:09:12 |

Downloaded artifacts and logs remain locally under `artifacts/local/amd64-runs/<run-id>/`.
The successful artifact directory is `amd64-evidence-34511914132-1`. Session-bearing traces,
raw database archives, environment dumps and raw failure payloads were not uploaded as artifacts.
The final reporting follow-up changes **documentation and source-equivalence manifest only**;
no executable or image input changed after the successful run.

## Native execution and immutable identities

| Layer | Actual successful-run evidence |
| --- | --- |
| Runner | Standard private `ubuntu-24.04`, Ubuntu 24.04.5 LTS; image `20260907.300.1`; `RUNNER_ARCH=X64` |
| CPU / virtualization | AMD EPYC 7763, x86_64; Microsoft hardware virtual machine |
| Kernel / Docker daemon | `6.17.0-1022-azure`, x86_64; 2 CPUs, 8,328,302,592 bytes RAM |
| Native gate | Runner, host, daemon and container architecture assertions pass; no registered QEMU CPU emulators |
| Runtime | Container x86_64; Python 3.13.15; UID 10001; OR-Tools 9.15.6755 |
| Build runtime | Node 24.21.0; exact locked Python wheels and npm dependencies; pinned Docker bases |
| PostgreSQL | 17.11 bookworm, AMD64, separate disposable restricted-role databases |

Successful runtime image ID: `sha256:27993df978c58fc58c3902bdea4a048e7a198ec1312116468218b6e392b0686d`.
Successful migration image ID: `sha256:2e26e94814fb83cabcaff69259dc14b57acb684af4bacc0487bc84df7d0d7c9d`.
PostgreSQL image ID: `sha256:a2ea0e68c465e0acf4c3672471b22b6b62972bb341e6f31544c855d85ba43745`;
repository digest `postgres@sha256:051f7b7b3abdd564d5d1bd1e8c4b9c1b6e77087d1dd22020ede611c096a272e0`.
Application/migration IDs describe local runner images, not registry-published digests.
The ephemeral images were not exported; deployment requires a separately authorized build/publish.

Base indexes remain Node `sha256:2fe369e969550cde8e867afc3fe370b260140cab4a23d467074295b42163d553`
and Python `sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e`.
Resolved platform manifests, tool versions and input hashes are in `build-inputs.txt`;
wheel hashes in `increment6-wheels-amd64.json`; installed runtime versions in
`runtime-packages.json`. Every retained runtime dependency matches its lock version.
Only Black, coverage, pytest, pytest-cov and Ruff are deliberately absent. No versions
were substituted. Pip consistency, frontend contents, excluded test/fixture/migration files,
non-root execution and migration-environment-secret exclusion passed.

## Checks actually executed

| Check | Result and downloaded evidence |
| --- | --- |
| Prior `0004_increment5` synthetic population | **62 passed in 48.06s**, 3 private-fixture tests deselected; `prior-synthetic.xml.json` |
| Fresh migration and populated upgrade | Pass; 39 preexisting domain tables have identical before/after row counts and hashes; only operational_state/event added (Alembic marker changes expected). Population includes 22 raw blobs and 22 requests; `before.json`, `after.json` |
| Focused current regressions | **174 passed in 113.53s**, 3 private-fixture tests deselected; `regressions.xml.json` |
| Regression scope | Exact arithmetic/tiny exhaustive oracle, integer-bound validator, fixed-slot constraints, native child lifecycle, application/OIDC, completion, decisions, late swaps, clock pool/monotonicity, transactions/retries/stale Apply, and three artifact/snapshot safety tests |
| Actual production runtime image workflow | Normal synthetic OIDC -> import/activate -> captured solve -> native child -> independent validator -> saved result -> Apply200; completion and three alternatives; `increment6-image-resources.json` |
| Busy and concurrent reads | Concurrent solve409, ready alternatives, two authenticated reading tabs, sampled DB connections; resources and polling JSON |
| Real child interruption and restart | Observed worker.py before SIGTERM, exit0/no OOM, restarted readiness, exact saved assignments retained; status interrupted and Apply409; no surviving child after browser checks |
| Decision workspace browser | Pass, 12.729s, retry0; context, alternatives, Apply, Undo, entered attestation and conflict |
| Late swaps/reconciliation browser | Pass, 15.728s, retry0; fixed slots, stale capture, remainder Apply, entered authority, reconciliation and second-tab conflict |
| Mobile browser | Pass, 2.570s, retry0; 320/390/430 widths, keyboard/scroll, no horizontal overflow or mutation requests |
| Production synthetic-identity rejection | Pass; explicit error in `production-rejection.txt`; normal workflow deliberately uses development identity |
| Schema/grant negative and positive controls | Startup pass -> incompatible schema rejection -> unsafe grants rejection -> repaired startup pass; `startup-controls.txt` |
| Runtime evidence mutation denials | raw_blob UPDATE and operational_event DELETE rejected; `grant-denials.txt` |
| Unavailable-endpoint handler | Ready503/health200 in isolated no-network probe, not a previously connected running app; `unavailable-handler.json` |

Counts are distinct within each recorded run, but prior/current suites overlap semantically;
do not add them as unique product cases. Browser results have no skipped, flaky or retried
tests. The decision browser records expected 401/409 console responses with no unexpected
errors; late-swap errors are empty. Desktop remainder/reconciliation and mobile 320 lineup/
430 briefing screenshots were visually inspected and show the intended synthetic review,
fixed assignments and read-only controls. Actual-phone acceptance remains separate.

## Representative resources and ARM64 comparison

App envelope **1 CPU / 2 GiB / 128 PIDs**, one worker; each disposable DB **0.5 CPU / 1 GiB**.
Main workload: 541 entries and 541 matched/admitted projections, similar synthetic point
values, nine slots. The browser remainder uses a separate 13-entry synthetic pool and
four fixed slots (RB2, WR2, TE, FLEX); it is not a 541-entry remainder benchmark.

| Observation | Native AMD64 | Historical ARM64 |
| --- | ---: | ---: |
| Creation to readiness | 1.802s | 1.805s |
| First completion including polling/busy checks | 5.395s | 5.372s |
| First / repeated three alternatives | 8.897 / 8.805s | 8.784 / 7.962s |
| Small browser remainder preview | 3.561s | Not recorded |
| Main workload cgroup peak before restart | 148.82 MiB | 150.11 MiB |
| Post-restart/browser cgroup peak | 212.56 MiB | Not comparable |
| Instrumented GET mean / maximum | 0.0819 / 0.1989s (136 reads) | 0.201 / 0.376s (77 reads) |
| Two-tab workspace+research pair | mean0.369s, range0.274-0.461s, 24 pairs | range0.326-0.756s |
| Sampled runtime DB connections | peak4, 206 samples | peak4, 148 samples |
| Observed-child shutdown | 0.407s, exit0, no OOM | 1.196s, exit0, no OOM |

Memory is cgroup memory including parent, children and cache, not Python RSS. The later
peak is larger than the pre-restart sample; memory.events reports zero OOM/oom_kill.
Read sample counts/phases differ, so they do not establish a controlled speedup. Remainder
evidence captures its exact fixed assignments; the inspected applied alternative shows
49.25 editable points plus 40 fixed pregame points, retaining four fixed identities. The
synthetic exhaustive fixed-slot regressions establish mathematical behavior separately.
No live remaining-points forecast is implied. CPU throttling under the one-core quota was
observed; no assertion/deadline/grant was relaxed. Retain proposed service sizes.
GitHub performance does **not** prove Render CPU, networking, storage, restore or capacity.

## Failure, correction and remaining gates

First run failed at `test_historical_reported_absence_remains_historical`, which also calls
`prepare(client, True)` and needs a prohibited historical fixture. The earlier two-test
exclusion was incomplete. The corrected procedure explicitly deselects all three such
tests; synthetic fixed/availability and historical-correction tests remain. Private fixtures
were not uploaded and test assertions were not weakened. Prior JUnit now writes directly
to an evidence mount even if pytest fails. Artifact upload requires successful bounded
collection; the per-attempt collector limit is 19 MiB, leaving space for the first failure.
The corrected complete procedure passed. No unresolved application correctness defect was
identified within this synthetic verification scope.

| Release gate | State |
| --- | --- |
| Native AMD64 verification | **PASS**, successful run and inspected artifacts above |
| Live DB outage/reconnection | **PENDING / disabled** under previous automatic approval rejection |
| Render deployment and hosted capacity | Pending; no provisioning/deployment authorized or performed |
| Google/HTTPS and owner rejection | Pending; synthetic development OIDC is not live identity acceptance |
| Hosted clock correctness | Pending; monotonicity regression tests do not establish correct UTC |
| Hosted backup/recovery | Pending; this run did not establish hosted backup/PITR or restore behavior |
| Actual-phone review | Pending; browser viewport emulation only |
| Current Yahoo contest/schedule/rules/source acceptance | Pending; synthetic data only |

The exact live outage test remains: previously connected running app, temporary database
unavailability, bounded failures/readiness, restored connectivity without app restart,
safe leases/idempotency/stale-result rejection, then a successful read and legitimate
mutation. No stop/pause/network fault was injected into a database. The successful handler
probe cannot close this gate or override its earlier approval rejection.

**Recommended next action:** review the existing hosted verification/deployment proposal
and its remaining gates before separately authorizing any provisioning. Weekly release
remains unaccepted; no increment 7. The native procedure and Actions handoff preserve the
bounded commands and correction for future separately budgeted verification.

---

# Earlier accepted preparation evidence

September 10, 2026. **Native AMD64: pending. Weekly release: unaccepted.**
No authorized native AMD64 environment was found. Independent preparation is complete;
this task stops here without provisioning, pushing, external CI, deployment or increment 7.
The [native-machine procedure](docs/AMD64_VERIFICATION_PROCEDURE.md) records prerequisites,
commands, isolation, measurements, evidence collection and remaining manual controls.

## Source and environment

Started with a clean working tree at `1f7be13dae42aa95990c1524f410871641694d19` on
`codex/increment-6-release`. HEAD equaled the accepted implementation; ancestry check passed.
Created `codex/increment-6-amd64-verification` directly from it. No unrelated changes were
present or replaced. The local verification commit contains only the changes listed below
and their evidence/documentation; application domain/solver/migration source is unchanged.

| Layer | Actual evidence | Interpretation |
| --- | --- | --- |
| Physical CPU | Snapdragon X 12-core X1E80100; Win32_Processor Architecture=12 | ARM64 hardware |
| Operating system | Windows 11, OSArchitecture `ARM 64-bit Processor` | ARM64 OS |
| Docker | Desktop Linux aarch64, WSL2 kernel 6.6.87.2; 12 CPUs, 16,508,788,736 bytes available | Native ARM64 execution |
| Available contexts | `default` and `desktop-linux`, both local named pipes | No configured remote native runner |
| WSL inventory | Ubuntu stopped; Docker Desktop distributions running, version2 | Same ARM64 host; no AMD64 hardware established |
| Local Python regression process | Python3.14.0, win-amd64, PE machine0x8664 | AMD64 executable under Windows-on-ARM translation; **not native AMD64** |
| New image smoke | Linux arm64, Python3.13.15, OR-Tools9.15.6755 | Native ARM64 only |

`platform.machine()` from Windows Python misleadingly reported ARM64 despite its AMD64 PE
header; interpreter build/sysconfig and physical-host evidence disambiguate it. Neither
that process nor a linux/amd64 label closes the native gate. No AMD64 image was executed,
no known exec-format failure was repeated, and no emulator was installed. No credential
search was used to infer external authorization. Environment evidence:
`artifacts/amd64-preparation-environment.json`, `amd64-preparation-python.json`.

## Narrow preparation fixes and results

1. `web/e2e/late-swap.spec.ts` now chooses the platform's venv Python, with an explicit
   `DFS_TEST_PYTHON` override. Previously its Windows-only executable blocked Linux browser
   verification. Synthetic-game/deadline checks and normal OIDC remain unchanged.
2. `tools/image_acceptance.py` records Docker/container architecture observations instead
   of hardcoding an ARM64/native claim. It requires readiness after restart and specifically
   requires `interrupted` plus Apply409. Previously a ready result could skip the rejection
   assertion and falsely appear to verify interruption. Native hardware still requires
   separate evidence. Full resource/restart rerun remains pending on the native machine.
3. Docker runtime now removes Black, coverage, pytest, pytest-cov and Ruff after locked
   installation. Static review found these development tools installed by the shared
   requirements lock despite excluded test files. Runtime dependency versions, base and
   migration target are unchanged. A narrow ARM64 rebuild verified removal and dependency
   consistency. The original accepted image tag and running review services were preserved.

| Executed check | Result / evidence |
| --- | --- |
| Focused solver exact arithmetic/exhaustive tiny oracle, independent bounds/validator, child lifecycle | **75 passed in45.52s**, Windows AMD64 Python under ARM translation; `artifacts/amd64-preparation-local-regressions.xml` |
| Black and Ruff on changed Python tool | Pass |
| Strict browser-test TypeScript with Bundler resolution and Node types; Prettier | Pass |
| Native handoff command syntax | Six Bash blocks passed `bash -n`; embedded Python compiled. Commands were not executed as an AMD64 procedure. |
| Existing production Dockerfile runtime rebuild, linux/arm64 | Pass; distinct local tag `dfs-increment6:amd64-preparation-arm64` |
| UID10001, frontend index, absence of test files/tools/fixtures/migrations/local env, imports, pip check | Pass; `artifacts/amd64-preparation-image-check.txt` |
| Actual child solve inside rebuilt ARM64 runtime at1CPU/2GiB/128PIDs, no network | OPTIMAL, exact objective90000 units, nine slots; independent validator accepted; `artifacts/amd64-preparation-arm64-child.json` |
| Production synthetic-identity rejection / explicit development Settings acceptance | Pass configuration-only in rebuilt ARM64 image; same image-check artifact; not a new OIDC workflow pass |

Initial verification-command mistakes were corrected: TypeScript first used NodeNext from
the repository root, producing missing Node types/extension errors; rerunning from web with
its Bundler configuration passed. A shell-quoted one-line configuration probe had a Python
syntax error; a multiline stdin probe passed. Neither initial attempt is counted as a pass.
No database, clock, full browser or representative load tests were rerun locally. The
75-test run is separate from production-image validation, and is not AMD64 native evidence.

## Image identity and resource limits

New local ARM64 runtime image ID/index:
`sha256:1e3869103654f7a1a60c1990ddff44cf272e6aaa5c440c53661dd6df4308f3b6`.
Build emitted config `sha256:4143a5d1ea3693fa9ef8dc4ee128d5e4339e0cbe44540d74b0cd41c579d1b23d`
and runtime manifest `sha256:42da6ac556ae3b805ff4d899fa53bbb13cfc3eb4f0df66a77a6d32903359780c`.
Existing ARM64 migration image was inspected, not rebuilt or executed:
`sha256:a5ec42fd086ffd504d076757094a8fb886d619d73ac919cf57592cd206d8eefd`.
See `artifacts/amd64-preparation-image-ids.txt`; local RepoDigests do not imply a push.

Unchanged pinned bases:

- Node24.21.0 bookworm-slim: `sha256:2fe369e969550cde8e867afc3fe370b260140cab4a23d467074295b42163d553`.
- Python3.13.15 slim-bookworm: `sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e`.

Locked wheels came from the existing ARM64 wheelhouse; no versions changed. Installed
versions are recorded in `artifacts/amd64-preparation-runtime-packages.json`. The small
11-entry solver smoke recorded1.214s elapsed and107,646,976 bytes child/runner peak RSS.
This is **not container peak memory or representative resource evidence**. No database
was used. There are no new startup,541-entry completion/alternatives/remainder, DB connection,
concurrent-read, shutdown or restart measurements. All native AMD64 measurements are pending.

Historical ARM64 evidence remains in INCREMENT_6_REPORT.md: app1CPU/2GiB, DB0.5CPU/1GiB,
541 entries/projections, readiness1.805s, complete5.372s, alternatives8.784/7.962s,
container peak150.11MiB, DB peak4, read mean/max0.201/0.376s. No numerical cross-architecture
performance comparison is possible yet. Retain proposed service sizes; neither this tiny
smoke nor low prior memory justifies shrinking. Local quotas cannot reproduce hosted CPU,
network or storage behavior. No current hosting price is quoted or revalidated in this follow-up.

## Deployment review and remaining gates

Static review of DEPLOYMENT_PLAN.md, compose.release.yml, Dockerfile, config/startup,
persistence/clock pools, migrations and runbook found the intended contract consistent:
AMD64 target; separate Alembic migration command/credential; restricted runtime role;
one Uvicorn worker, port8000, proxy/access logs disabled and40s graceful shutdown;
1CPU/2GiB app,0.5CPU/1GiB local DB; five domain plus one independent clock connection;
configured HTTPS origin and secure production cookies; offline quarantine before restored
state becomes actionable. Synthetic workflow tests explicitly use development mode.
Local/native verification is not live Google, hosted grant, proxy or backup acceptance.
The packaging correction above is the only production-image change from this review.

Native fresh migration, populated upgrade from `0004_increment5`, immutable data hashes,
bad-schema/grant startup rejection, runtime evidence-mutation denial, full API→child→validator→
saved result→Apply, bounded alternatives, fixed remainder, stale Apply, retries, two tabs,
child interruption, persistence and three browser scenarios all remain **pending**.
The procedure uses accepted prior code to create synthetic populated data; it needs no
copy of a real database. It also documents fixed ports/names, OIDC sequencing, cgroup-v2
requirements, artifact filenames and the mobile test's dependency on late-swap evidence.

**Live outage/reconnection remains pending.** The earlier automatic approval rejection of
the isolated database stop remains binding. No stop, pause, network disconnection, proxy or
alternate fault injection was attempted. No distinct permitted method was established.
The procedure states the required previously-connected app, bounded failures/readiness,
restore, same-key receipt checks, safe lease/Apply behavior and positive recovered read
AND mutation controls. An unreachable-port startup check remains insufficient.

Remaining external actions are separate: approved hosting configuration/spending; native
hosted load; Google client, verified owner and exact HTTPS/callback; hosted clock accuracy;
hosted backup/recovery/PITR; actual phone/browser review; and current Yahoo contest/rules,
schedule and source acceptance. None was authorized or performed by this task.

**Minimum next action:** provide access to an already authorized native x86-64 Linux
machine with the prerequisites above and an approved local copy of this branch/history.
Run the prepared procedure, collect actual evidence and resolve the separately permitted
outage method before making the next deployment decision. No environment access is assumed.
