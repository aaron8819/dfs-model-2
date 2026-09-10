# Native AMD64 verification procedure

Prepared September 10, 2026. **Executed successfully on native AMD64:** [run 34511914132](https://github.com/aaron8819/dfs-model-2/actions/runs/34511914132). The current task authorizes a
private GitHub Actions verification snapshot. See [Actions handoff](AMD64_ACTIONS_HANDOFF.md).
The canonical commands now live in `tools/amd64_verify.sh`, reused from this procedure.
Only the reviewed snapshot is pushed; its manifest records current and prior source hashes.
No original Git history or historical fixtures are transported. The script intentionally
requires the intended private Actions repository and a native x64 runner.

## Prerequisites and isolation

Original standalone planning allowance: 4 CPU cores, 8 GiB RAM and 15 GiB free disk.
The authorized standard private Actions VM supplies 2 CPUs, 8 GB RAM and 14 GB SSD;
execution is serial and capacity/disk sufficiency must be observed, not assumed. App limits remain 1 CPU / 2 GiB / 128 PIDs, PostgreSQL
0.5 CPU / 1 GiB; one worker and 40-second graceful shutdown. Need Docker Engine/BuildKit,
cgroup v2, native Python 3.13 with pip/venv, Node 24.21.0/npm, Git, curl, and permission to
download pinned bases, locked wheels/npm packages and Playwright Chromium dependencies.
No production secrets, private fixtures or real user data are needed.

These Bash commands run from the repository root on a dedicated machine. Existing tools
use fixed names and loopback ports. Abort on ANY collision; do not repurpose existing
containers, volumes, ports or databases. Run tests serially. Never run this procedure on
the original ARM64 host: its increment-6 containers are existing review resources.

**Executable commands:** Native host gate in [`tools/amd64_verify.sh`](../tools/amd64_verify.sh).

The Actions runner contract documents the selected VM as x64. Capture runner image/version,
CPU model, kernel, daemon and container machine; fail on non-X64 runner or registered QEMU
CPU emulators. Never infer native execution solely from an image platform label.
The runner must use its local Docker daemon; no remote builder or emulation setup is used.

## Locked builds and image checks

**Executable commands:** Locked builds in [`tools/amd64_verify.sh`](../tools/amd64_verify.sh).

Retain wheel manifest, lockfile hashes, base index digests from Dockerfile, and resolved
AMD64 base manifests from build logs/`docker buildx imagetools inspect <pinned-base>`.
The test-base retains test dependencies; runtime explicitly removes development tools.
No dependency versions are substituted. Record local image IDs and RepoDigests; an empty
RepoDigests list is normal for a local build and must not be represented as a pushed digest.
Inspect `/app` recursively for unexpected files; review `.dockerignore` and every COPY.

## Disposable databases, fresh migration and populated prior upgrade

**Executable commands:** Fresh and prior databases in [`tools/amd64_verify.sh`](../tools/amd64_verify.sh).

The prior-code API tests populate linked synthetic domain data under accepted schema
`0004_increment5`, including imports, drafts, requests/results and entered records.
No production dump or private fixture is used. Tests must pass before upgrading.
Capture all public table contents in canonical order before and after:

**Executable commands:** Upgrade preservation and focused regressions in [`tools/amd64_verify.sh`](../tools/amd64_verify.sh).

The test-base run validates exact arithmetic/oracle results, upper bounds, fixed slots,
clock observations, child lifecycle, retries and database authority. It is a test harness
using the locked image base; it does not replace the following actual runtime-image HTTP test.
Do not run `server.benchmark` or the historical 88-run suite. Record failures without
loosening limits. Compare exact objectives only for proven optimal comparable instances;
bounded feasible solutions can legitimately differ across CPUs.

## Runtime image, normal synthetic OIDC and resources

Run the following only AFTER the test fixture's OIDC thread has exited and port 8766 is free.
Synthetic env files are private ignored files; never add them to Git. Trust authentication
is restricted to these disposable task-only databases and is not a hosting configuration.

**Executable commands:** Runtime and browser workflow in [`tools/amd64_verify.sh`](../tools/amd64_verify.sh).

Install browser OS dependencies only under the authorized local machine's normal package policy. Running app
on loopback 8765 is a harness port override; all production worker/proxy/shutdown settings
are retained. Development identity is explicit; production Google/HTTPS is a separate gate.

Existing reports/screenshots use increment-6 filenames. Use a fresh checkout and preserve
the accepted artifacts in Git; copy new outputs under the AMD64 run directory and restore
ONLY overwritten tracked artifact files after collecting them. Do not commit synthetic
cookies, authorization codes, full traces, env files, dump files or raw inspect environments.

Resource evidence: subtract readiness/start timestamps; use image_acceptance's first
completion, alternatives, 541-entry/541-projection pool and cgroup memory. image_polling
records runtime DB connections and two-tab read timings. The late-swap browser evidence records remainder preview wall latency and exact fixed slots;
retain candidate objective and validation from saved browser evidence/API state. Traces remain
disabled because they can contain session credentials.
Capture cgroup `memory.peak`, `cpu.stat`, `memory.events` immediately after browser scenarios
as well (the app was restarted by image_acceptance). Record `docker top` before/after
interruption, zero surviving worker.py, exit0/no OOM, restored assignments, interrupted
result and Apply409. A solve that finishes before interruption is inconclusive and the
now-strict harness fails; repeat that focused drill, never label a ready result interrupted.

Production-mode negative controls use another disposable cloned DB. Run after the serial
regressions, when no connection remains to their database. This tests the actual runtime
lifespan with structurally valid synthetic placeholders; no live Google login is attempted.

**Executable commands:** Startup and restricted grants in [`tools/amd64_verify.sh`](../tools/amd64_verify.sh).

Retain stdout/status for each startup control. The CI command tees these into the allowlisted
startup-controls file. The separate unavailable-endpoint handler check has no running-app lifespan
and is explicitly not live reconnection. Each permission attempt is a separate
transaction/connection, rolled back on failure. These controls remain pending until
their actual outputs are collected; positive grants checks alone cannot establish rejection.

## Outage/reconnection gate — pending, no injection authorized by this recipe

The previous automatic approval review rejected stopping the database. Do not stop/pause
it, disconnect its network, block its port or introduce a proxy to achieve that rejected
action indirectly. No distinct permitted fault mechanism has been established here.
The following is the exact acceptance sequence for a separately permitted fault mechanism;
the injection/restoration commands must be supplied and reviewed with that mechanism's scope:

1. Prove ownership/labels/database/network and isolation from unrelated resources. Start
   a normal authenticated session; successful read and mutation establish live connection.
2. Save a ready preview and its revisions, start a new solve, and observe its real child.
   Record request IDs, idempotency keys, receipts, lease and monotone clock/lock evidence.
3. Inject the permitted temporary loss only on that disposable app/database connection.
   Measure `/ready`503 and `/health`200; time failed read/mutation and poll calls. Check
   against connect3s, checkout8s, statement15s/lock7s and clock2s/1s timeouts; include elapsed
   multi-stage request time rather than assuming each request has one timeout.
4. Restore connectivity using the permitted mechanism. Poll `/ready` to200 with timestamps,
   without restarting the application. A legitimate authenticated read and a new mutation
   must succeed. Repeat the interrupted mutation's SAME idempotency key: either one existing
   receipt/result or one new commit, never duplicates or an invalid success receipt.
5. Confirm interrupted/expired solve cannot Apply, no orphan child/active lease, and no
   stale preview can Apply after the successful recovery mutation. Compare saved assignments,
   immutable evidence and receipts. Capture all status codes and exact revisions.

An unreachable-port startup/TestClient probe is not this test. Keep the gate pending if a
permitted fault mechanism or any required observation/control is missing.

## Decision and evidence handoff

Record actual source commit, images, platform attestation, versions, limits, test counts,
sanitized logs, XML/JSON/screenshots and every failed attempt. Compare to the ARM64 report:
startup1.805s, completion5.372s, alternatives8.784/7.962s, peak150.11MiB, DB peak4 and read
mean/max0.201/0.376s. No previous representative remainder latency was recorded. These are
historical representative observations, not correctness thresholds. Local quotas do not
reproduce hosted CPU performance, network or storage. Retain proposed sizing until native
and hosted evidence supports a change; low memory alone does not justify shrinking.

Update AMD64_VERIFICATION_REPORT.md and acceptance matrix only for executed checks.
Keep separate gates for approved hosting/spending, hosted AMD64 load, Google client/owner
and HTTPS, host clock evidence, hosted recovery/PITR, actual-device review, and current
Yahoo contest/rules/schedule/source acceptance. Do not quote fresh prices without checking
official dated sources. No deployment, provisioning or increment 7 follows this run. Reviewed verification commits may be pushed under the current task authorization.

## September 10 execution result

The complete corrected procedure passed; see [report](../AMD64_VERIFICATION_REPORT.md).
Three private-fixture tests are explicitly deselected, including the reported-absence test
missed in the first attempt. Prior JUnit is written directly to the evidence mount so test
failure does not lose it. Upload runs only after successful size-bounded artifact collection.
The successful job cap was 20 minutes, with a 15-minute procedure cap and 19 MiB per-attempt
artifact check; total actual artifacts across both attempts were 2.42 MiB. Do not treat this
successful task as authorization for future runs or additional spending. The outage sequence
above remains pending and disabled. Final report-only edits did not change executable inputs.
