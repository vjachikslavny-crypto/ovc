import type { DraftAction, AgentReply } from "@/types/agent";
import { MockLLMProvider } from "./mock";

export type LLMPlanContext = {
  text: string;
  noteId?: string;
  notes: Array<{ id: string; title: string; contentMd: string }>;
  languages?: string[];
};

export interface LLMProvider {
  plan(context: LLMPlanContext): Promise<AgentReply>;
}

export function createLLMProvider(): LLMProvider {
  const provider = (process.env.LLM_PROVIDER || "mock").toLowerCase();
  switch (provider) {
    case "mock":
    default:
      return new MockLLMProvider();
  }
}
