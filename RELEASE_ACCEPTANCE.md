# Increment 6 release acceptance

**Weekly release not accepted. Native AMD64 verification passed.** The private Actions
run and downloaded evidence cover the selected synthetic image/database/application/browser
procedure. Hosted verification and live-source acceptance remain separate gates.

Evidence: [native AMD64 report](AMD64_VERIFICATION_REPORT.md),
[successful run](https://github.com/aaron8819/dfs-model-2/actions/runs/34511914132), and
[original increment-6 evidence](INCREMENT_6_REPORT.md).
Tested snapshot `ecf145e` maps to local source `5b54e88` by the verified hash manifest.
62 prior-schema tests, 174 focused current tests and three browser scenarios passed.
One earlier private-fixture selection failure was corrected and the complete procedure rerun.
No product/image input changed after that pass; final updates are documentation only.
Two jobs used 8m45s total (10 rounded runner minutes), artifacts 2.42 MiB retained one day.

| Required behavior | Method / actual environment | Evidence path | Status / exact pending prerequisite |
| --- | --- | --- | --- |
| Mobile read-only review | Browser 320/390/430, keyboard, scroll, no mutation requests | artifacts/increment6-final-image-browser.json; artifacts/increment6-mobile-*.png | Pass emulation; owner's actual phone/browser pending |
| Atomic clock; bounded observation cost | Five occupied domain connections, dedicated clock pool, PostgreSQL | artifacts/increment6-boundaries-final.xml; artifacts/increment6-operations.xml | Pass locally |
| Integer-only upper-bound proof | ULP, integer gap, below-objective, nonfinite checks | artifacts/increment6-boundaries-final.xml | Pass locally; raw diagnostics retained |
| Non-root locked image and solver child | Docker Linux AMD64 native on standard private Actions VM | artifacts/increment6-image-identity.json; artifacts/increment6-image-resources.json | Pass native AMD64; see AMD64_VERIFICATION_REPORT.md for tested image IDs and run |
| Fresh and populated upgrade | Fresh DB; clone of accepted schema; separate migration image | artifacts/increment6-migrations.json | Pass native AMD64: all 39 old domain table hashes preserved |
| Owner, CSRF, cookie, runtime/config safeguards | PostgreSQL + local OIDC; image startup rejection | artifacts/increment6-final-regressions.xml; artifacts/increment6-production-config.json; artifacts/increment6-operations.xml | Pass native AMD64 synthetic/config checks; live Google/HTTPS pending |
| Weekly workflow, late swaps, conflicts | Final image + synthetic OIDC/slate, three browser scenarios | artifacts/increment6-final-image-browser.json; artifacts/increment6-image-browser-evidence.json | Pass native AMD64 synthetic workflow; actual current Yahoo inputs pending |
| Linked archive and recovery quarantine | pg_dump/fresh restore, hash/grants checks; restored-image HTTP probes | artifacts/increment6-recovery.json; artifacts/increment6-recovery-quarantine.json; artifacts/increment6-recovery-release.json | Pass locally; hosted PITR/retention/restore pending |
| Whole-image sizing, busy, interruption, persistence | 541 entries; app 1 CPU/2 GiB, DB 0.5 CPU/1 GiB | artifacts/increment6-image-resources.json; artifacts/increment6-image-polling.json; artifacts/increment6-image-startup.json | Pass representative native AMD64 workload; hosted capacity remains pending |
| Unavailable DB readiness | Separate TestClient app inside image, unreachable DB port | artifacts/increment6-database-unavailable.json | Pass handler check; running-container outage/reconnection pending: automatic approval review blocked DB stop |
| Live identity and HTTPS topology | Not tested: intended Google owner + second account at exact HTTPS origin | DEPLOYMENT_PLAN.md | Pending: client ID/secret, verified owner sub, chosen origin/callback, authorized deployment |
| Hosted clocks, role setup, capacity and PITR | Not tested: intended Render Ohio AMD64 | DEPLOYMENT_PLAN.md; OPERATIONS_RUNBOOK.md | Pending: authorized paid service/DB, host time-health evidence, native architecture and restore tests |
| Current contest and source facts | Not tested: owner-confirmed current Yahoo slate and files | DEPLOYMENT_PLAN.md live checklist | Pending: actual contest/rules/game/schedule confirmation and current five-file projections |

Local implementation, production-image verification, hosted verification and weekly acceptance
are separate milestones. No external access or spending is authorized by this document. Native AMD64 is complete; review the existing hosting proposal and all remaining gates
before separately authorizing provisioning/deployment. This task did not revalidate prices. No increment 7.

Native evidence is linked above for fresh/upgrade migration, runtime checks and synthetic
browser/resource rows. Historical artifact paths in the matrix retain prior ARM64 evidence;
they are not mislabeled as new native results. The live outage drill remains disabled under
its prior automatic approval rejection, independently of the successful unavailable-port probe.
