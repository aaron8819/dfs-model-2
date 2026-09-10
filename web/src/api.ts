import { z } from "zod";
import type { components } from "./generatedApi";

export const playerSchema = z.object({
  entry_id: z.string(),
  row_id: z.string(),
  subject_id: z.string(),
  name: z.string(),
  position: z.string(),
  team: z.string(),
  opponent: z.string(),
  game: z.string(),
  game_id: z.string().optional(),
  salary_cents: z.number().nullable(),
  yahoo_id: z.string(),
  injury: z.string().nullable(),
  historical_fppg: z.string().nullable(),
  projection: z.string().nullable().optional(),
  starting: z.string().nullable(),
  line: z.number(),
  issues: z.array(z.string()).default([]),
  raw: z.record(z.string(), z.string()).optional(),
});
export type Player = z.infer<typeof playerSchema>;
const enteredPlayer = playerSchema.extend({
  subject_id: z.string().nullable(),
  game_id: z.string().nullable().optional(),
});
export const gameSchema = z.object({
  event_key: z.string(),
  away: z.string(),
  home: z.string(),
  kickoff: z.string().nullable(),
});
export const setupSchema = z.object({
  name: z.string().min(1),
  yahoo_id: z.string().min(1),
  season: z.string().min(1),
  round: z.string().min(1),
  timezone: z.string().min(1),
  games: z.array(gameSchema).min(1),
  confirmed: z.literal(true),
  provenance: z.string().min(5),
  expected_revision: z.number().optional(),
  membership_change_confirmed: z.boolean(),
});
export type Setup = components["schemas"]["SetupInput"];
export const environmentSchema = z.object({
  id: z.string(),
  game_id: z.string(),
  source: z.string(),
  reference: z.string(),
  observed_at: z.string(),
  published_at: z.string().nullable(),
  created_at: z.string(),
  total: z.string(),
  home_spread: z.string(),
  home_implied: z.string(),
  away_implied: z.string(),
  current_setup: z.boolean(),
  total_change: z.string().nullable(),
  spread_change: z.string().nullable(),
});
export const workspaceSchema = z.object({
  id: z.string(),
  name: z.string(),
  yahoo_id: z.string(),
  season: z.string(),
  round: z.string(),
  revision: z.number(),
  active_pool_id: z.string().nullable(),
  draft_id: z.string().nullable(),
  context_revision: z.number(),
  environments: z.array(environmentSchema),
  undo_available: z.boolean(),
  preferences: z.array(z.object({ entry_id: z.string(), value: z.string(), name: z.string() })),
  entered_status: z.enum(["none", "matches", "differs"]),
  entered: z
    .object({
      id: z.string(),
      created_at: z.string(),
      parent_id: z.string().nullable(),
      assignments: z.record(z.string(), enteredPlayer),
    })
    .nullable(),
  locked: z.boolean(),
  late_swap: z.object({
    mode: z.string(),
    started: z.array(z.string()),
    blockers: z.array(z.string()),
    fixed: z.record(z.string(), enteredPlayer),
    all_locked: z.boolean(),
    deadlines: z.record(z.string(), z.string().nullable()),
  }),
  pool_matches_setup: z.boolean(),
  deadline: z.string().nullable(),
  games: z.array(gameSchema.extend({ id: z.string() })),
  setup: z.object({
    timezone: z.string(),
    provenance: z.string(),
    confirmed_at: z.string(),
  }),
  players: z.array(playerSchema),
  issues: z.array(z.string()),
  assignments: z.record(
    z.string(),
    playerSchema.extend({
      concerns: z.array(z.string()),
      current: playerSchema.nullable(),
    }),
  ),
  imports: z.array(z.object({ id: z.string(), created_at: z.string() })),
});
export type Workspace = z.infer<typeof workspaceSchema>;
export const previewSchema = z.object({
  id: z.string(),
  revision: z.number(),
  summary: z.record(z.string(), z.number()),
  errors: z.array(z.string()),
  rows: z.array(playerSchema),
  setup_matches: z.boolean(),
  imported_at: z.string(),
  provider_updated_at: z.string().nullable(),
  changes: z.object({
    added: z.array(z.string()),
    removed: z.array(z.string()),
    changed: z.array(z.string()),
  }),
});
export type Preview = z.infer<typeof previewSchema>;
export type Operation = components["schemas"]["Operation"];
let csrf = "";
export function setCsrf(value: string): void {
  csrf = value;
}
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function api(
  path: string,
  body?: unknown,
  method = "POST",
  key?: string,
): Promise<unknown> {
  const options: RequestInit =
    body === undefined
      ? {}
      : {
          method,
          headers: {
            "X-CSRF-Token": csrf,
            "Idempotency-Key": key ?? crypto.randomUUID(),
            ...(body instanceof FormData ? {} : { "Content-Type": "application/json" }),
          },
          body: body instanceof FormData ? body : JSON.stringify(body),
        };
  const response = await fetch(path, options);
  if (!response.ok) {
    const payload: unknown = await response.json();
    const parsed = z.object({ detail: z.unknown() }).safeParse(payload);
    const detail = parsed.success ? parsed.data.detail : null;
    const message = z.object({ message: z.string() }).safeParse(detail);
    const validation = z.array(z.object({ msg: z.string() })).safeParse(detail);
    throw new ApiError(
      response.status,
      typeof detail === "string"
        ? detail
        : message.success
          ? message.data.message
          : validation.success
            ? validation.data.map((issue) => issue.msg).join("; ")
            : "Request failed. Your changes are not confirmed saved.",
    );
  }
  return response.status === 204 ? null : response.json();
}
