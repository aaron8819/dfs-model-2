# Increment 6 release acceptance

**Weekly release not accepted.** Local implementation/preparation complete. Production image verified
on native ARM64 only; required AMD64 pending. Hosted verification pending. Synthetic evidence does
not establish live Yahoo, Google identity, correct host time or hosted capacity.
Details: [INCREMENT_6_REPORT.md](INCREMENT_6_REPORT.md).

AMD64 follow-up: [verification prepared; native execution pending](AMD64_VERIFICATION_REPORT.md).
The available host is ARM64; Windows AMD64 Python runs under translation. Preparation includes
75 focused local regression passes, a narrow ARM64 packaging smoke and stricter portable harness
checks. These do not close native AMD64, full updated-image workflow, sizing or live reconnection
gates. The runtime development-tool removal requires native verification with the updated image.

Private Actions follow-up: [prepared handoff](docs/AMD64_ACTIONS_HANDOFF.md). A private
personal verification repository has been created; only a reviewed synthetic snapshot is
eligible for push. Native execution remains **pending: confirm 60 included Linux minutes
and 20 MiB included artifact storage before dispatch**. No native run or resource result is
claimed. Three local snapshot/artifact safety tests pass; they do not close this gate.

| Required behavior | Method / actual environment | Evidence path | Status / exact pending prerequisite |
| --- | --- | --- | --- |
| Mobile read-only review | Browser 320/390/430, keyboard, scroll, no mutation requests | artifacts/increment6-final-image-browser.json; artifacts/increment6-mobile-*.png | Pass emulation; owner's actual phone/browser pending |
| Atomic clock; bounded observation cost | Five occupied domain connections, dedicated clock pool, PostgreSQL | artifacts/increment6-boundaries-final.xml; artifacts/increment6-operations.xml | Pass locally |
| Integer-only upper-bound proof | ULP, integer gap, below-objective, nonfinite checks | artifacts/increment6-boundaries-final.xml | Pass locally; raw diagnostics retained |
| Non-root locked image and solver child | Docker Linux ARM64 native | artifacts/increment6-image-identity.json; artifacts/increment6-image-resources.json | Pass ARM64; AMD64 build/execute pending: native AMD64 runner (local exec format error) |
| Fresh and populated upgrade | Fresh DB; clone of accepted schema; separate migration image | artifacts/increment6-migrations.json | Pass: old domain hashes preserved |
| Owner, CSRF, cookie, runtime/config safeguards | PostgreSQL + local OIDC; image startup rejection | artifacts/increment6-final-regressions.xml; artifacts/increment6-production-config.json; artifacts/increment6-operations.xml | Pass locally; live Google/HTTPS pending |
| Weekly workflow, late swaps, conflicts | Final image + synthetic OIDC/slate, three browser scenarios | artifacts/increment6-final-image-browser.json; artifacts/increment6-image-browser-evidence.json | Pass synthetic workflow; actual current Yahoo inputs pending |
| Linked archive and recovery quarantine | pg_dump/fresh restore, hash/grants checks; restored-image HTTP probes | artifacts/increment6-recovery.json; artifacts/increment6-recovery-quarantine.json; artifacts/increment6-recovery-release.json | Pass locally; hosted PITR/retention/restore pending |
| Whole-image sizing, busy, interruption, persistence | 541 entries; app 1 CPU/2 GiB, DB 0.5 CPU/1 GiB | artifacts/increment6-image-resources.json; artifacts/increment6-image-polling.json; artifacts/increment6-image-startup.json | Pass representative ARM64 workload; hosted AMD64 load pending |
| Unavailable DB readiness | Separate TestClient app inside image, unreachable DB port | artifacts/increment6-database-unavailable.json | Pass handler check; running-container outage/reconnection pending: automatic approval review blocked DB stop |
| Live identity and HTTPS topology | Not tested: intended Google owner + second account at exact HTTPS origin | DEPLOYMENT_PLAN.md | Pending: client ID/secret, verified owner sub, chosen origin/callback, authorized deployment |
| Hosted clocks, role setup, capacity and PITR | Not tested: intended Render Ohio AMD64 | DEPLOYMENT_PLAN.md; OPERATIONS_RUNBOOK.md | Pending: authorized paid service/DB, host time-health evidence, native architecture and restore tests |
| Current contest and source facts | Not tested: owner-confirmed current Yahoo slate and files | DEPLOYMENT_PLAN.md live checklist | Pending: actual contest/rules/game/schedule confirmation and current five-file projections |

Local implementation, production-image verification, hosted verification and weekly acceptance
are separate milestones. No external access or spending is authorized by this document. Review the
$47/month proposal and obtain native AMD64 execution before authorizing deployment. No increment 7.
