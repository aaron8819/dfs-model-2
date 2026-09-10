import { useState } from "react";
import { z } from "zod";
import { api, playerSchema, previewSchema, type Player, type Workspace } from "./api";

const slots = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DEF"];
const historicalAttestation =
  "Correct historical Yahoo facts; this does not authorize a late selection";
const planSchema = z.object({
  preview_hash: z.string(),
  before_entered: z.record(
    z.string(),
    playerSchema.extend({
      subject_id: z.string().nullable(),
      game_id: z.string().nullable().optional(),
    }),
  ),
  entered: z.record(z.string(), playerSchema),
  before_draft: z.record(z.string(), playerSchema),
  draft: z.record(z.string(), playerSchema),
});

export function Reconciliation({
  w,
  disabled,
  reload,
}: {
  w: Workspace;
  disabled: boolean;
  reload: () => Promise<void>;
}) {
  const [rows, setRows] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      Object.entries(w.entered?.assignments ?? w.assignments).map(([s, p]) => [s, p.row_id]),
    ),
  );
  const [historyRows, setHistoryRows] = useState<Player[]>([]);
  const [draftRows, setDraftRows] = useState<Record<string, string> | null>(null);
  const [reason, setReason] = useState("");
  const [reference, setReference] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [review, setReview] = useState<{
    plan: z.infer<typeof planSchema>;
    body: object;
    revision: number;
  } | null>(null);
  const evidence = [
    ...new Map(
      [
        ...w.players,
        ...historyRows,
        ...Object.values(w.assignments),
        ...Object.values(w.entered?.assignments ?? {}),
      ].map((p) => [p.row_id, p]),
    ).values(),
  ];
  async function loadHistory(id: string) {
    if (!id) return;
    setBusy(true);
    setError("");
    try {
      const source = previewSchema.parse(await api(`/api/workspaces/${w.id}/imports/${id}`));
      setHistoryRows((previous) => [
        ...new Map([...previous, ...source.rows].map((p) => [p.row_id, p])).values(),
      ]);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function preview() {
    setBusy(true);
    setError("");
    try {
      const body = {
        expected_revision: w.revision,
        draft_id: w.draft_id,
        entered_id: w.entered?.id ?? null,
        assignments: rows,
        draft_assignments:
          draftRows === null
            ? null
            : Object.fromEntries(Object.entries(draftRows).filter(([, v]) => v)),
        attestation: historicalAttestation,
        reason,
        reference,
      };
      const plan = planSchema.parse(await api(`/api/workspaces/${w.id}/reconcile-preview`, body));
      setReview({ plan, body: { ...body, preview_hash: plan.preview_hash }, revision: w.revision });
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function dispute() {
    setBusy(true);
    setError("");
    try {
      await api(`/api/workspaces/${w.id}/entered-dispute`, {
        expected_revision: w.revision,
        reason,
        reference,
      });
      setReview(null);
      await reload();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function commit() {
    if (!review) return;
    setBusy(true);
    setError("");
    try {
      await api(`/api/workspaces/${w.id}/reconcile`, review.body);
      setReview(null);
      await reload();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="completion-section" id="reconciliation">
      <summary>Reconcile actual Yahoo lineup</summary>
      <p>
        Correct what already exists in Yahoo. This does not submit a lineup or permit a new locked
        selection. Verify exact slots and Yahoo salary evidence.
      </p>
      {w.late_swap.blockers.map((b) => (
        <p className="error" key={b}>
          {b}
        </p>
      ))}
      <p>
        Pending browser edits remain local when reconciliation changes the saved draft; review any
        revision conflict explicitly.
      </p>
      <button
        className="secondary"
        onClick={() => {
          setRows(
            Object.fromEntries(
              Object.entries(w.entered?.assignments ?? w.assignments).map(([s, p]) => [
                s,
                p.row_id,
              ]),
            ),
          );
          setReview(null);
        }}
      >
        Start from {w.entered ? "recorded entered" : "unconfirmed saved draft"} assignments
      </button>
      <label>
        Load older Yahoo evidence
        <select
          aria-label="Load older Yahoo evidence"
          defaultValue=""
          disabled={busy}
          onChange={(e) => void loadHistory(e.target.value)}
        >
          <option value="">Choose an immutable import</option>
          {w.imports.map((i) => (
            <option key={i.id} value={i.id}>
              {new Date(i.created_at).toLocaleString("en-US", { timeZone: "America/Chicago" })} ·{" "}
              {i.id.slice(0, 8)}
            </option>
          ))}
        </select>
      </label>
      {slots.map((s) => (
        <label key={s}>
          Actual Yahoo {s}
          <select
            aria-label={`Actual Yahoo ${s}`}
            value={rows[s] ?? ""}
            onChange={(e) => {
              setRows({ ...rows, [s]: e.target.value });
              setReview(null);
            }}
          >
            <option value="">Select evidenced player</option>
            {evidence
              .filter(
                (p) =>
                  !p.issues.length &&
                  (s === "FLEX"
                    ? ["RB", "WR", "TE"].includes(p.position)
                    : s.replace(/[123]/g, "") === p.position),
              )
              .map((p) => (
                <option key={p.row_id} value={p.row_id}>
                  {p.name} · ${p.salary_cents === null ? "unknown" : p.salary_cents / 100} · source{" "}
                  {p.row_id.slice(0, 8)}
                </option>
              ))}
          </select>
        </label>
      ))}
      <details>
        <summary>Resolve displaced editable draft work</summary>
        <p>
          Use this explicit resulting-draft plan if restoring fixed slots displaces editable
          selections. Every removal is shown in the preview.
        </p>
        <button
          className="secondary"
          onClick={() => {
            setDraftRows(
              Object.fromEntries(Object.entries(w.assignments).map(([s, p]) => [s, p.row_id])),
            );
            setReview(null);
          }}
        >
          Edit resulting draft plan
        </button>
        {draftRows
          ? slots.map((s) => (
              <label key={s}>
                Resulting draft {s}
                <select
                  aria-label={`Resulting draft ${s}`}
                  value={draftRows[s] ?? ""}
                  onChange={(e) => {
                    setDraftRows({ ...draftRows, [s]: e.target.value });
                    setReview(null);
                  }}
                >
                  <option value="">Empty</option>
                  {evidence
                    .filter(
                      (p) =>
                        !p.issues.length &&
                        (s === "FLEX"
                          ? ["RB", "WR", "TE"].includes(p.position)
                          : s.replace(/[123]/g, "") === p.position),
                    )
                    .map((p) => (
                      <option key={p.row_id} value={p.row_id}>
                        {p.name}
                      </option>
                    ))}
                </select>
              </label>
            ))
          : null}
      </details>
      <label>
        Historical correction reason
        <input
          aria-label="Historical correction reason"
          value={reason}
          onChange={(e) => {
            setReason(e.target.value);
            setReview(null);
          }}
        />
      </label>
      <label>
        Yahoo evidence reference
        <input
          aria-label="Yahoo evidence reference"
          value={reference}
          onChange={(e) => {
            setReference(e.target.value);
            setReview(null);
          }}
        />
      </label>
      <button
        disabled={disabled || busy || reason.length < 5 || reference.length < 5}
        onClick={() => void preview()}
      >
        Preview reconciliation
      </button>
      {w.entered ? (
        <button
          className="secondary"
          disabled={disabled || busy || reason.length < 5 || reference.length < 5}
          onClick={() => void dispute()}
        >
          Mark entered facts disputed
        </button>
      ) : null}
      {review ? (
        <div className="inset">
          <h3>Review exact historical correction</h3>
          {slots.map((s) => (
            <p key={s}>
              {s}: entered {review.plan.before_entered[s]?.name ?? "unrecorded"} →{" "}
              {review.plan.entered[s]?.name}; draft {review.plan.before_draft[s]?.name ?? "empty"} →{" "}
              {review.plan.draft[s]?.name ?? "empty"}
              <small>
                Yahoo salary{" "}
                {review.plan.before_entered[s]?.salary_cents == null
                  ? "unknown"
                  : `$${review.plan.before_entered[s].salary_cents / 100}`}{" "}
                → ${(review.plan.entered[s]?.salary_cents ?? 0) / 100} ·{" "}
                {review.plan.entered[s]?.game} · source {review.plan.entered[s]?.row_id.slice(0, 8)}
              </small>
            </p>
          ))}
          <p>Preferences remain as recorded. Server receipt time is recorded now.</p>
          {review.revision !== w.revision ? (
            <p className="error">Information changed. Selections retained; preview again.</p>
          ) : null}
          <button
            disabled={disabled || busy || review.revision !== w.revision}
            onClick={() => void commit()}
          >
            {historicalAttestation}
          </button>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className="error">
          {error}
        </p>
      ) : null}
    </details>
  );
}
