import type { DraftAction as LibDraftAction } from "@/lib/actions";

export type DraftAction = LibDraftAction;

export interface AgentReply {
  reply: string;
  draft?: DraftAction[];
}

export type AgentMode = "propose_only" | "safe_auto" | "full_auto";
