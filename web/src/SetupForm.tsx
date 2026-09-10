import { useState } from "react";
import { z } from "zod";
import { setupSchema, type Setup, type Workspace } from "./api";

type Props = {
  workspace?: Workspace;
  rules: unknown;
  onSave: (setup: Setup) => Promise<void>;
};
export function SetupForm({ workspace, rules, onSave }: Props) {
  const [games, setGames] = useState<
    { event_key: string; away: string; home: string; kickoff: string }[]
  >(
    workspace?.games.map((g) => ({ ...g, kickoff: g.kickoff ?? "" })) ?? [
      { event_key: crypto.randomUUID(), away: "", home: "", kickoff: "" },
    ],
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const scoring = z.object({ scoring: z.record(z.string(), z.string()) }).safeParse(rules);
  return (
    <form
      className="card space-y-5"
      onSubmit={async (event) => {
        event.preventDefault();
        setError("");
        setBusy(true);
        const form = new FormData(event.currentTarget);
        try {
          await onSave(
            setupSchema.parse({
              name: form.get("name"),
              yahoo_id: form.get("yahoo_id"),
              season: form.get("season"),
              round: form.get("round"),
              timezone: form.get("timezone"),
              games: games.map((g) => ({ ...g, kickoff: g.kickoff || null })),
              confirmed: workspace ? true : form.get("confirmed") === "on",
              provenance: form.get("provenance"),
              expected_revision: workspace?.revision,
              membership_change_confirmed: form.get("membership") === "on",
            }),
          );
        } catch (err) {
          setError(err instanceof Error ? err.message : "Setup failed");
        } finally {
          setBusy(false);
        }
      }}
    >
      <div>
        <p className="eyebrow">01 / CONTEST & SLATE</p>
        <h2>{workspace ? "Revise dated schedule" : "Set up your contest"}</h2>
        <p className="muted">Confirm the exact games and applicable Yahoo rules once.</p>
      </div>
      <div className="grid grid-cols-2 gap-4">
        {(
          [
            ["name", "Contest name"],
            ["yahoo_id", "Yahoo URL or identifier"],
            ["season", "Season"],
            ["round", "Round"],
          ] as const
        ).map(([name, label]) => (
          <label key={name}>
            {label}
            <input
              name={name}
              required
              readOnly={!!workspace}
              defaultValue={workspace?.[name] ?? ""}
            />
          </label>
        ))}
        <label>
          Display timezone
          <input
            name="timezone"
            required
            defaultValue={workspace?.setup.timezone ?? "America/Chicago"}
          />
        </label>
      </div>
      <div>
        <h3>Exact dated games</h3>
        <p className="muted">
          Use Yahoo codes (LA, JAC). Enter an ISO date with timezone, such as 2030-09-08T17:00:00Z.
          Blank kickoff blocks editing.
        </p>
      </div>
      {games.map((game, i) => (
        <div key={game.event_key} className="grid grid-cols-[75px_75px_1fr_auto] items-end gap-3">
          <label>
            Away
            <input
              aria-label={`Game ${i + 1} away`}
              required
              value={game.away}
              onChange={(e) =>
                setGames(
                  games.map((g, j) => (j === i ? { ...g, away: e.target.value.toUpperCase() } : g)),
                )
              }
            />
          </label>
          <label>
            Home
            <input
              aria-label={`Game ${i + 1} home`}
              required
              value={game.home}
              onChange={(e) =>
                setGames(
                  games.map((g, j) => (j === i ? { ...g, home: e.target.value.toUpperCase() } : g)),
                )
              }
            />
          </label>
          <label>
            Dated kickoff
            <input
              aria-label={`Game ${i + 1} kickoff`}
              value={game.kickoff}
              placeholder="YYYY-MM-DDTHH:MM:SSZ"
              onChange={(e) =>
                setGames(games.map((g, j) => (j === i ? { ...g, kickoff: e.target.value } : g)))
              }
            />
          </label>
          <button
            type="button"
            className="subtle"
            aria-label={`Remove game ${i + 1}`}
            disabled={games.length === 1}
            onClick={() => setGames(games.filter((_, j) => j !== i))}
          >
            ×
          </button>
        </div>
      ))}
      <button
        type="button"
        className="secondary"
        disabled={games.length >= 16}
        onClick={() =>
          setGames([...games, { event_key: crypto.randomUUID(), away: "", home: "", kickoff: "" }])
        }
      >
        Add game
      </button>
      {workspace ? (
        <label className="check">
          <input name="membership" type="checkbox" />I explicitly confirm any changed game
          membership and will reimport to revalidate.
        </label>
      ) : null}
      <div className="inset">
        <h3>Yahoo NFL candidate profile</h3>
        <p>$200 · QB / RB / RB / WR / WR / WR / TE / FLEX / DEF</p>
        <p>FLEX: RB, WR, TE · At least 3 teams · Maximum 6 per team, including DEF</p>
        <p>
          Game kickoff lock policy. Entered players remain fixed in their exact slots after their
          game starts; later games remain editable.
        </p>
        <details>
          <summary>Review applicable scoring</summary>
          <table className="w-full text-left text-xs">
            <thead>
              <tr>
                <th className="py-2">Statistic</th>
                <th>Points / treatment</th>
              </tr>
            </thead>
            <tbody>
              {scoring.success
                ? Object.entries(scoring.data.scoring).map(([label, value]) => (
                    <tr key={label}>
                      <td className="py-1 capitalize">{label.replaceAll("_", " ")}</td>
                      <td>{value}</td>
                    </tr>
                  ))
                : null}
            </tbody>
          </table>
        </details>
        {workspace ? (
          <p>Rules confirmed {new Date(workspace.setup.confirmed_at).toLocaleString()}.</p>
        ) : (
          <label className="check">
            <input name="confirmed" type="checkbox" required />I confirm this rule profile applies
            to this contest.
          </label>
        )}
      </div>
      <label>
        Confirmation / schedule source
        <input
          name="provenance"
          required
          minLength={5}
          defaultValue={workspace?.setup.provenance ?? ""}
          placeholder="Yahoo contest reviewed by owner, or clearly synthetic test setup"
        />
      </label>
      {error ? (
        <p role="alert" className="error">
          {error}
        </p>
      ) : null}
      <button disabled={busy}>
        {busy ? "Saving setup…" : workspace ? "Save setup revision" : "Create workspace"}
      </button>
    </form>
  );
}
