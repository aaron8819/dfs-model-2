import { Reconciliation } from "./Reconciliation";
import { MobileReview } from "./MobileReview";
import { useEffect, useState } from "react";
import { z } from "zod";
import {
  api,
  ApiError,
  previewSchema,
  setCsrf,
  workspaceSchema,
  type Preview,
  type Setup,
  type Player,
} from "./api";
import { useDraft, draftPlayers } from "./store";
import { SetupForm } from "./SetupForm";
import { AnalysisPanel } from "./AnalysisPanel";
import { Environments, DraftHistory, centralTime } from "./DecisionPanels";
import { ImportPanel } from "./ImportPanel";
const slots = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DEF"];
const money = (cents: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
export function App() {
  const [mobile, setMobile] = useState(() => matchMedia("(max-width: 800px)").matches);
  useEffect(() => {
    const media = matchMedia("(max-width: 800px)");
    const changed = () => setMobile(media.matches);
    media.addEventListener("change", changed);
    return () => media.removeEventListener("change", changed);
  }, []);
  const { workspace: w, pending, key, load, edit } = useDraft();
  const [auth, setAuth] = useState<"loading" | "signed-out" | "owner">("loading");
  const [testIdentity, setTestIdentity] = useState(false);
  const [list, setList] = useState<{ id: string; name: string }[]>([]);
  const [rules, setRules] = useState<unknown>(null);
  const [setup, setSetup] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [query, setQuery] = useState("");
  const [position, setPosition] = useState("");
  const [sort, setSort] = useState("projection");
  const [slot, setSlot] = useState("QB");
  const [replacement, setReplacement] = useState<Player | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [conflict, setConflict] = useState(false);
  async function refreshList() {
    const data = z
      .array(z.object({ id: z.string(), name: z.string() }))
      .parse(await api("/api/workspaces"));
    setList(data);
    return data;
  }
  async function open(id: string, discard = false) {
    const value = workspaceSchema.parse(await api(`/api/workspaces/${id}`));
    if (useDraft.getState().pending.length && !discard) {
      if (value.id === w?.id && value.revision === w.revision) {
        useDraft.setState({ workspace: value });
        setStatus("Workspace refreshed. Unsaved edits retained.");
        return;
      }
      setConflict(true);
      throw new Error(
        "Server refreshed. Unsaved edits retained; save or explicitly discard them before loading newer state.",
      );
    }
    load(value);
    setPreview(null);
    setSetup(false);
    setConflict(false);
    setReplacement(null);
    history.replaceState(null, "", `/?workspace=${id}`);
  }
  useEffect(() => {
    void (async () => {
      try {
        const session = z
          .object({ csrf: z.string(), test_identity: z.boolean() })
          .parse(await api("/api/session"));
        setCsrf(session.csrf);
        setTestIdentity(session.test_identity);
        const [available, profile] = await Promise.all([refreshList(), api("/api/rules")]);
        setRules(profile);
        const id = new URLSearchParams(location.search).get("workspace") ?? available[0]?.id;
        if (id) await open(id);
        else setSetup(true);
        setAuth("owner");
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) setAuth("signed-out");
        else {
          setError(err instanceof Error ? err.message : "Unable to load");
          setAuth("signed-out");
        }
      }
    })();
  }, []);
  useEffect(() => {
    if (!pending.length) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [pending.length]);
  async function action(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    setStatus("");
    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed; changes are not saved");
      if (err instanceof ApiError && err.status === 409) setConflict(true);
    } finally {
      setBusy(false);
    }
  }
  async function saveSetup(data: Setup) {
    const result = z
      .object({ workspace_id: z.string() })
      .parse(
        await api(
          w && setup ? `/api/workspaces/${w.id}/setup` : "/api/workspaces",
          data,
          w && setup ? "PUT" : "POST",
        ),
      );
    await refreshList();
    await open(result.workspace_id);
    setStatus("Setup saved");
  }
  if (auth === "loading")
    return (
      <main className="signin">
        <p>Loading your workspace…</p>
      </main>
    );
  if (auth === "signed-out")
    return (
      <main className="signin">
        <p className="eyebrow">DFS / PERSONAL WORKSPACE</p>
        <h1>
          Build your next lineup.
          <br />
          Keep every decision.
        </h1>
        <p className="muted">
          Import your Yahoo pool and save a draft against an exact dated slate.
        </p>
        <p className="banner">
          Local late-swap development build · Not ready for regular weekly use
        </p>
        <a className="button" href="/auth/login">
          Sign in
        </a>
        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}
      </main>
    );
  if (mobile)
    return (
      <MobileReview
        w={w}
        list={list}
        open={open}
        pending={pending.length > 0}
        signOut={async () => {
          await api("/auth/logout", {});
          setAuth("signed-out");
        }}
      />
    );
  const assignments = w ? draftPlayers(w, pending) : {};
  const currentAssignments = Object.values(assignments).map(
    (p) =>
      Object.values(w?.late_swap.fixed ?? {}).find(
        (f) => f.entry_id === p.entry_id && f.subject_id === p.subject_id,
      ) ??
      w?.players.find(
        (c) => c.entry_id === p.entry_id && c.subject_id === p.subject_id && !c.issues.length,
      ),
  );
  const knownSalary = currentAssignments.every(Boolean);
  const total = currentAssignments.reduce((sum, p) => sum + (p?.salary_cents ?? 0), 0);
  const disabled = busy || conflict || !w || w.locked || !w.pool_matches_setup;
  const players =
    w?.players.filter(
      (p) =>
        !p.issues.length &&
        (!position || p.position === position) &&
        `${p.name} ${p.team}`.toLowerCase().includes(query.toLowerCase()),
    ) ?? [];
  const units = (p: Pick<Player, "projection">) => {
    if (p.projection == null) return null;
    const negative = p.projection.startsWith("-");
    const [whole, fraction = ""] = p.projection.replace(/^[+-]/, "").split(".");
    const value = BigInt(whole || "0") * 10000n + BigInt(fraction.padEnd(4, "0").slice(0, 4));
    return negative ? -value : value;
  };
  const selectedUnits = currentAssignments.every((p) => p && p.projection != null)
    ? currentAssignments.reduce((sum, p) => sum + (p ? (units(p) ?? 0n) : 0n), 0n)
    : null;
  players.sort((a, b) => {
    if (sort === "salary")
      return (b.salary_cents ?? 0) - (a.salary_cents ?? 0) || a.yahoo_id.localeCompare(b.yahoo_id);
    const x = units(a),
      y = units(b);
    if (x === null || y === null) return x === y ? 0 : x === null ? 1 : -1;
    const delta =
      sort === "value" ? y * BigInt(a.salary_cents || 1) - x * BigInt(b.salary_cents || 1) : y - x;
    return delta > 0n ? 1 : delta < 0n ? -1 : a.yahoo_id.localeCompare(b.yahoo_id);
  });
  const selected = new Set(Object.values(assignments).map((p) => p.entry_id));
  function choose(player: Player) {
    if (assignments[slot]) setReplacement(player);
    else edit({ op: "add", slot, entry_id: player.entry_id });
  }
  return (
    <div className="shell">
      <header className="topbar">
        <a href="/" className="brand">
          DFS<span> / DRAFT WORKSPACE</span>
        </a>
        <div className="flex gap-3 items-center">
          {testIdentity ? <span className="tag">Synthetic test identity</span> : null}
          <button
            className="subtle"
            disabled={!!pending.length || busy}
            onClick={() =>
              void action(async () => {
                await api("/auth/logout", {});
                setAuth("signed-out");
              })
            }
          >
            Sign out
          </button>
        </div>
      </header>
      <div className="banner">
        Local late-swap development build · Entered players lock at each game’s kickoff. Not ready
        for weekly use.
      </div>
      <div className="page-heading">
        <div>
          <p className="eyebrow">YOUR CONTEST</p>
          <h1>{w?.name ?? "Start a workspace"}</h1>
          <p className="muted">
            {w
              ? `${w.season} · ${w.round} · ${w.games.length} dated games · ${w.setup.timezone}`
              : "An exact slate. A durable draft."}
          </p>
        </div>
        <div className="flex gap-2">
          <select
            aria-label="Choose workspace"
            value={w?.id ?? ""}
            disabled={!!pending.length || busy}
            onChange={(e) => void action(() => open(e.target.value))}
          >
            <option value="" disabled>
              Choose workspace
            </option>
            {list.map((c) => (
              <option value={c.id} key={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <button
            className="secondary"
            disabled={!!pending.length || busy}
            onClick={() => {
              useDraft.setState({ workspace: null });
              setStatus("");
              setSetup(true);
              setPreview(null);
            }}
          >
            New contest
          </button>
        </div>
      </div>
      {error ? (
        <div role="alert" className="error notice">
          {error}
          {pending.length
            ? " Your attempted edits remain below; no automatic retry or overwrite occurred."
            : ""}
        </div>
      ) : null}
      {status && (!pending.length || status.startsWith("Workspace refreshed.")) ? (
        <p role="status" className="success notice">
          {status}
        </p>
      ) : null}
      <main className="workspace-grid">
        <div className="research space-y-5">
          {setup ? (
            <>
              <SetupForm workspace={w ?? undefined} rules={rules} onSave={saveSetup} />
              {w ? (
                <button className="subtle" onClick={() => setSetup(false)}>
                  Close setup
                </button>
              ) : null}
            </>
          ) : w ? (
            <>
              <section className="card flex justify-between items-center">
                <div>
                  <h3>{w.late_swap.mode}</h3>
                  {w.late_swap.blockers.length ? (
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() => {
                        const panel = document.getElementById("reconciliation");
                        if (panel instanceof HTMLDetailsElement) {
                          panel.open = true;
                          panel.scrollIntoView({ block: "start" });
                        }
                      }}
                    >
                      Review entered reconciliation
                    </button>
                  ) : null}
                  <button
                    className="subtle"
                    disabled={busy}
                    onClick={() => void action(() => open(w.id))}
                  >
                    Refresh workspace
                  </button>
                  <p className="muted">
                    {w.deadline
                      ? new Date(w.deadline).toLocaleString("en-US", {
                          timeZone: "America/Chicago",
                          dateStyle: "medium",
                          timeStyle: "short",
                        })
                      : w.late_swap.all_locked
                        ? "Every game has reached its established deadline"
                        : "Required deadline unknown"}
                  </p>
                  {!w.pool_matches_setup ? (
                    <p className="error">
                      Upload and activate a pool for this setup to enable edits.
                    </p>
                  ) : null}
                </div>
                <button
                  className="secondary"
                  disabled={!!pending.length || busy}
                  onClick={() => setSetup(true)}
                >
                  Review setup
                </button>
              </section>
              <Environments
                key={w.id}
                w={w}
                disabled={busy || !!pending.length}
                reload={() => open(w.id)}
              />
              <details className="card">
                <summary>Yahoo source management</summary>
                <ImportPanel
                  activeCount={w.players.filter((p) => !p.issues.length).length}
                  preview={preview}
                  busy={busy}
                  disabled={busy || !!pending.length}
                  onUpload={(file) =>
                    void action(async () => {
                      const form = new FormData();
                      form.append("file", file);
                      const result = z
                        .object({ batch_id: z.string() })
                        .parse(await api(`/api/workspaces/${w.id}/imports`, form));
                      setPreview(
                        previewSchema.parse(
                          await api(`/api/workspaces/${w.id}/imports/${result.batch_id}`),
                        ),
                      );
                    })
                  }
                  onActivate={() =>
                    void action(async () => {
                      if (!preview) return;
                      await api(`/api/workspaces/${w.id}/activate`, {
                        expected_revision: w.revision,
                        batch_id: preview.id,
                        batch_revision: preview.revision,
                      });
                      await open(w.id);
                      setStatus("Reviewed pool activated. Existing selections preserved.");
                    })
                  }
                />
                {w.imports.length ? (
                  <details className="card">
                    <summary>Previous import reviews</summary>
                    {w.imports.map((b) => (
                      <button
                        className="subtle block"
                        key={b.id}
                        onClick={() =>
                          void action(async () =>
                            setPreview(
                              previewSchema.parse(
                                await api(`/api/workspaces/${w.id}/imports/${b.id}`),
                              ),
                            ),
                          )
                        }
                      >
                        {new Date(b.created_at).toLocaleString()}
                      </button>
                    ))}
                  </details>
                ) : null}
              </details>
              <AnalysisPanel
                key={w.id}
                w={w}
                disabled={busy || !!pending.length}
                reload={() => open(w.id)}
              />
              <section className="card">
                <p className="eyebrow">03 / PLAYER RESEARCH</p>
                <h2>Find your next selection</h2>
                <div className="filters">
                  <input
                    aria-label="Search players"
                    placeholder="Search name or team"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                  <select
                    aria-label="Position filter"
                    value={position}
                    onChange={(e) => setPosition(e.target.value)}
                  >
                    <option value="">All positions</option>
                    {["QB", "RB", "WR", "TE", "DEF"].map((p) => (
                      <option key={p}>{p}</option>
                    ))}
                  </select>
                  <select
                    aria-label="Target slot"
                    value={slot}
                    onChange={(e) => {
                      setSlot(e.target.value);
                      setReplacement(null);
                    }}
                  >
                    {slots.map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </div>
                <label>
                  Sort players
                  <select
                    aria-label="Sort players"
                    value={sort}
                    onChange={(e) => setSort(e.target.value)}
                  >
                    <option value="projection">Projected points</option>
                    <option value="salary">Salary</option>
                    <option value="value">Points per salary dollar</option>
                  </select>
                </label>
                <p className="muted">
                  Points per dollar is descriptive; completion maximizes projected points.
                </p>
                <p className="muted">
                  FPPG is historical source data. Blank injury or starting fields provide no
                  clearance or starter evidence.
                </p>
                {replacement ? (
                  <div className="inset">
                    <p>
                      Replace {assignments[slot]?.name} with {replacement.name} in {slot}?
                    </p>
                    <button
                      disabled={disabled}
                      onClick={() => {
                        edit({
                          op: "replace",
                          slot,
                          entry_id: replacement.entry_id,
                        });
                        setReplacement(null);
                      }}
                    >
                      Confirm replacement
                    </button>
                    <button className="subtle" onClick={() => setReplacement(null)}>
                      Cancel
                    </button>
                  </div>
                ) : null}
                {!players.length ? (
                  <p className="empty">
                    {w.active_pool_id
                      ? "No players match your search."
                      : "Activate a reviewed import to browse players."}
                  </p>
                ) : (
                  <div className="player-list">
                    {players.slice(0, 150).map((p) => (
                      <div className="player" key={p.row_id}>
                        <div>
                          <strong>{p.name}</strong>
                          {w.late_swap.started.includes(p.game_id ?? "") ? (
                            <small className="tag">
                              Game locked · unavailable for new selection
                            </small>
                          ) : null}
                          {w.preferences.find((v) => v.entry_id === p.entry_id) ? (
                            <span className="tag">
                              {w.preferences.find((v) => v.entry_id === p.entry_id)?.value}
                            </span>
                          ) : null}
                          <p className="muted">
                            {p.position} · {p.team} vs {p.opponent}
                            {p.injury ? ` · ${p.injury}` : ""}
                          </p>
                          <small>
                            Projection {p.projection ?? "missing"} · Historical FPPG{" "}
                            {p.historical_fppg ?? "unknown"}
                          </small>
                          <small>
                            {p.projection != null && p.salary_cents
                              ? `${(Number(p.projection) / (p.salary_cents / 100)).toFixed(3)} pts/$`
                              : "Value missing"}{" "}
                            ·{" "}
                            {centralTime(w.games.find((g) => g.id === p.game_id)?.kickoff ?? null)}
                          </small>
                          <details>
                            <summary>Player evidence</summary>
                            <p>
                              Yahoo eligibility {p.position} · Source line {p.line}
                            </p>
                            <p>
                              {p.injury
                                ? `Recorded designation: ${p.injury}`
                                : "Availability designation unknown"}
                            </p>
                            <p>Accepted projected points: {p.projection ?? "missing"}</p>
                          </details>
                        </div>
                        <strong>{money(p.salary_cents ?? 0)}</strong>
                        <button
                          className="secondary"
                          disabled={
                            disabled ||
                            selected.has(p.entry_id) ||
                            !!w.late_swap.fixed[slot] ||
                            w.late_swap.started.includes(p.game_id ?? "") ||
                            !(slot === "FLEX"
                              ? ["RB", "WR", "TE"].includes(p.position)
                              : slot.replace(/[123]/g, "") === p.position)
                          }
                          onClick={() => choose(p)}
                        >
                          {assignments[slot] ? "Replace" : "Add"}
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                {players.length > 150 ? (
                  <p className="muted">
                    Showing first 150 of {players.length}. Narrow your search.
                  </p>
                ) : null}
              </section>
            </>
          ) : null}
        </div>
        <aside className="lineup card">
          <p className="eyebrow">YOUR WORKING LINEUP</p>
          <h2>Draft</h2>
          <div className="flex justify-between my-5">
            <div className="stat">
              {knownSalary ? money(total) : "Unknown"}
              <small>current salary</small>
            </div>
            <div className={`stat ${total > 20000 ? "text-red-800" : ""}`}>
              {knownSalary ? money(20000 - total) : "Unknown"}
              <small>remaining</small>
            </div>
          </div>
          {w && w.late_swap.started.length > 0 ? (
            <p>
              Editable salary capacity:{" "}
              {Object.values(w.late_swap.fixed).every((p) => p.salary_cents !== null)
                ? money(
                    20000 -
                      Object.values(w.late_swap.fixed).reduce(
                        (sum, p) => sum + (p.salary_cents ?? 0),
                        0,
                      ),
                  )
                : "unresolved"}
              . Fixed salaries use the entered Yahoo evidence.
            </p>
          ) : null}
          {pending.length ? (
            <p>
              Unsaved draft projection:{" "}
              {selectedUnits === null
                ? "Incomplete"
                : `${Number(selectedUnits) / 10000} pts across ${currentAssignments.length} selected players`}
            </p>
          ) : null}
          <p className={pending.length ? "unsaved" : "muted"}>
            {pending.length
              ? `${pending.length} unsaved edit${pending.length === 1 ? "" : "s"}`
              : w
                ? "Showing saved server draft"
                : "No saved draft yet"}
          </p>
          {slots.map((s) => (
            <div className="lineup-slot" key={s}>
              <span className="slot-key">{s}</span>
              <div className="min-w-0 flex-1">
                <strong>{assignments[s]?.name ?? "Open slot"}</strong>
                {w?.late_swap.fixed[s] ? (
                  <small className="tag">
                    Fixed · entered at kickoff{" "}
                    {centralTime(w.late_swap.deadlines[w.late_swap.fixed[s].game_id ?? ""] ?? null)}
                  </small>
                ) : (
                  <small>Editable slot</small>
                )}
                {w?.preferences.find((p) => p.entry_id === assignments[s]?.entry_id) ? (
                  <span className="tag">
                    {w.preferences.find((p) => p.entry_id === assignments[s]?.entry_id)?.value}
                  </span>
                ) : null}
                {assignments[s] ? (
                  <small>
                    {assignments[s].team} · {money(assignments[s].salary_cents ?? 0)} selected
                    {w?.assignments[s]?.concerns.map((c) => (
                      <span className="error block" key={c}>
                        {c}
                      </span>
                    ))}
                    {w?.assignments[s]?.current &&
                    w.assignments[s].current.salary_cents !== assignments[s].salary_cents ? (
                      <span className="block">
                        Active pool salary: {money(w.assignments[s].current.salary_cents ?? 0)}
                      </span>
                    ) : null}
                  </small>
                ) : null}
              </div>
              {assignments[s] ? (
                <button
                  className="subtle"
                  aria-label={`Remove ${s}`}
                  disabled={disabled || !!w?.late_swap.fixed[s]}
                  onClick={() => edit({ op: "remove", slot: s })}
                >
                  ×
                </button>
              ) : null}
            </div>
          ))}
          {w ? (
            <DraftHistory
              w={w}
              assignments={assignments}
              disabled={disabled || !!pending.length}
              reload={() => open(w.id)}
            />
          ) : null}
          {w ? <Reconciliation key={w.id} w={w} disabled={busy} reload={() => open(w.id)} /> : null}
          <div id="completion-preview" />
          <div className="mt-5 space-y-3">
            <button
              className="w-full"
              disabled={disabled || !pending.length}
              onClick={() =>
                void action(async () => {
                  if (!w) return;
                  await api(
                    `/api/workspaces/${w.id}/draft`,
                    { expected_revision: w.revision, operations: pending },
                    "POST",
                    key,
                  );
                  // Durable server acknowledgement precedes clearing pending edits.
                  await open(w.id, true);
                  setStatus("Draft saved.");
                })
              }
            >
              Save draft
            </button>
            {pending.length ? (
              <button
                className="secondary w-full"
                disabled={busy}
                onClick={() =>
                  void action(async () => {
                    if (w) await open(w.id, true);
                  })
                }
              >
                Discard attempted edits and reload saved draft
              </button>
            ) : null}
            {conflict && pending.length ? (
              <details open>
                <summary>Attempted changes retained for review</summary>
                <ol className="list-decimal pl-5 text-sm space-y-2">
                  {pending.map((operation, index) => (
                    <li key={index}>
                      {operation.op === "remove"
                        ? `Remove selection from ${operation.slot}`
                        : `${operation.op === "add" ? "Add" : "Replace with"} ${w?.players.find((p) => p.entry_id === operation.entry_id)?.name ?? "selected player"} in ${operation.slot}`}
                    </li>
                  ))}
                </ol>
              </details>
            ) : null}
            {w?.locked ? (
              <p className="error">
                {w.late_swap.blockers.join("; ") ||
                  "All games locked. Historical evidence remains available."}
              </p>
            ) : null}
            <details>
              <summary>Saved draft issues ({w?.issues.length ?? 0})</summary>
              {w?.issues.map((issue) => (
                <p className="muted" key={issue}>
                  {issue}
                </p>
              ))}
            </details>
            <p className="muted">
              Incomplete and over-budget drafts can be saved. Saving does not establish contest
              legality.
            </p>
          </div>
        </aside>
      </main>
    </div>
  );
}
