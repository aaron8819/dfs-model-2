import { create } from "zustand";
import type { Operation, Player, Workspace } from "./api";

type DraftState = {
  workspace: Workspace | null;
  pending: Operation[];
  key: string;
  load: (workspace: Workspace) => void;
  edit: (operation: Operation) => void;
};
export const useDraft = create<DraftState>((set) => ({
  workspace: null,
  pending: [],
  key: crypto.randomUUID(),
  load: (workspace) => set({ workspace, pending: [], key: crypto.randomUUID() }),
  edit: (operation) =>
    set((s) => ({
      pending: [...s.pending, operation],
      key: crypto.randomUUID(),
    })),
}));
export function draftPlayers(workspace: Workspace, pending: Operation[]): Record<string, Player> {
  const result: Record<string, Player> = { ...workspace.assignments };
  for (const operation of pending) {
    if (operation.op === "remove") delete result[operation.slot];
    else {
      const player = workspace.players.find(
        (p) => p.entry_id === operation.entry_id && !p.issues.length,
      );
      if (player) result[operation.slot] = player;
    }
  }
  return result;
}
