# Private native AMD64 Actions handoff

September 10, 2026. **Prepared; no run dispatched. Native AMD64 pending. Weekly release unaccepted.**

## Destination and allowance

Authenticated personal account: `aaron8819` (`type=User`). No source-repository remote was
configured. The account's repositories were inspected; none is the intended DFS Model 2.0
destination. In particular, the existing public `DFS-optimizer` is unrelated and must not
receive this code. Created `aaron8819/dfs-model-2` under that authorization; API confirmed private visibility
and personal owner `aaron8819` (`User`).

The user confirmed from the personal billing dashboard that 2,000 included Actions minutes
and 0.5 GB included storage were available before dispatch. This confirmation supersedes
the earlier API limitation (missing `user` scope); no scope or billing changes were made.

The current task has a **total ceiling of 60 Linux runner minutes and 20 MiB of artifacts
retained for one day**, including any corrected attempts. The earlier 180-minute/60-MiB
planning ceiling is superseded. No paid overage, deployment, automatic retry, cache upload,
registry publication or live outage drill is authorized. Before any further attempt,
subtract completed job time (rounded up to runner minutes) and set its timeout within the
remaining total. Download and inspect each attempt's evidence before expiry. Retained
artifact sizes across attempts must remain below 20 MiB.

Official documentation checked September 10, 2026:

- [Standard hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners):
  private `ubuntu-24.04` is an x64 VM with 2 CPUs, 8 GB RAM and 14 GB SSD. This is below
  the handoff's earlier 4-core planning allowance; build and tests run serially, while app
  and each DB retain their existing limits. Disk/CPU sufficiency remains to be measured.
- [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions):
  private runs consume the owner's included allowance; overages are billed. Free includes
  2,000 minutes and 500 MB artifact storage; Pro includes 3,000 minutes and 1 GB. These
  plan totals do **not** establish this account's current remaining allowance.
- [Manual dispatch](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow):
  the workflow must exist on the default branch. Initialize the new sanitized repository's
  `codex/increment-6-amd64-verification` as its initial/default branch; do not modify an
  unrelated existing default branch.
- [Artifact retention/download](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts):
  default retention is 90 days; this workflow explicitly requests one day. Included storage
  is shared with Packages. Download the allowlisted evidence immediately after completion.

## Source review and equivalence

The original Git history contains real private historical fixtures and screenshots/artifacts.
It must never be pushed for this task. No rewrite or force push is needed. The exporter
`tools/prepare_verification_snapshot.py` reads every reachable blob for secret/large-file
screening, then writes only allowlisted code, locked build inputs, selected documentation
and synthetic harness files to a new directory. Pattern screening is not a guarantee that
arbitrary future content is safe; review the selected file diff before every later push.

The initial audit at `bd8ff57` read 373 blobs / 20,725,607 bytes; 174 blobs were flagged as
historical/private artifacts or large files, with no credential-pattern matches. Detailed
metadata stays local at `artifacts/local/amd64-history-audit.json`; matching contents are
never printed. The final export repeats the audit after preparation is committed.

`SOURCE_EQUIVALENCE.json` records the full current local source commit and prior `72f67ab`
commit, with SHA-256 and byte length for every exported file. `verification/prior` contains
only reviewed prior code and synthetic test helpers. Runtime/migration/build inputs retain
their original Git blob bytes. Excluded runtime files (`server/fixtures.py`, benchmark and
fixture tests) are already excluded by the production `.dockerignore`. The CI root commit
is intentionally different from the local commit. CI verifies every tracked snapshot file
against the manifest before building. Keep the manifest with downloaded evidence.

## Executable scope and corrections

`tools/amd64_verify.sh` is the single executable version of the six original procedure
blocks, called by `.github/workflows/amd64-verification.yml`. The workflow is dispatch-only,
private-repository gated, `contents: read`, credential persistence disabled, immutable action
SHAs, repository-wide concurrency without cancelling active runs, 60-minute timeout.
The dispatch input is an operator attestation after checking allowance, not a billing API
or protection against account-wide concurrent spending.

Actions' `v4` checkout, `v5` setup-python, `v4` setup-node and `v4` upload-artifact refs were
resolved to the commit SHAs in the workflow; their action metadata was reviewed. Exact
Python 3.13.15 and Node 24.21.0 are requested, and image bases/dependencies remain locked.
No fallback version is permitted if these inputs cannot be downloaded.

The procedure builds the actual runtime/migration targets, runs fresh migration and a
synthetically populated prior-schema upgrade, compares all domain hashes, exercises actual
API/native-child/Apply and resource/restart tools, runs three browser scenarios, and checks
production identity rejection, unsafe schema/grants and unreachable-endpoint handlers.
Normal browser workflow uses explicit development synthetic OIDC. No production secrets.

Three historical-data tests are explicitly deselected in both applicable regression commands:
`application_test.py::test_historical_import_through_postgres` and
`completion_test.py::test_historical_import_and_server_objectives`, and
`completion_test.py::test_historical_reported_absence_remains_historical`. They require prohibited
private fixtures. Synthetic historical-correction tests remain selected. No assertions or
deadlines were weakened. The old command list would have failed without private fixtures.

The late-swap browser harness now records remainder preview latency and its exact fixed
assignments without uploading a Playwright trace (which can contain session tokens).
Resource timings are observational, not new acceptance thresholds. Raw XML/browser failure
payloads and traces are excluded from artifacts; test names, statuses and durations are
retained. Only explicitly named measurements, identities, hash inventories and generic
startup/grant diagnostics are uploaded, with a 20 MiB size check. A failed procedure remains
a failed job even when diagnostic collection succeeds. GitHub disposes of the job VM;
no database stop, pause or connectivity fault is used for cleanup or an outage drill.

## Resume and evidence review

After the remaining included allowance is established, confirm repository privacy/default
branch and no active run, then manually dispatch `amd64-verification.yml` on the exact
reviewed snapshot commit with `allowance_confirmed=true`. Record its run URL and commit.
Download `amd64-evidence-<run-id>-<attempt>` immediately, inspect test records, final marker,
image IDs, source manifest, architecture and measurements; a green badge alone is insufficient.
Record failed attempts and narrow corrections. Executable changes require affected reruns;
documentation-only changes after a successful run must be identified as such.

Native AMD64 is independent of the still-pending live outage/reconnection, Render deployment
and hosted capacity, Google/HTTPS and owner rejection, hosted clock correctness, hosted
backup/recovery, actual-phone review, and current Yahoo contest/schedule/rules/source gates.
The previously rejected live outage drill stays disabled. Its exact required recovery
sequence remains in the native procedure; an unavailable endpoint does not close it.

## First execution correction

Run 34511464239 on snapshot d65e36c failed after native image checks and fresh migration:
62 prior tests passed, one failed because the third historical-data test above also calls
`prepare(client, True)`. The private data remains excluded. The corrected selection omits
that test explicitly. Prior JUnit now writes directly to the evidence mount so a failing
pytest command cannot skip its collection. Upload requires successful bounded collection.
The next attempt is capped at 20 minutes (15-minute procedure), within the remaining
57-minute task budget. The first artifact was 18,398 bytes with one-day retention.
