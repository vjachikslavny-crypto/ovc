import { DraftAction, AgentReply, AgentMode } from "@/types/agent";
import { db } from "@/lib/db";
import { ragSearch } from "@/lib/rag";
import type { SearchResult } from "@/lib/rag";
import { commitDraft } from "@/server/agent/commitDraft";
import { getLLM } from "@/server/providers/llm";
import { planAndDraftActions } from "@/server/agent";

const DEFAULT_MODE: AgentMode = "propose_only";
const agentMode = (process.env.AGENT_MODE as AgentMode) || DEFAULT_MODE;
const REPLY_LIMIT = Number(process.env.AGENT_REPLY_LIMIT ?? 900);
const DEFAULT_REPLY = "Принял. Могу создать новую заметку или дополнить существующую.";
const LINK_STOP_WORDS = new Set([
  "на",
  "и",
  "в",
  "о",
  "с",
  "по",
  "the",
  "and",
  "of",
  "для",
  "про",
  "off",
  "on"
]);

export async function handleUserMessage(text: string, options: HandleOptions = {}): Promise<AgentReply> {
  try {
    return await runPipeline(text, options);
  } catch (error) {
    console.error("handleUserMessage critical failure", error);
    return buildFallbackAgentReply(text);
  }
}

type HandleOptions = {
  noteId?: string;
  languages?: string[];
};

async function runPipeline(text: string, options: HandleOptions): Promise<AgentReply> {
  const noteList = await db.query.notes.findMany({
    columns: {
      id: true,
      title: true,
      contentMd: true
    },
    orderBy: (table, { desc }) => [desc(table.updatedAt)]
  });

  const llm = getLLM();

  const response = await planAndDraftActions(text, {
    notes: noteList,
    noteId: options.noteId,
    languages: options.languages
  });

  let draft = response.draft ?? [];
  let reply = normalizeReply(response.reply);

  let ragMatches: SearchResult[] = [];
  try {
    ragMatches = await ragSearch(text, 5);
  } catch (error) {
    console.warn("ragSearch failed", error);
  }

  try {
    const llmReply = await llm.chat(
      buildLLMPrompt(text, draft, ragMatches),
      "Ты — локальный помощник заметок. Работай офлайн."
    );
    if (llmReply && llmReply.trim().length > 0) {
      reply = normalizeReply(llmReply);
    }
  } catch (error) {
    console.warn("LLM mock chat failed", error);
  }

  if (!draft.some((action) => action.type === "create_note" || action.type === "update_note")) {
    const fallbackCreate = buildBasicCreateAction(text);
    draft = [fallbackCreate, ...draft];

    const parent = findLikelyParentNote(fallbackCreate.title, noteList);
    if (parent) {
      if (!draft.some((action) => action.type === "update_note" && action.id === parent.id)) {
        draft.splice(1, 0, {
          type: "update_note",
          id: parent.id,
          patch_md: `- [[${fallbackCreate.title}]] — добавлено ${new Date().toLocaleDateString("ru-RU")}`,
          position: "append"
        });
      }
      if (!draft.some((action) => action.type === "add_link" && action.from_id === parent.id && action.to_title === fallbackCreate.title)) {
        draft.splice(2, 0, {
          type: "add_link",
          from_id: parent.id,
          to_title: fallbackCreate.title,
          reason: "auto_fallback",
          confidence: 0.95
        });
      }
      reply = normalizeReply(`${reply} Связал с «${parent.title}».`);
    }
  }

  let targetNoteId = options.noteId;
  if (!targetNoteId) {
    const updateAction = draft.find((action) => action.type === "update_note");
    if (updateAction?.type === "update_note") targetNoteId = updateAction.id;
  }
  if (!targetNoteId) {
    const linkAction = draft.find((action) => action.type === "add_link");
    if (linkAction?.type === "add_link") targetNoteId = linkAction.from_id;
  }

  // Интернет выключен, веб-обогащение не выполняется

  if (draft.length > 1) {
    draft = dedupeDraft(draft);
  }

  if (!draft || draft.length === 0) {
    return { reply, draft };
  }

  const { remainingDraft, autoAppliedCount } = await maybeAutoApply(draft, {
    userId: "agent-auto",
    mode: agentMode
  });

  if (autoAppliedCount > 0) {
    const append = ` Автоматически применено ${autoAppliedCount} безопасных действий.`;
    return {
      reply: normalizeReply(`${reply}${append}`),
      draft: remainingDraft
    };
  }

  return {
    reply: normalizeReply(reply),
    draft: remainingDraft
  };
}

function dedupeDraft(actions: DraftAction[]) {
  const seen = new Set<string>();
  const result: DraftAction[] = [];
  for (const action of actions) {
    const key = actionDedupeKey(action);
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(action);
  }
  return result;
}

function actionDedupeKey(action: DraftAction) {
  switch (action.type) {
    case "create_note":
      return `create:${action.title.toLowerCase()}`;
    case "update_note":
      return `update:${action.id}:${action.position}:${hashString(action.patch_md)}`;
    case "add_link":
      return `link:${action.from_id}:${action.to_title.toLowerCase()}:${action.reason}`;
    case "add_source":
      return `source:${action.note_id}:${action.source.url}`;
    case "add_tag":
      return `tag:${action.note_id}:${action.tag.toLowerCase()}`;
    default:
      return JSON.stringify(action);
  }
}

function hashString(input: string) {
  let hash = 0;
  for (let i = 0; i < input.length; i += 1) {
    hash = (hash << 5) - hash + input.charCodeAt(i);
    hash |= 0;
  }
  return hash.toString(16);
}

function maybeAutoApply(draft: DraftAction[], { userId, mode }: { userId: string; mode: AgentMode }) {
  if (mode === "propose_only" || draft.length === 0) {
    return Promise.resolve({ remainingDraft: draft, autoAppliedCount: 0 });
  }

  const safeActions = draft.filter((action) => {
    if (action.type === "add_tag") return true;
    if (action.type === "add_link") return action.confidence >= 0.85;
    return mode === "full_auto";
  });

  if (safeActions.length === 0) {
    return Promise.resolve({ remainingDraft: draft, autoAppliedCount: 0 });
  }

  return commitDraft(safeActions, { userId })
    .then((result) => ({ remainingDraft: draft.filter((action) => !safeActions.includes(action)), autoAppliedCount: result.applied }))
    .catch((error) => {
      console.error("Failed to auto-apply actions", error);
      return { remainingDraft: draft, autoAppliedCount: 0 };
    });
}

function buildFallbackAgentReply(text: string): AgentReply {
  return {
    reply: DEFAULT_REPLY,
    draft: [buildBasicCreateAction(text)]
  };
}

function buildBasicCreateAction(text: string): DraftAction {
  const normalized = text?.trim() || "Новая заметка";
  const primary = normalized.split(/[.!?\n]/)[0]?.trim() || normalized;
  const title = prettifyTitle(primary);
  const body = normalized.length > 120 ? normalized : `- ${normalized}`;
  return {
    type: "create_note",
    title,
    content_md: `# ${title}\n\n${body}`
  };
}

function findLikelyParentNote(title: string, notes: Array<{ id: string; title: string }>) {
  const normalizedTitle = normalizeForMatch(title);
  const newTokens = tokenizeForMatch(title);
  if (newTokens.length === 0) return null;

  let bestScore = 0;
  let best: { id: string; title: string } | null = null;

  for (const note of notes) {
    const existingNormalized = normalizeForMatch(note.title);
    if (!existingNormalized) continue;

    if (
      normalizedTitle === existingNormalized ||
      normalizedTitle.startsWith(`${existingNormalized} `) ||
      normalizedTitle.includes(` ${existingNormalized} `)
    ) {
      return note;
    }

    const existingTokens = tokenizeForMatch(note.title);
    if (existingTokens.length === 0) continue;

    const overlap = existingTokens.filter((token) => newTokens.includes(token)).length;
    if (overlap === 0) continue;

    const jaccard = overlap / new Set([...existingTokens, ...newTokens]).size;
    const coverage = overlap / existingTokens.length;
    const score = Math.max(jaccard, coverage);

    if (score > bestScore) {
      bestScore = score;
      best = note;
    }
  }

  if (bestScore >= 0.15) {
    return best;
  }
  return null;
}

function normalizeForMatch(text: string) {
  return text.toLowerCase().replace(/[^a-zа-яё0-9]+/g, " ").trim();
}

function tokenizeForMatch(text: string) {
  return normalizeForMatch(text)
    .split(" ")
    .map((token) => token.trim())
    .filter((token) => token && !LINK_STOP_WORDS.has(token));
}

function prettifyTitle(raw: string) {
  const lower = raw.toLowerCase();
  const capitalized = lower.replace(/(^|\s)([a-zа-яё])/g, (match) => match.toUpperCase());
  return capitalized.slice(0, 80);
}

function normalizeReply(text: string | undefined) {
  const limit = Number.isFinite(REPLY_LIMIT) && REPLY_LIMIT > 50 ? REPLY_LIMIT : 900;
  const trimmed = text?.toString().trim();
  if (!trimmed) return DEFAULT_REPLY;
  if (trimmed.length <= limit) return trimmed;
  return `${trimmed.slice(0, limit - 1).trimEnd()}…`;
}

function buildLLMPrompt(message: string, draft: DraftAction[], related: SearchResult[]) {
  const summary = draft
    .map((action, index) => {
      switch (action.type) {
        case "create_note":
          return `${index + 1}. Создать заметку «${action.title}».`;
        case "update_note":
          return `${index + 1}. Обновить заметку ${action.id}: ${plainPreview(action.patch_md)}`;
        case "add_link":
          return `${index + 1}. Связать ${action.from_id} → ${action.to_title}.`;
        case "add_tag":
          return `${index + 1}. Добавить тег ${action.tag} к ${action.note_id}.`;
        case "add_source":
          return `${index + 1}. Добавить источник ${action.source.url}.`;
        default:
          return `${index + 1}. ${action.type}`;
      }
    })
    .join(" \n");
  const relatedNotes = related
    .map((item) => `- Заметка ${item.noteId} (score=${item.score.toFixed(2)})`)
    .join(" \n");

  return `Пользователь написал: ${message}.\nПредложенные действия:\n${summary || "- Нет действий"}.\nПохожие заметки:\n${relatedNotes || "- Нет"}.\nСформулируй короткий ответ с упоминанием ключевых шагов.`;
}

function plainPreview(markdown: string) {
  return markdown.replace(/[#*_`\-]/g, "").slice(0, 80);
}
