import { useEffect, useState } from "react";
import { centralTime } from "./DecisionPanels";
import { Candidates, candidatesSchema as resultSchema } from "./Candidates";
import { createPortal } from "react-dom";
import { z } from "zod";
import { api, playerSchema, type Workspace } from "./api";

const analyzedPlayer = playerSchema.extend({
  game_id: z.string(),
  projection: z.string().nullable(),
  units: z.number().nullable(),
  available: z.boolean(),
  concerns: z.array(z.string()),
});
const interpretation = z.object({ state: z.string(), limitations: z.string() });
const coverage = z.object({
  summary: z.record(z.string(), z.number()),
  by_position: z.record(z.string(), z.unknown()),
  by_game: z.record(z.string(), z.unknown()),
  players: z.array(analyzedPlayer),
  exceptions: z.array(
    z.object({
      source: z
        .object({
          source_key: z.string(),
          name: z.string(),
          team: z.string(),
          opponent: z.string().nullable(),
          position: z.string(),
        })
        .passthrough(),
      yahoo: z.unknown(),
      reason: z.string(),
    }),
  ),
});
export const stateSchema = z.object({
  sources: z.array(
    z.object({
      position: z.string(),
      imported_at: z.string(),
      provider_updated_at: z.string().nullable(),
      filename: z.string(),
    }),
  ),
  current: z.boolean(),
  issues: z.array(z.string()),
  analysis: z
    .object({
      report: coverage,
      interpretation,
      imported_at: z.string(),
      declaration: z.object({ source_context: z.string(), period: z.string() }),
    })
    .nullable(),
  preferences: z.array(
    z.object({ entry_id: z.string(), subject_id: z.string(), value: z.string(), name: z.string() }),
  ),
  batches: z.array(z.object({ id: z.string(), created_at: z.string() })),
  availability: z.array(z.record(z.string(), z.unknown())),
});
const reviewSchema = z.object({
  candidate_id: z.string(),
  expected_revision: z.number(),
  batch: z.object({
    id: z.string(),
    interpretation,
    validation: z.object({
      errors: z.array(z.string()),
      records: z.number(),
      separators: z.number(),
    }),
  }),
  coverage,
});
const positions = ["QB", "RB", "WR", "TE", "DST"];
const money = (v: number) => `$${v / 100}`;

export function AnalysisPanel({
  w,
  disabled,
  reload,
}: {
  w: Workspace;
  disabled: boolean;
  reload: () => Promise<void>;
}) {
  const [state, setState] = useState<z.infer<typeof stateSchema> | null>(null);
  const [review, setReview] = useState<z.infer<typeof reviewSchema> | null>(null);
  const [result, setResult] = useState<z.infer<typeof resultSchema> | null>(null);
  const [request, setRequest] = useState("");
  const [files, setFiles] = useState<Record<string, File>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [choice, setChoice] = useState("");
  const [remove, setRemove] = useState(false);
  const [batch, setBatch] = useState("");
  const [include, setInclude] = useState("");
  const [exclude, setExclude] = useState("");
  const base = `/api/workspaces/${w.id}`;
  useEffect(() => {
    let live = true;
    void api(`${base}/analysis`)
      .then((v) => {
        if (live) setState(stateSchema.parse(v));
      })
      .catch((e) => {
        if (live) setError(String(e));
      });
    return () => {
      live = false;
    };
  }, [base, w.revision]);
  useEffect(() => {
    if (!request) return;
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const r = resultSchema.parse(await api(`${base}/completions/${request}`));
        if (!live) return;
        setResult(r);
        if (r.status === "pending") timer = setTimeout(() => void poll(), 600);
      } catch (e) {
        if (live) setError(String(e));
      }
    }
    void poll();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [base, request, w.revision]);
  async function action(fn: () => Promise<void>) {
    setError("");
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  async function reviewBatch(id: string) {
    setBatch(id);
    setReview(reviewSchema.parse(await api(`${base}/projections/${id}/review`, {})));
  }
  async function preference(value: string, entry = choice, subject?: string) {
    const p = w.players.find((p) => p.entry_id === entry);
    if (!p && !subject) return;
    await api(`${base}/preferences`, {
      expected_revision: w.revision,
      entry_id: entry,
      subject_id: subject ?? p?.subject_id,
      value,
      remove_selected: remove,
    });
    setRemove(false);
    await reload();
  }
  const selected = w.players.find((p) => p.entry_id === choice);
  const report = review?.coverage ?? state?.analysis?.report;
  const evaluatedDraft = Object.values(w.assignments).map((p) =>
    state?.analysis?.report.players.find(
      (c) => c.entry_id === p.entry_id && c.subject_id === p.subject_id && !c.issues.length,
    ),
  );
  const projectedTotal =
    state?.current && evaluatedDraft.every((p) => p?.units != null)
      ? evaluatedDraft.reduce((sum, p) => sum + (p?.units ?? 0), 0) / 10000
      : null;
  const fixedEntries = new Set(Object.values(w.late_swap.fixed).map((p) => p.entry_id));
  const editableDraft = evaluatedDraft.filter(
    (_, i) => !fixedEntries.has(Object.values(w.assignments)[i].entry_id),
  );
  const editablePoints =
    state?.current && editableDraft.every((p) => p?.units != null)
      ? editableDraft.reduce((sum, p) => sum + (p?.units ?? 0), 0) / 10000
      : null;
  const fixedForecasts = Object.values(w.late_swap.fixed).map((p) =>
    state?.analysis?.report.players.find(
      (c) => c.entry_id === p.entry_id && c.subject_id === p.subject_id && !c.issues.length,
    ),
  );
  const knownFixedPoints =
    fixedForecasts.filter((p) => p?.units != null).reduce((sum, p) => sum + (p?.units ?? 0), 0) /
    10000;
  const blocked = disabled || busy;
  const target = document.getElementById("completion-preview");
  const completion = (
    <section className="completion-section">
      <h3>Recommendations</h3>
      {state?.current ? (
        <p>
          Disclosed editable pool:{" "}
          {state.analysis?.report.players.filter(
            (p) =>
              p.available &&
              p.projection !== null &&
              !p.issues.length &&
              !w.late_swap.started.includes(p.game_id),
          ).length ?? 0}{" "}
          projected entries before preferences and request constraints. Started games are excluded
          from new selections; entered fixed members remain in every result.
        </p>
      ) : null}
      <p>
        Saved draft projection:{" "}
        {projectedTotal === null
          ? "Incomplete"
          : `${projectedTotal} pts across ${evaluatedDraft.length} selected players`}
      </p>
      {w.late_swap.started.length ? (
        <p>
          Editable pregame contribution:{" "}
          {editablePoints === null ? "incomplete" : `${editablePoints} pts`}. Supported fixed
          pregame contribution: {knownFixedPoints} pts;{" "}
          {fixedForecasts.filter((p) => p?.units == null).length} fixed projections missing. These
          are not live remaining points.
        </p>
      ) : null}
      <p className="muted">
        Preserves selected players and includes Keep choices. Works within the covered eligible
        pool.
      </p>
      {state?.issues.map((i) => (
        <p className="error" key={i}>
          {i}
        </p>
      ))}
      <button
        disabled={blocked || !state?.current || w.locked || result?.status === "pending"}
        onClick={() =>
          void action(async () => {
            const r = z
              .object({ request_id: z.string() })
              .parse(await api(`${base}/complete`, { expected_revision: w.revision }));
            setRequest(r.request_id);
            setResult(null);
          })
        }
      >
        Complete lineup
      </button>
      <details>
        <summary>Temporary request controls</summary>
        <label>
          Include for this request
          <select
            aria-label="Temporary include"
            value={include}
            onChange={(e) => setInclude(e.target.value)}
          >
            <option value="">None</option>
            {w.players
              .filter((p) => !p.issues.length)
              .map((p) => (
                <option key={p.row_id} value={p.yahoo_id}>
                  {p.name}
                </option>
              ))}
          </select>
        </label>
        <label>
          Exclude for this request
          <select
            aria-label="Temporary exclude"
            value={exclude}
            onChange={(e) => setExclude(e.target.value)}
          >
            <option value="">None</option>
            {w.players
              .filter((p) => !p.issues.length)
              .map((p) => (
                <option key={p.row_id} value={p.yahoo_id}>
                  {p.name}
                </option>
              ))}
          </select>
        </label>
      </details>
      <button
        className="secondary"
        disabled={blocked || !state?.current || w.locked || result?.status === "pending"}
        onClick={() =>
          void action(async () => {
            const r = z.object({ request_id: z.string() }).parse(
              await api(`${base}/alternatives`, {
                expected_revision: w.revision,
                include: include ? [include] : [],
                exclude: exclude ? [exclude] : [],
              }),
            );
            setRequest(r.request_id);
            setResult(null);
          })
        }
      >
        Find alternatives
      </button>
      <small>
        May replace selections; preserves Keep and respects Avoid. Up to three distinct lineups in
        one shared budget. Extra candidates explicitly exclude a leading replaceable player.
      </small>
      {result ? (
        <Candidates result={result} w={w} disabled={blocked} action={action} reload={reload} />
      ) : null}
    </section>
  );
  return (
    <section className="card">
      <p className="eyebrow">ACCEPTED PROJECTIONS</p>
      <h2>Projection review</h2>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <p>
        {state?.current
          ? state.analysis?.interpretation.state
          : "Activate a reviewed projection batch to enable completion"}
      </p>
      <p className="muted">
        {state?.analysis?.declaration.source_context} · {state?.analysis?.declaration.period}
      </p>
      <p className="muted">
        Publication:{" "}
        {state?.sources.every((s) => s.provider_updated_at === null)
          ? "unknown"
          : state?.sources
              .map((s) => `${s.position}: ${centralTime(s.provider_updated_at)}`)
              .join("; ")}
        . Acquisition does not establish forecast freshness.
      </p>
      {state?.analysis && (
        <p className="muted">Imported {centralTime(state.analysis.imported_at)}</p>
      )}
      {state?.analysis ? (
        <p>
          {state.analysis.report.summary.eligible} eligible projected entries ·{" "}
          {state.analysis.report.summary.matched} matched.{" "}
          {state.analysis.interpretation.limitations}
        </p>
      ) : null}
      {state?.current && state.analysis ? (
        <p className="inset">
          Highest available projection:{" "}
          {[...state.analysis.report.players]
            .filter((p) => p.available && p.units !== null && !p.issues.length)
            .sort((a, b) => (b.units ?? 0) - (a.units ?? 0) || a.yahoo_id.localeCompare(b.yahoo_id))
            .slice(0, 1)
            .map(
              (p) =>
                `${p.name}, ${p.projection} pts at ${money(p.salary_cents ?? 0)} (${p.position}).`,
            )}{" "}
          Keep remains your preference.
        </p>
      ) : null}
      <details>
        <summary>Upload five FantasyPros files</summary>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const values = new FormData(e.currentTarget);
            void action(async () => {
              const form = new FormData();
              positions.forEach((p) => {
                if (files[p]) form.append("files", files[p]);
              });
              form.append("positions", JSON.stringify(positions.filter((p) => files[p])));
              form.append(
                "declaration",
                JSON.stringify({
                  season: String(values.get("season")),
                  period: String(values.get("period")),
                  scoring: "half-ppr-baseline",
                  material_settings_match: values.get("settings") === "on",
                  evidence: String(values.get("evidence")),
                  source_context: String(values.get("context")),
                }),
              );
              const r = z
                .object({ batch_id: z.string() })
                .parse(await api(`${base}/projections`, form));
              await reviewBatch(r.batch_id);
            });
          }}
        >
          {positions.map((p) => (
            <label key={p}>
              {p} projection CSV
              <input
                aria-label={`${p} projection CSV`}
                type="file"
                accept=".csv"
                required
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) setFiles((f) => ({ ...f, [p]: file }));
                }}
              />
            </label>
          ))}
          <label>
            Projection season
            <input name="season" defaultValue={w.season} required />
          </label>
          <label>
            Forecast period
            <input name="period" defaultValue={w.round} required />
          </label>
          <label>
            Source context
            <input
              name="context"
              required
              minLength={5}
              placeholder="Export page, intended week, acquisition context"
            />
          </label>
          <label>
            Scoring evidence
            <input
              name="evidence"
              required
              minLength={5}
              placeholder="Half PPR and main scoring settings evidence"
            />
          </label>
          <label>
            <input name="settings" type="checkbox" required /> Half PPR and main yardage, TD,
            turnover, conversion and DEF settings match the documented baseline.
          </label>
          <p className="muted">
            Rare component omissions remain an accepted approximation. File names do not prove the
            week; compare opponents and source context.
          </p>
          <button disabled={blocked}>Stage projection batch</button>
        </form>
      </details>
      {!!state?.batches.length && (
        <details>
          <summary>Previous projection batches</summary>
          {state.batches.map((b) => (
            <button
              className="subtle block"
              key={b.id}
              onClick={() => void action(() => reviewBatch(b.id))}
            >
              {new Date(b.created_at).toLocaleString()}
            </button>
          ))}
        </details>
      )}
      {review && (
        <div className="inset">
          <h3>Review staged projections</h3>
          <p>
            {review.batch.interpretation.state} · {review.batch.validation.records} source records ·{" "}
            {review.batch.validation.separators} separators
          </p>
          {review.batch.validation.errors.map((e) => (
            <p className="error" key={e}>
              {e}
            </p>
          ))}
          <p className="muted">{review.batch.interpretation.limitations}</p>
          <button
            disabled={blocked || !!review.batch.validation.errors.length}
            onClick={() =>
              void action(async () => {
                await api(`${base}/analysis/activate`, {
                  candidate_id: review.candidate_id,
                  expected_revision: review.expected_revision,
                });
                setReview(null);
                await reload();
              })
            }
          >
            Activate reviewed projections
          </button>
        </div>
      )}
      {report && (
        <>
          <p>
            {report.summary.matched} matched · {report.summary.eligible} eligible numeric ·{" "}
            {report.summary.zeros} explicit zeros · {report.summary.unmatched_or_conflicting} source
            exceptions
          </p>
          <details>
            <summary>Accepted player projections</summary>
            {report.players
              .filter((p) => !p.issues.length)
              .map((p) => (
                <p key={p.entry_id}>
                  {p.name} � {p.position} � {p.team} vs {p.opponent} � {money(p.salary_cents ?? 0)}{" "}
                  � {p.projection ?? "Missing"} pts � {p.concerns.join(" / ")}
                </p>
              ))}
          </details>
          <details>
            <summary>Coverage by position and game</summary>
            <pre>
              {JSON.stringify({ positions: report.by_position, games: report.by_game }, null, 2)}
            </pre>
          </details>
          <details>
            <summary>Mapping exceptions ({report.exceptions.length})</summary>
            {report.exceptions.map((ex) => (
              <details key={ex.source.source_key}>
                <summary>
                  {ex.source.name} · {ex.source.team} · {ex.reason}
                </summary>
                <pre>{JSON.stringify(ex, null, 2)}</pre>
                {review && (
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      const f = new FormData(e.currentTarget);
                      const p = w.players.find((p) => p.entry_id === f.get("entry"));
                      if (p)
                        void action(async () => {
                          await api(`${base}/mappings`, {
                            expected_revision: w.revision,
                            batch_id: batch,
                            source_key: ex.source.source_key,
                            entry_id: p.entry_id,
                            subject_id: p.subject_id,
                            reason: f.get("reason"),
                          });
                          setReview(null);
                          await reload();
                        });
                    }}
                  >
                    <label>
                      Reviewed Yahoo association
                      <select name="entry" required>
                        <option value="">Choose subject</option>
                        {w.players
                          .filter(
                            (p) =>
                              !p.issues.length &&
                              p.team === ex.source.team &&
                              p.position === ex.source.position &&
                              p.opponent === ex.source.opponent,
                          )
                          .map((p) => (
                            <option key={p.entry_id} value={p.entry_id}>
                              {p.name} · {p.team} vs {p.opponent}
                            </option>
                          ))}
                      </select>
                    </label>
                    <label>
                      Association evidence
                      <input name="reason" minLength={5} required />
                    </label>
                    <button disabled={blocked}>Record mapping evidence</button>
                    <p>Review the batch again after recording evidence.</p>
                  </form>
                )}
              </details>
            ))}
          </details>
        </>
      )}
      <details>
        <summary>Keep / Avoid and availability</summary>
        <label>
          Preference subject
          <select
            aria-label="Preference subject"
            value={choice}
            onChange={(e) => {
              setChoice(e.target.value);
              setRemove(false);
            }}
          >
            <option value="">Choose player</option>
            {w.players
              .filter((p) => !p.issues.length)
              .map((p) => (
                <option key={p.entry_id} value={p.entry_id}>
                  {p.name} · {p.position} · {p.team}
                </option>
              ))}
          </select>
        </label>
        {selected && (
          <>
            <button disabled={blocked} onClick={() => void action(() => preference("keep"))}>
              Keep player
            </button>{" "}
            <button disabled={blocked} onClick={() => void action(() => preference("avoid"))}>
              {remove ? "Remove and Avoid player" : "Avoid player"}
            </button>{" "}
            <button
              className="subtle"
              disabled={blocked}
              onClick={() => void action(() => preference("clear"))}
            >
              Clear preference
            </button>
            {Object.values(w.assignments).some((p) => p.entry_id === choice) && (
              <label>
                <input
                  type="checkbox"
                  checked={remove}
                  onChange={(e) => setRemove(e.target.checked)}
                />{" "}
                Explicitly remove selected player when choosing Avoid (leave unchecked to cancel
                removal)
              </label>
            )}
          </>
        )}
        {state?.preferences.map((p) => (
          <p key={p.entry_id}>
            {p.name}: {p.value}{" "}
            <button
              className="subtle"
              disabled={blocked}
              onClick={() => void action(() => preference("clear", p.entry_id, p.subject_id))}
            >
              Clear {p.name} preference
            </button>
          </p>
        ))}
        {selected && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              const analyzed = report?.players.find((p) => p.entry_id === choice);
              if (!analyzed) return;
              void action(async () => {
                await api(`${base}/availability`, {
                  expected_revision: w.revision,
                  subject_id: selected.subject_id,
                  game_id: analyzed.game_id,
                  evidence_type: f.get("type"),
                  designation: f.get("designation"),
                  source: f.get("source"),
                  source_time: f.get("time") ? new Date(String(f.get("time"))).toISOString() : null,
                  reason: f.get("reason"),
                  resolves: String(f.get("resolves") ?? "")
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean),
                });
                await reload();
              });
            }}
          >
            <h3>Record game-specific availability</h3>
            <p>
              {selected.name} · {selected.game} · {w.round}
            </p>
            <label>
              Evidence type
              <select name="type">
                <option value="designation">Designation</option>
                <option value="participation">Participation</option>
                <option value="practice">Practice</option>
                <option value="resolution">Resolution</option>
              </select>
            </label>
            <label>
              Designation
              <select name="designation">
                {[
                  "Out",
                  "Inactive",
                  "IR",
                  "PUP",
                  "NFI",
                  "Suspended",
                  "Reported absence",
                  "Q",
                  "D",
                  "DTD",
                  "Limited",
                  "Active",
                  "Unknown",
                ].map((d) => (
                  <option key={d}>{d}</option>
                ))}
              </select>
            </label>
            <label>
              Availability source
              <input name="source" minLength={5} required />
            </label>
            <label>
              Underlying source time (optional)
              <input type="datetime-local" name="time" />
            </label>
            <label>
              Reason / evidence
              <input name="reason" minLength={5} required />
            </label>
            <label>
              Resolved evidence references (comma separated)
              <input name="resolves" />
            </label>
            <button disabled={blocked || !report}>Record availability evidence</button>
            <p className="muted">
              New evidence requires reviewing and activating projections again. Q/D/DTD and practice
              concerns do not change points.
            </p>
          </form>
        )}
        <details>
          <summary>Availability evidence references</summary>
          <pre>{JSON.stringify(state?.availability, null, 2)}</pre>
        </details>
      </details>
      {target ? createPortal(completion, target) : null}
    </section>
  );
}
