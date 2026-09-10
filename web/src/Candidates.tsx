import { z } from "zod";
import { api, environmentSchema, playerSchema, type Workspace } from "./api";
import { centralTime } from "./DecisionPanels";
const candidate = z.object({
  index: z.number(),
  constraint_name: z.string().nullable(),
  extra_exclusion: z.string().nullable(),
  result: z.object({
    primary_proven: z.boolean(),
    tie_complete: z.boolean(),
    salary_cents: z.number(),
    whole_total_units: z.number().nullable(),
    editable_units: z.number(),
    known_total_units: z.number(),
    missing_fixed: z.array(z.string()),
  }),
  preview: z.array(
    playerSchema.extend({
      slot: z.string(),
      previous_slot: z.string().nullable(),
      concerns: z.array(z.string()).default([]),
    }),
  ),
  removed: z.array(z.string()),
  delta_best_units: z.number(),
  delta_draft_units: z.number().nullable(),
  salary_delta_best_cents: z.number(),
  salary_delta_draft_cents: z.number().nullable(),
});
export const candidatesSchema = z.object({
  validation: z
    .object({ shared_budget_exhausted: z.boolean().optional() })
    .passthrough()
    .nullable(),
  request_id: z.string(),
  status: z.string(),
  stale: z.boolean(),
  bound_revision: z.number(),
  interpretation: z.object({ state: z.string(), limitations: z.string() }),
  candidates: z.array(candidate),
  options: z.object({
    action: z.string(),
    include: z.array(z.string()).optional(),
    exclude: z.array(z.string()).optional(),
  }),
  captured_context: z.object({
    environments: z.array(environmentSchema).optional(),
    locks: z.object({ started: z.array(z.string()) }).optional(),
  }),
  newer_context: z.boolean(),
  fixed_conflicts: z.array(z.string()).default([]),
});
export function Candidates({
  result: r,
  w,
  disabled,
  action,
  reload,
  readOnly = false,
}: {
  result: z.infer<typeof candidatesSchema>;
  w: Workspace;
  disabled: boolean;
  action: (fn: () => Promise<void>) => Promise<void>;
  reload: () => Promise<void>;
  readOnly?: boolean;
}) {
  const stale =
    r.stale ||
    r.bound_revision !== w.revision ||
    JSON.stringify(r.captured_context.locks?.started ?? []) !== JSON.stringify(w.late_swap.started);
  const names = (keys: string[] | undefined) =>
    keys
      ?.map(
        (k) =>
          r.candidates[0]?.preview.find((p) => p.yahoo_id === k)?.name ??
          Object.values(w.late_swap.fixed).find((p) => p.yahoo_id === k)?.name ??
          w.players.find((p) => p.yahoo_id === k)?.name ??
          k,
      )
      .join(", ") || "none";
  return (
    <div className="inset">
      {r.validation?.shared_budget_exhausted ? (
        <p>
          Shared search budget exhausted. Additional comparisons may be incomplete; only validated
          candidates are shown.
        </p>
      ) : null}
      <h3>
        {stale
          ? "Preview stale — information changed"
          : r.status === "pending"
            ? "Completing lineup…"
            : r.status === "ready"
              ? "Review exact completion"
              : `Completion: ${r.status}`}
      </h3>
      <p>{r.interpretation.state}. Comparisons use one projection snapshot.</p>
      {r.newer_context ? (
        <p>Newer game context exists. These explanations retain captured evidence.</p>
      ) : null}
      {r.options.action === "alternatives" ? (
        <p>
          Request only: include {names(r.options.include)}; exclude {names(r.options.exclude)}.
        </p>
      ) : null}
      {r.fixed_conflicts.length ? (
        <p className="notice">
          Fixed authority takes precedence over Avoid or exclusion for {names(r.fixed_conflicts)}.
          Preferences are retained.
        </p>
      ) : null}
      {r.candidates.map((c) => (
        <details className="candidate" key={c.index} open={r.candidates.length === 1}>
          <summary>
            {c.index === 0 ? "Leading candidate" : `Alternative ${c.index}`} ·{" "}
            {c.result.whole_total_units === null
              ? "Total incomplete"
              : `${c.result.whole_total_units / 10000} pregame pts`}{" "}
            · ${c.result.salary_cents / 100}
          </summary>
          <p>
            {c.result.primary_proven
              ? c.extra_exclusion
                ? "Optimal under added exclusion"
                : "Proven optimal"
              : "Best found; optimality unproven"}{" "}
            · {c.result.tie_complete ? "Tie ordering complete" : "Tie ordering incomplete"}
          </p>
          {c.constraint_name ? <p>Added constraint: exclude {c.constraint_name}.</p> : null}
          {c.preview.some((p) => p.concerns.includes("Availability unknown")) ? (
            <p className="muted">
              Availability designation unknown for{" "}
              {c.preview.filter((p) => p.concerns.includes("Availability unknown")).length} selected
              players.
            </p>
          ) : null}
          <p>
            Editable contribution: {c.result.editable_units / 10000} pts. Supported fixed pregame
            contribution: {(c.result.known_total_units - c.result.editable_units) / 10000} pts.{" "}
            {c.result.missing_fixed.length
              ? `Missing fixed projections: ${names(c.result.missing_fixed)}.`
              : ""}{" "}
            These are not live remaining points.
          </p>
          <p>
            Editable portion versus leading: {c.delta_best_units / 10000} pts · salary $
            {c.salary_delta_best_cents / 100}.
          </p>
          <p>
            {c.delta_draft_units === null
              ? "Draft incomplete or not comparable; no projected-point difference."
              : `Editable portion versus draft: ${c.delta_draft_units / 10000} pts · salary $${(c.salary_delta_draft_cents ?? 0) / 100}.`}
          </p>
          {c.removed.length ? <p>Removed: {c.removed.join(", ")}.</p> : null}
          {c.preview.map((p) => (
            <div className="lineup-slot" key={p.slot}>
              <span className="slot-key">{p.slot}</span>
              <div>
                <strong>{p.name}</strong>
                <small>
                  ${(p.salary_cents ?? 0) / 100} · {p.projection} pts ·{" "}
                  {p.previous_slot
                    ? p.previous_slot === p.slot
                      ? "Preserved"
                      : `Moved from ${p.previous_slot}`
                    : "Added"}
                </small>
                <small>{p.concerns.filter((c) => c !== "Availability unknown").join(" · ")}</small>
              </div>
            </div>
          ))}
          <details>
            <summary>Captured game context</summary>
            {r.captured_context.environments
              ?.filter((e) => e.current_setup)
              .map((e) => (
                <p key={e.id}>
                  {w.games.find((g) => g.id === e.game_id)?.away} at{" "}
                  {w.games.find((g) => g.id === e.game_id)?.home}: total {e.total}; implied away{" "}
                  {e.away_implied}, home {e.home_implied}. {e.source}, observed{" "}
                  {centralTime(e.observed_at)}. Reference: {e.reference}
                </p>
              ))}
          </details>
          {!readOnly ? (
            <button
              disabled={disabled || stale || w.locked || r.status !== "ready"}
              onClick={() =>
                void action(async () => {
                  await api(`/api/workspaces/${w.id}/completions/${r.request_id}/apply`, {
                    expected_revision: r.bound_revision,
                    candidate_index: c.index,
                  });
                  await reload();
                })
              }
            >
              {c.index === 0 ? "Apply exact preview" : `Apply alternative ${c.index}`}
            </button>
          ) : null}
        </details>
      ))}
      {r.status !== "pending" && r.status !== "ready" ? (
        <p>No draft changes. Resolve the issue and request completion explicitly.</p>
      ) : null}
    </div>
  );
}
