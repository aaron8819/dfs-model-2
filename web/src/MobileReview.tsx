import { useEffect, useState } from "react";
import { z } from "zod";
import { api, type Workspace } from "./api";
import { stateSchema } from "./AnalysisPanel";
import { Candidates, candidatesSchema } from "./Candidates";
import { centralTime } from "./DecisionPanels";

const slots = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DEF"];
export function MobileReview({
  w,
  list,
  open,
  pending,
  signOut,
}: {
  w: Workspace | null;
  list: { id: string; name: string }[];
  open: (id: string) => Promise<void>;
  pending: boolean;
  signOut: () => Promise<void>;
}) {
  const [section, setSection] = useState("Briefing");
  const [query, setQuery] = useState("");
  const [state, setState] = useState<z.infer<typeof stateSchema> | null>(null);
  const [result, setResult] = useState<z.infer<typeof candidatesSchema> | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    setState(null);
    setResult(null);
    setError("");
    if (w)
      void Promise.all([
        api(`/api/workspaces/${w.id}/analysis`).then((v) => {
          if (live) setState(stateSchema.parse(v));
        }),
        api(`/api/workspaces/${w.id}/completions`).then(async (v) => {
          const requests = z.array(z.object({ id: z.string() })).parse(v);
          if (requests[0]) {
            const value = candidatesSchema.parse(
              await api(`/api/workspaces/${w.id}/completions/${requests[0].id}`),
            );
            if (live) setResult(value);
          }
        }),
      ]).catch((e) => {
        if (live) setError(String(e));
      });
    return () => {
      live = false;
    };
  }, [w?.id, w?.revision]);
  const act = (fn: () => Promise<void>) => fn().catch((e) => setError(String(e)));
  return (
    <main className="mobile-review">
      <header>
        <p className="eyebrow">DFS / REVIEW ONLY</p>
        <button className="subtle" disabled={pending} onClick={() => void act(signOut)}>
          Sign out
        </button>
      </header>
      <h1>{w?.name ?? "Your workspace"}</h1>
      <p className="muted">Release verification in progress · Not ready for weekly use</p>
      {pending ? (
        <p role="status">
          Desktop edits remain unsaved in this tab. This view shows saved server facts.
        </p>
      ) : null}
      <label>
        Workspace
        <select value={w?.id ?? ""} onChange={(e) => void act(() => open(e.target.value))}>
          {list.map((x) => (
            <option key={x.id} value={x.id}>
              {x.name}
            </option>
          ))}
        </select>
      </label>
      {w ? (
        <button className="secondary" onClick={() => void act(() => open(w.id))}>
          Refresh review
        </button>
      ) : (
        <p>Create a workspace on desktop to begin.</p>
      )}
      {error ? (
        <p role="alert" className="error">
          {error}
        </p>
      ) : null}
      <nav aria-label="Review sections">
        {["Briefing", "Players", "Lineup", "Previews"].map((s) => (
          <button
            key={s}
            aria-current={section === s ? "page" : undefined}
            onClick={() => setSection(s)}
          >
            {s}
          </button>
        ))}
      </nav>
      {w ? (
        <>
          <p role="status">
            <strong>{w.late_swap.mode}</strong> · Yahoo record: {w.entered_status}
          </p>
          {[...w.late_swap.blockers, ...w.issues, ...(state?.issues ?? [])].map((s, i) => (
            <p className="error" key={i}>
              {s}
            </p>
          ))}
          {section === "Briefing" ? (
            <section aria-label="Slate briefing">
              <h2>Slate briefing</h2>
              <p>
                {w.season} · {w.round} · {w.games.length} games
              </p>
              <p>
                {state?.current
                  ? "Accepted analysis is current for saved inputs."
                  : "Accepted analysis missing or stale."}{" "}
                Publication time must be checked separately.
              </p>
              <p>
                {state?.analysis?.interpretation.state}{" "}
                {state?.analysis?.interpretation.limitations}
              </p>
              {state?.sources.map((s) => (
                <p key={s.position}>
                  <strong>{s.position}</strong> · Published {centralTime(s.provider_updated_at)}
                  <small>Imported {centralTime(s.imported_at)}</small>
                </p>
              ))}
              {w.games.map((g) => {
                const e = w.environments.find((e) => e.game_id === g.id && e.current_setup);
                return (
                  <article className="card" key={g.id}>
                    <h3>
                      {g.away} at {g.home}
                    </h3>
                    <p>
                      {centralTime(g.kickoff)} ·{" "}
                      {w.late_swap.started.includes(g.id) ? "Fixed game" : "Upcoming"}
                    </p>
                    {e ? (
                      <>
                        <p>
                          Total {e.total} · Home spread {e.home_spread}
                        </p>
                        <p>
                          Implied {g.away} {e.away_implied} / {g.home} {e.home_implied}
                        </p>
                        <small>
                          {e.source} · Observed {centralTime(e.observed_at)} · Published{" "}
                          {centralTime(e.published_at)}
                        </small>
                        <p>{e.reference}</p>
                      </>
                    ) : (
                      <p>Game environment evidence missing.</p>
                    )}
                  </article>
                );
              })}
            </section>
          ) : null}
          {section === "Players" ? (
            <section>
              <h2>Player research</h2>
              <label>
                Search players
                <input value={query} onChange={(e) => setQuery(e.target.value)} />
              </label>
              {(state?.analysis?.report.players ?? w.players)
                .filter((p) =>
                  `${p.name} ${p.team} ${p.position}`.toLowerCase().includes(query.toLowerCase()),
                )
                .map((p) => (
                  <article className="card" key={p.row_id}>
                    <h3>{p.name}</h3>
                    <p>
                      {p.position} · {p.team} / {p.opponent} ·{" "}
                      {p.salary_cents == null ? "Salary unknown" : `$${p.salary_cents / 100}`} ·{" "}
                      {p.projection ?? "Unknown"} pts
                    </p>
                    <p>
                      {p.injury ?? "Availability unknown"} · {p.issues.join(" · ")}
                    </p>
                    <details>
                      <summary>Player evidence</summary>
                      <p>
                        {"concerns" in p
                          ? z.array(z.string()).parse(p.concerns).join(" · ")
                          : "No accepted analysis evidence"}
                      </p>
                      <p>
                        Yahoo row {p.yahoo_id} · Game {p.game}
                      </p>
                      {state?.availability
                        .filter((a) => a.entry_id === p.entry_id || a.subject_id === p.subject_id)
                        .map((a, i) => (
                          <pre key={i}>{JSON.stringify(a, null, 2)}</pre>
                        ))}
                    </details>
                  </article>
                ))}
            </section>
          ) : null}
          {section === "Lineup" ? (
            <section>
              <h2>Saved working lineup</h2>
              <p>
                Entered record {w.entered ? centralTime(w.entered.created_at) : "missing"}. This
                records the owner's confirmation, not a verified Yahoo submission.
              </p>
              {slots.map((s) => {
                const p = w.assignments[s];
                const entered = w.entered?.assignments[s];
                const facts = w.late_swap.fixed[s] ?? p?.current;
                const differs =
                  p?.entry_id !== entered?.entry_id || p?.subject_id !== entered?.subject_id;
                return (
                  <article className="card" key={s}>
                    <h3>
                      {s} · {w.late_swap.fixed[s] ? "Fixed" : "Editable on desktop"}
                    </h3>
                    <p>
                      <strong>{p?.name ?? "Empty"}</strong> ·{" "}
                      {facts?.salary_cents == null
                        ? "Salary unknown"
                        : `$${facts.salary_cents / 100}`}{" "}
                      · {facts?.projection ?? "Unknown"} pts
                    </p>
                    <p>Yahoo record: {entered?.name ?? "Empty"}</p>
                    {differs ? (
                      <p className="error">
                        Difference: {entered?.name ?? "empty"} → {p?.name ?? "empty"}
                      </p>
                    ) : (
                      <small>Assignments match</small>
                    )}
                    <p>{p?.concerns.join(" · ")}</p>
                  </article>
                );
              })}
            </section>
          ) : null}
          {section === "Previews" ? (
            <section>
              <h2>Latest saved recommendation</h2>
              {result ? (
                <Candidates
                  result={result}
                  w={w}
                  disabled
                  readOnly
                  action={async () => {}}
                  reload={async () => {}}
                />
              ) : (
                <p>No saved preview available. Generate recommendations on desktop.</p>
              )}
            </section>
          ) : null}
        </>
      ) : null}
    </main>
  );
}
