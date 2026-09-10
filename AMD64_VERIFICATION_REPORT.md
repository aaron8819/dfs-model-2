# Private Actions preparation complete; native AMD64 pending

September 10, 2026. **Native AMD64: pending. Weekly release: unaccepted.**

The current task authorizes private GitHub Actions verification, reviewed snapshot pushes,
and bounded included-allowance runs. Preparation is complete, but dispatch is blocked by
unknown remaining included Actions minutes and artifact storage. No AMD64 build/test ran,
no run URL or tested image identity exists, and no new native resource measurements are claimed.

## Current follow-up

- Source started clean at accepted `bd8ff57` on `codex/increment-6-amd64-verification`;
  ancestry passed. No unrelated working-tree changes or source remotes were present.
- Authenticated personal account `aaron8819` was established through GitHub API metadata.
  Created [aaron8819/dfs-model-2](https://github.com/aaron8819/dfs-model-2), verified private
  and personally owned. The unrelated public `DFS-optimizer` was not used.
- Original history contains private fixtures and historical artifacts. It is not eligible
  for pushing. The separate sanitized repository uses the same verification branch as its
  initial/default branch, with current and prior-schema code mapped by SHA-256 manifest.
  CI and local commit identities are deliberately different. `SOURCE_EQUIVALENCE.json`
  in the snapshot provides the exact local source commit and per-file relationship.
- Added one canonical executable procedure, a manual-only SHA-pinned workflow, source
  equivalence verification and allowlisted diagnostics. A job has a 60-minute maximum;
  first-run reservation is 60 included Linux minutes plus 20 MiB included artifact storage
  for one day. No dispatch or automatic retries occur until allowance is established.
- Corrected two private-fixture-dependent test selections by explicit deselection only;
  retained synthetic equivalents and all other selected tests. Added remainder preview
  timing and fixed-slot evidence to the existing browser scenario. Product behavior,
  production Dockerfile, dependencies, migrations, grants and solver code are unchanged.
- Local verification: Bash syntax and embedded Python syntax, Black/Ruff, Python
  compilation, browser TypeScript/Prettier, and three handoff safety tests passed.
  The safety tests verify private-file exclusion, changed/extra-file rejection and removal
  of session-bearing failure payloads from artifacts. They do not establish native execution.

The current token cannot retrieve billing usage: HTTP 404 with an explicit missing `user`
scope notice, and no plan value in account metadata. No scope or billing changes were made.
The exact remaining prerequisite is confirmation of the current account's available
included minutes and storage covering the bounded run. See the dated official sources,
action pins, snapshot policy, selection changes and resume instructions in
[AMD64_ACTIONS_HANDOFF.md](docs/AMD64_ACTIONS_HANDOFF.md).

## Pushed preparation identity

Private snapshot pushed on `codex/increment-6-amd64-verification` (also its new default branch).
Initial reviewed snapshot: [`5faf8bc4de7eee8168f3703ce01f85de4f272302`](https://github.com/aaron8819/dfs-model-2/commit/5faf8bc4de7eee8168f3703ce01f85de4f272302),
from local executable preparation `ee5ac2317369a342e07852e49526640fc68138c4`.
The snapshot contains 95 current files, 33 prior files and its equivalence manifest; its
single-root reachable history was screened again: 102 unique blobs / 862,534 bytes,
no flagged private paths, credential patterns or large blobs. Original history stayed local.
Both source and snapshot working trees were clean after their commits/push.

Collection-only checks in the exported snapshot found **175 selected current tests** and
**63 selected prior-schema tests**, each excluding exactly the two private-data tests.
These counts establish collection/import availability only, not test passes. No DB or
solver workload was executed by collection. GitHub's run inventory is empty; there is no
workflow run URL. The subsequent reporting update changes documentation and the source
manifest only; executable preparation is the same as the initial snapshot above.

## Results and outstanding gates

Native fresh migration, populated upgrade, restricted grants, API/native child/validator/
Apply, interruption/restart, browser scenarios and representative resources are all pending.
No native failed run occurred; the concrete preparation defects above were found locally.
Historical ARM64 observations remain below for later comparison. Retain app 1 CPU/2 GiB
and DB 0.5 CPU/1 GiB; GitHub's 2-CPU VM performance will not establish Render capacity.

Live outage/reconnection remains disabled under the earlier automatic approval rejection.
The script includes only the permitted independent unreachable-endpoint handler check;
it cannot prove reconnection of a previously connected running app. The exact outstanding
sequence remains in the [procedure](docs/AMD64_VERIFICATION_PROCEDURE.md).

Separate remaining gates: native AMD64; live DB outage/reconnection; Render deployment and
hosted capacity; Google/HTTPS and owner rejection; hosted clock correctness; hosted
backup/recovery; actual-phone review; current Yahoo contest, schedule, rules and sources.
No deployment, registry publication, Google configuration changes or increment 7.

**Recommended next action:** establish at least 60 remaining included Linux Actions minutes
and 20 MiB available included artifact storage for one day on `aaron8819`, then dispatch the
reviewed snapshot once and inspect its downloaded evidence before updating acceptance.

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
