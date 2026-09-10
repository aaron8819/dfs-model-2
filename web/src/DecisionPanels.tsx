import { useState } from "react";
import { api, type Workspace, type Player } from "./api";

export const centralTime = (value: string | null) =>
  value
    ? new Date(value).toLocaleString("en-US", {
        timeZone: "America/Chicago",
        dateStyle: "medium",
        timeStyle: "short",
      }) + " CT"
    : "unknown";

export function Environments({
  w,
  disabled,
  reload,
}: {
  w: Workspace;
  disabled: boolean;
  reload: () => Promise<void>;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<unknown>(null);
  const [game, setGame] = useState(w.games[0]?.id ?? "");
  const old = w.environments.find((e) => e.game_id === game);
  return (
    <section className="card">
      <p className="eyebrow">SLATE BRIEFING</p>
      <h2>Game environments</h2>
      <p className="muted">
        Full-game lines · Home spread: negative means home favored. Context does not change
        projections.
      </p>
      <div className="environment-grid">
        {[...w.games]
          .sort(
            (a, b) =>
              Number(w.environments.find((e) => e.game_id === b.id)?.total ?? -1) -
              Number(w.environments.find((e) => e.game_id === a.id)?.total ?? -1),
          )
          .map((g) => {
            const e = w.environments.find((e) => e.game_id === g.id && e.current_setup);
            return (
              <div className="inset" key={g.id}>
                <h3>
                  {g.away} at {g.home}
                </h3>
                <small>{centralTime(g.kickoff)}</small>
                {e ? (
                  <>
                    <p>
                      <strong>Total {e.total}</strong> · {g.home} spread{" "}
                      {Number(e.home_spread) > 0 ? "+" : ""}
                      {e.home_spread}
                    </p>
                    <p>
                      Implied: {g.away} {e.away_implied} · {g.home} {e.home_implied}
                    </p>
                    <small>
                      {e.source} · Observed {centralTime(e.observed_at)}
                    </small>
                    <small>
                      Observation age{" "}
                      {Math.max(0, Math.floor((Date.now() - Date.parse(e.observed_at)) / 60000))}{" "}
                      min · Published {centralTime(e.published_at)}
                    </small>
                    {e.total_change !== null ? (
                      <small>
                        Comparable prior: total Δ {e.total_change}; home spread Δ {e.spread_change}
                      </small>
                    ) : (
                      <small>No comparable prior change</small>
                    )}
                    <details>
                      <summary>Observation evidence</summary>
                      <p>{e.reference}</p>
                      <small>Acquired {centralTime(e.created_at)}</small>
                      <small>
                        Home implied = (total − home spread) / 2; away = (total + home spread) / 2.
                      </small>
                    </details>
                  </>
                ) : (
                  <p>Odds missing · Projection completion remains available.</p>
                )}
              </div>
            );
          })}
      </div>
      <details>
        <summary>Add or revise game evidence</summary>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const form = new FormData(e.currentTarget);
            setBusy(true);
            setError("");
            void api(`/api/workspaces/${w.id}/odds`, {
              expected_revision: w.revision,
              expected_context_revision: w.context_revision,
              game_id: game,
              source: form.get("source"),
              reference: form.get("reference"),
              observed_at: form.get("observed"),
              published_at: form.get("published") || null,
              total: form.get("total"),
              home_spread: form.get("spread"),
              supersedes: old?.id ?? null,
              reason: form.get("reason"),
            })
              .then(reload)
              .catch((e) => setError(String(e)))
              .finally(() => setBusy(false));
          }}
        >
          <label>
            Exact slate game
            <select aria-label="Odds game" value={game} onChange={(e) => setGame(e.target.value)}>
              {w.games.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.away} at {g.home}
                </option>
              ))}
            </select>
          </label>
          <label>
            Source / bookmaker
            <input name="source" required />
          </label>
          <label>
            Source reference
            <input name="reference" required placeholder="Page, export, or recorded source" />
          </label>
          <label>
            Observed timestamp with timezone
            <input name="observed" required placeholder="2026-09-10T12:00:00-05:00" />
          </label>
          <label>
            Publication timestamp, if known
            <input name="published" placeholder="Unknown if blank" />
          </label>
          <div className="environment-grid">
            <label>
              Game total
              <input name="total" required />
            </label>
            <label>
              Home team spread (− = favored)
              <input name="spread" required placeholder="-3.5" />
            </label>
          </div>
          <label>
            Reason / observation context
            <input name="reason" required minLength={5} />
          </label>
          {old ? (
            <label className="check">
              <input key={old.id} type="checkbox" required />
              Explicitly replace displayed {old.source} observation; retain its history.
            </label>
          ) : null}
          <button disabled={disabled || busy}>Save game evidence</button>
          {error ? (
            <p className="error" role="alert">
              {error}
            </p>
          ) : null}
        </form>
      </details>
      <details
        onToggle={(e) => {
          if (e.currentTarget.open)
            void api(`/api/workspaces/${w.id}/decision-history`)
              .then(setHistory)
              .catch((e) => setError(String(e)));
        }}
      >
        <summary>Retained decision evidence (latest 100 revisions)</summary>
        <pre>{history ? JSON.stringify(history, null, 2) : "Loading evidence…"}</pre>
      </details>
    </section>
  );
}

export function DraftHistory({
  w,
  assignments,
  disabled,
  reload,
}: {
  w: Workspace;
  assignments: Record<string, Player>;
  disabled: boolean;
  reload: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const same =
    w.entered &&
    Object.keys(assignments).length === 9 &&
    Object.entries(assignments).every(
      ([s, p]) =>
        w.entered?.assignments[s]?.entry_id === p.entry_id &&
        w.entered.assignments[s]?.subject_id === p.subject_id,
    );
  function currentSalary(p: Player): string {
    const current =
      Object.values(w.late_swap.fixed).find(
        (f) => f.entry_id === p.entry_id && f.subject_id === p.subject_id,
      ) ??
      w.players.find(
        (c) => c.entry_id === p.entry_id && c.subject_id === p.subject_id && !c.issues.length,
      );
    return current?.salary_cents == null ? "salary unknown" : `$${current.salary_cents / 100}`;
  }
  async function act(path: string, body: unknown) {
    setBusy(true);
    setError("");
    try {
      await api(`/api/workspaces/${w.id}/${path}`, body);
      await reload();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="completion-section">
      <button
        className="secondary"
        disabled={disabled || busy || w.locked || !w.undo_available}
        onClick={() => void act("undo", { expected_revision: w.revision })}
      >
        Undo latest lineup action
      </button>
      <small>
        Restores prior slots under current Yahoo facts. Preferences stay; clear conflicting Avoid
        first. One level, no redo.
      </small>
      <h3 className="mt-4">Entered in Yahoo</h3>
      <p data-testid="entered-status">
        {!w.entered
          ? "No recorded entered lineup"
          : same
            ? "Draft matches recorded lineup"
            : "Draft differs from recorded lineup"}
      </p>
      {w.entered ? (
        <details>
          <summary>Recorded {centralTime(w.entered.created_at)}</summary>
          {Object.entries(w.entered.assignments).map(([s, p]) => (
            <p key={s}>
              {s} · {p.name} · ${(p.salary_cents ?? 0) / 100}
            </p>
          ))}
        </details>
      ) : null}
      {w.entered && !same ? (
        <div>
          {Object.keys({ ...assignments, ...w.entered.assignments })
            .filter(
              (s) =>
                assignments[s]?.entry_id !== w.entered?.assignments[s]?.entry_id ||
                assignments[s]?.subject_id !== w.entered?.assignments[s]?.subject_id,
            )
            .map((s) => (
              <p key={s}>
                {s}: Yahoo record {w.entered?.assignments[s]?.name ?? "empty"} → draft{" "}
                {assignments[s]?.name ?? "empty"}
              </p>
            ))}
          <p>Manual Yahoo submission and explicit updated recording are outstanding.</p>
        </div>
      ) : null}
      <details>
        <summary>Review draft for entered recording</summary>
        <p>User attestation. Manually submit in Yahoo first; this app cannot verify submission.</p>
        {Object.entries(assignments).map(([s, p]) => (
          <p key={s}>
            {s} · {p.name} · {currentSalary(p)}
          </p>
        ))}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const form = new FormData(e.currentTarget);
            void act("entered", {
              expected_revision: w.revision,
              draft_id: w.draft_id,
              attestation: "Record as entered in Yahoo",
              reason: form.get("reason"),
            });
          }}
        >
          <label>
            Recording / replacement reason
            <input name="reason" required minLength={5} />
          </label>
          <button disabled={disabled || busy || w.locked || Object.keys(assignments).length !== 9}>
            Record as entered in Yahoo
          </button>
        </form>
      </details>
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}
