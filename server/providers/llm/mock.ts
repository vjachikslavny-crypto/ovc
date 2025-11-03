import type { AgentReply } from "@/types/agent";
import { planAndDraftActions } from "@/server/agent";
import type { LLMPlanContext, LLMProvider } from "./index";

export class MockLLMProvider implements LLMProvider {
  async plan(context: LLMPlanContext): Promise<AgentReply> {
    const reply = await planAndDraftActions(context.text, {
      notes: context.notes,
      noteId: context.noteId,
      languages: context.languages
    });
    return reply;
  }
}
