import { DraftAction } from "@/lib/actions";
import { plainTextPreview } from "@/lib/markdown";
import { tavilySearch } from "@/server/web/tavily";

type SourcePayload = {
  source: {
    url: string;
    title: string;
    domain: string;
    published_at: string | null;
    summary: string;
  };
  noteSummary: string;
  imageUrl?: string | null;
};

export type AgentContext = {
  notes: Array<{ id: string; title: string; contentMd: string }>;
  noteId?: string;
  languages?: string[];
};

export type AgentDraft = {
  reply: string;
  draft: DraftAction[];
};

const CREATE_TRIGGERS = [
  "создай",
  "создать",
  "создайте",
  "сделай заметку",
  "сделайте заметку",
  "новую заметку",
  "запиши",
  "записать",
  "запишите",
  "добавь заметку",
  "добавьте заметку",
  "заведи заметку",
  "создай запись",
  "создать запись",
  "создай заметочку",
  "note down",
  "make a note",
  "create note",
  "add note",
  "log это",
  "логируй"
];

const UPDATE_TRIGGERS = [
  "дополни",
  "дополнить",
  "расширь",
  "расширить",
  "обнови",
  "обновить",
  "добавь",
  "добавьте",
  "допиши",
  "дописать",
  "внеси",
  "внести",
  "редактируй",
  "редактировать",
  "summary",
  "сводка",
  "продолжи",
  "продолжить"
];

const SOURCE_TRIGGERS = [
  "источник",
  "источники",
  "sources",
  "найди",
  "найди в интернете",
  "найди инфо",
  "найди информацию",
  "найди в сети",
  "поищи",
  "поищи в интернете",
  "поищи в сети",
  "проверь в интернете",
  "подбери источники",
  "подбери ссылки",
  "добавь инфу из интернета",
  "веб поиск",
  "web search",
  "search online",
  "find sources",
  "link sources"
];

const LINK_TRIGGERS = [
  "свяжи",
  "связать",
  "добавь связь",
  "добавьте связь",
  "соедини",
  "привяжи",
  "привязать",
  "link",
  "connect",
  "add link",
  "make link",
  "соединить"
];

export async function planAndDraftActions(
  message: string,
  context: AgentContext
): Promise<AgentDraft> {
  const text = message.trim();
  const normalized = text.toLowerCase();
  const matchableText = normalizeForMatch(text);
  const actions: DraftAction[] = [];
  const notes = context.notes ?? [];
  const wantsSources = hasSourceIntent(text);

  const createIntent = extractCreateNoteIntent(text);
  const targetNote = findNoteFromMessage(notes, matchableText, context.noteId);
  const titleForCreate = createIntent?.title ?? null;

  if (createIntent) {
    actions.push({
      type: "create_note",
      title: createIntent.title,
      content_md: buildCreateNoteContent(createIntent.title, createIntent.body, text)
    });
  } else if (
    targetNote &&
    UPDATE_TRIGGERS.some((w) => normalized.includes(w)) &&
    !LINK_TRIGGERS.some((w) => normalized.includes(w))
  ) {
    if (!wantsSources) {
      const summaryPatch = buildSummaryPatch(text, targetNote.title);
      if (summaryPatch) {
        actions.push({
          type: "update_note",
          id: targetNote.id,
          patch_md: summaryPatch,
          position: "append"
        });
      }
    }
  } else if (!targetNote) {
    const quickActions = detectQuickLogIntent(text, notes);
    if (quickActions) {
      actions.push(...quickActions.actions);
    }
  }

  const linkIntent = detectLinkIntent(text, notes);
  if (linkIntent) {
    actions.push(...linkIntent.actions);
  }

  if (wantsSources) {
    const topic = titleForCreate ?? targetNote?.title ?? inferTopicFromMessage(text);
    const sourcePayloads = await fetchWebSources(topic, context.languages);
    if (targetNote && sourcePayloads.length > 0) {
      const infoLines = sourcePayloads.map(({ noteSummary, source, imageUrl }) => {
        let line = `- [${source.title}](${source.url}) — ${noteSummary}`;
        if (imageUrl) {
          line += `\n  ![Изображение по теме](${imageUrl})`;
        }
        return line;
      });
      actions.push({
        type: "update_note",
        id: targetNote.id,
        patch_md: `## Информация из интернета\n${infoLines.join("\n")}`,
        position: "append"
      });
      for (const payload of sourcePayloads) {
        actions.push({
          type: "add_source",
          note_id: targetNote.id,
          source: payload.source
        });
      }
    } else if (targetNote) {
      actions.push({
        type: "update_note",
        id: targetNote.id,
        patch_md: "## Информация из интернета\n- Не удалось найти подходящие материалы. Попробуйте уточнить запрос или выбрать другой язык поиска.",
        position: "append"
      });
    }
  }

  if (targetNote) {
    const linkSuggestions = suggestLinks(targetNote, notes);
    actions.push(...linkSuggestions);
  }

  if (!createIntent && !targetNote && actions.length === 0) {
    const fallback = buildFallbackNoteAction(text);
    if (fallback) {
      actions.push(fallback);
    }
  }

  const reply = craftReply(message, actions, targetNote?.title ?? titleForCreate);
  return { reply, draft: actions };
}

function extractCreateNoteIntent(message: string) {
  const normalized = message.toLowerCase();
  if (!CREATE_TRIGGERS.some((token) => normalized.includes(token))) return null;

  const createPattern =
    /(?:создай(?:те)?|создать|сделай|create|new\s+note)\s*(?:мне|пожалуйста)?\s*(?:новую|эту)?\s*(?:заметку|note)?\s*(.*)/i;
  const match = message.match(createPattern);
  const remainder = match?.[1]?.trim();
  if (!remainder) return null;

  const cleanedRemainder = remainder.replace(/^[\s:–—-]+/, "");

  const delimiters = [":", " - ", " — ", "–", "—"];
  let titlePart = cleanedRemainder;
  let bodyPart = "";

  for (const delimiter of delimiters) {
    if (cleanedRemainder.includes(delimiter)) {
      const [first, ...rest] = cleanedRemainder.split(delimiter);
      titlePart = first;
      bodyPart = rest.join(delimiter).trim();
      break;
    }
  }

  if (!bodyPart) {
    const sentences = cleanedRemainder
      .split(/[\.\n]+/)
      .map((sentence) => sentence.trim())
      .filter(Boolean);
    titlePart = sentences.shift() ?? cleanedRemainder;
    bodyPart = sentences.join(". ").trim();
  }

  const title = tidyTitle(titlePart);
  const body = bodyPart ? bodyPart : buildDefaultBodyFromMessage(message, title);

  if (!title) return null;
  return { title, body };
}

function buildCreateNoteContent(title: string, body: string, originalMessage: string) {
  const sections: string[] = [`# ${title}`];

  if (body) {
    sections.push(formatBodyText(body));
  }

  sections.push(
    "## Следующие шаги\n- [ ] Уточнить детали\n- [ ] Добавить действия или задачи",
    `## Исходный запрос\n> ${originalMessage.trim()}`
  );

  return sections.join("\n\n");
}

function formatBodyText(text: string) {
  const lines = text
    .split(/[\r?\n•]/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (lines.length === 0) return "";

  if (lines.length === 1) {
    return lines[0];
  }

  return lines.map((line) => `- ${line}`).join("\n");
}

function buildDefaultBodyFromMessage(message: string, title: string) {
  const cleaned = message
    .replace(new RegExp(`${escapeRegExp(title)}`, "i"), "")
    .replace(/(?:создай|создать|сделай|create|new\s+note|заметку)/gi, "")
    .trim();
  return cleaned ? cleaned : `Запрос о теме «${title}».`;
}

function escapeRegExp(input: string) {
  return input.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function tidyTitle(raw: string) {
  return compressRepeats(raw)
    .replace(/[.!?*#]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^\w/u, (c) => c.toUpperCase());
}

function normalizeForMatch(input: string) {
  return compressRepeats(
    input
      .toLowerCase()
      .replace(/ё/g, "е")
      .replace(/[^a-zа-я0-9\s]/gi, " ")
  )
    .replace(/\s+/g, " ")
    .trim();
}

function compressRepeats(input: string) {
  return input.replace(/([a-zа-я0-9])\1+/gi, "$1");
}

function tokenize(text: string) {
  return text.split(/\s+/).filter(Boolean);
}

function normalizeToken(token: string) {
  return token.toLowerCase().replace(/[^a-zа-я0-9]/gi, "");
}

function isMeaningfulToken(token: string) {
  const normalized = normalizeToken(token);
  if (!normalized) return false;
  if (/^\d+$/.test(normalized)) return false;
  if (normalized.length < 3) return false;
  return true;
}

function filterMeaningfulTokens(tokens: string[]) {
  return tokens.filter((token) => isMeaningfulToken(token) && !STOP_WORDS.has(token));
}

function buildSummaryPatch(message: string, noteTitle?: string) {
  let cleaned = message.trim();
  cleaned = cleaned.replace(/\b(дополни(?:те)?|обнови(?:ть)?|расширь(?:те)?|сводка|summary|добавь(?:те)?|информац(?:ия|ии|ию)|из\s+интернета|найди(?:те)?|проверь(?:те)?)\b/gi, "");
  if (noteTitle) {
    cleaned = cleaned.replace(new RegExp(escapeRegExp(noteTitle), "gi"), "");
  }
  cleaned = cleaned.replace(/\s+/g, " ").trim();
  if (cleaned.length < 8) return null;

  const sentences = cleaned
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.replace(/[.!?]+$/g, "").trim())
    .filter((sentence) => sentence.length >= 8);

  if (sentences.length === 0) return null;

  const uniqueSentences: string[] = [];
  for (const sentence of sentences) {
    if (!uniqueSentences.some((existing) => existing.toLowerCase() === sentence.toLowerCase())) {
      uniqueSentences.push(sentence);
    }
    if (uniqueSentences.length >= 3) break;
  }

  if (uniqueSentences.length === 0) return null;

  const bullets = uniqueSentences.map((sentence) => `- ${capitalizeSentence(sentence)}`);
  return `## Сводка\n${bullets.join("\n")}`;
}

const SOURCE_INTENT_REGEXES = [
  /найд[аиоё]?(?:те)?/i,
  /поищи?(?:те)?/i,
  /подбер[еи](?:те)?/i,
  /добав(?:ь|ьте).*(инф|инфо|данн)/i,
  /узнай(?:те)?/i,
  /собер(?:и|ите)/i,
  /проверь(?:те)?/i,
  /провер[^\s]*\s+факт/i,
  /провер[^\s]*\s+информ/i,
  /возьми.*из\s+интер/i
];

const INTERNET_KEYWORDS = [
  "интернет",
  "инете",
  "сети",
  "сетев",
  "web",
  "онлайн",
  "online",
  "internet",
  "в интернете",
  "в сети",
  "с интернета"
];

const STRONG_SOURCE_REGEXES = [/провер[^\s]*\s+факт/i, /провер[^\s]*\s+информ/i, /подбер[^\s]*\s+источ/i, /добав(?:ь|ьте).*\bисточ/i];

function hasSourceIntent(message: string) {
  const normalized = message.toLowerCase();
  const hasKeyword = INTERNET_KEYWORDS.some((keyword) => normalized.includes(keyword));
  const hasDirectPhrase = SOURCE_TRIGGERS.some((trigger) => normalized.includes(trigger));
  const hasVerb = SOURCE_INTENT_REGEXES.some((regex) => regex.test(normalized));
  const hasStrongMatch = STRONG_SOURCE_REGEXES.some((regex) => regex.test(normalized));
  const mentionsInfo =
    normalized.includes("инфо") ||
    normalized.includes("информац") ||
    normalized.includes("данн") ||
    normalized.includes("ссылк");
  if (hasDirectPhrase || hasStrongMatch) return true;
  if (hasKeyword && (hasVerb || mentionsInfo)) return true;
  return false;
}

type QuickLogResult = {
  actions: DraftAction[];
};

const PREPOSITIONS = new Set(["на", "в", "по", "для", "о", "об", "от", "про", "с", "со"]);
const STOP_WORDS = new Set([
  "заметка",
  "заметку",
  "заметке",
  "заметок",
  "заметочка",
  "note",
  "notes",
  "запись",
  "записи",
  "лог",
  "журнал",
  "на",
  "в",
  "по",
  "для",
  "о",
  "об",
  "от",
  "про",
  "с",
  "со",
  "и",
  "во",
  "из",
  "как",
  "что",
  "это",
  "про",
  "по"
]);
const CONTEXT_KEYWORDS = [
  "лекция",
  "урок",
  "семинар",
  "встреча",
  "митап",
  "занятие",
  "конспект",
  "проект",
  "работа",
  "ежедневник",
  "тренировка",
  "заезд",
  "турнир",
  "презентация",
  "обсуждение",
  "тема",
  "курс",
  "практика",
  "обзор",
  "выпуск",
  "сессия"
];

function detectQuickLogIntent(message: string, notes: AgentContext["notes"]): QuickLogResult | null {
  const text = message.trim();
  if (!text) return null;
  if (text.length < 10) return null;
  if (/[?]/.test(text)) return null;
  const lower = text.toLowerCase();
  if (CREATE_TRIGGERS.some((trigger) => lower.includes(trigger))) return null;
  if (UPDATE_TRIGGERS.some((trigger) => lower.includes(trigger))) return null;

  const hasDate = /\d{1,2}[./]\d{1,2}[./]\d{2,4}/.test(text) || /(сегодня|завтра|вчера)/i.test(text);
  const hasKeywordContext = CONTEXT_KEYWORDS.some((keyword) => lower.includes(keyword));
  const hasActionVerb = /(делали|прошли|разбирали|считали|обсуждали|тренировались|работали|изучали)/i.test(text);
  if (!(hasKeywordContext || (hasDate && hasActionVerb))) return null;

  const sentenceSplitter = /[.!?]+/;
  const sentences = text
    .split(sentenceSplitter)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
  if (sentences.length === 0) return null;

  const baseSentence = sentences[0];
  const detailSentence = sentences.slice(1).join(". ").trim();

  const baseTitle = buildBaseTitle(baseSentence);
  if (!baseTitle) return null;

  const dateMatch = text.match(/\d{1,2}[./]\d{1,2}[./]\d{2,4}/);
  const timeMatch = text.match(/(?:лучшее\s+время|время)\s+([0-9]+(?:[.,][0-9]+)?\s*(?:с|сек|секунд|мин))/i);
  const locationMatch = text.match(/(?:на|в)\s+[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9\s-]+/u);
  const locationText = locationMatch ? tidyTitle(locationMatch[0]) : "";

  const subTopic = extractSubTopic(detailSentence) || extractSubTopic(baseSentence) || locationText;
  const childTitle = tidyTitle(
    subTopic ? `${baseTitle} · ${subTopic}` : `${baseTitle} · Запись ${new Date().toLocaleDateString("ru-RU")}`
  );

  const detailBlocks: string[] = [];
  if (detailSentence) {
    detailBlocks.push(detailSentence);
  }
  if (locationText) {
    detailBlocks.push(`Локация: ${locationText}`);
  }
  if (dateMatch) {
    detailBlocks.push(`Дата: ${dateMatch[0]}`);
  }
  if (timeMatch) {
    detailBlocks.push(`Время: ${timeMatch[1]}`);
  }

  const detailMarkdown =
    detailBlocks.length > 0
      ? detailBlocks.map((block) => `- ${block}`).join("\n")
      : "- Детали: уточнить события и выводы";

  const linkageLine = `Связано с [[${baseTitle}]]`;
  const childContent = [linkageLine, detailMarkdown, `> ${text}`].join("\n\n");

  const actions: DraftAction[] = [];

  const baseMatches = findBestNoteMatches(baseTitle, notes);
  const bestMatch = baseMatches[0];

  if (!bestMatch || bestMatch.score < 0.35) {
    actions.push({
      type: "create_note",
      title: baseTitle,
      content_md: `[[${childTitle}]]\n\n- Дополнить содержание встречи.`
    });
  } else if (bestMatch.score >= 0.6) {
    actions.push({
      type: "update_note",
      id: bestMatch.note.id,
      patch_md: `- [[${childTitle}]] — ${new Date().toLocaleDateString("ru-RU")}`,
      position: "append"
    });
  } else {
    return null;
  }

  actions.push({
    type: "create_note",
    title: childTitle,
    content_md: childContent
  });

  return { actions };
}

function buildBaseTitle(sentence: string) {
  const words = sentence.split(/\s+/).filter(Boolean);
  const meaningful = words
    .filter((word) => isMeaningfulToken(word) && !STOP_WORDS.has(normalizeToken(word)))
    .slice(0, 6);
  if (meaningful.length === 0) return tidyTitle(sentence);
  return tidyTitle(meaningful.join(" "));
}

function extractSubTopic(text: string) {
  if (!text) return null;
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (!cleaned) return null;

  const themeDirectMatch = cleaned.match(/тема\s+([^.,;]+)/i);
  if (themeDirectMatch?.[1]) {
    return tidyTitle(themeDirectMatch[1]);
  }

  const themeMatch = cleaned.match(/по\s+теме\s+([^.,;]+)/i);
  if (themeMatch?.[1]) {
    return tidyTitle(themeMatch[1]);
  }

  const aboutMatch = cleaned.match(/(?:про|об|о)\s+([^.,;]+)/i);
  if (aboutMatch?.[1]) {
    return tidyTitle(aboutMatch[1]);
  }

  const capitalMatch = cleaned.match(/([А-ЯЁA-Z][^.,;]+)/);
  if (capitalMatch?.[1]) {
    const candidate = tidyTitle(capitalMatch[1]);
    if (candidate && candidate.length <= 60) {
      return candidate;
    }
  }

  const tokens = filterMeaningfulTokens(tokenize(normalizeForMatch(cleaned)));
  if (tokens.length === 0) return null;
  return tidyTitle(tokens.slice(0, Math.min(tokens.length, 3)).join(" "));
}

function findBestNoteMatches(title: string, notes: AgentContext["notes"]) {
  const matchableTitle = normalizeForMatch(title);
  const titleTokens = filterMeaningfulTokens(tokenize(matchableTitle));
  return notes
    .map((note) => {
      const normalized = normalizeForMatch(note.title);
      const noteTokens = filterMeaningfulTokens(tokenize(normalized));
      const intersection = noteTokens.filter((token) => titleTokens.includes(token));
      const overlap = noteTokens.length > 0 ? intersection.length / noteTokens.length : 0;
      const secondary = computeTitleOverlap(normalized, matchableTitle);
      return { note, score: Math.max(overlap, secondary) };
    })
    .sort((a, b) => b.score - a.score);
}

function capitalizeSentence(input: string) {
  if (!input) return "";
  return input[0].toUpperCase() + input.slice(1);
}

function buildFallbackNoteAction(message: string): DraftAction | null {
  const cleaned = message.trim();
  if (cleaned.length < 15) return null;

  const sentences = cleaned
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
  if (sentences.length === 0) return null;

  const title = buildBaseTitle(sentences[0]);
  if (!title) return null;

  const body = sentences.join(" ");
  const bulletSummary = sentences.slice(0, 4).map((sentence) => `- ${capitalizeSentence(sentence)}`);

  const contentParts = [body];
  if (bulletSummary.length > 0) {
    contentParts.push(bulletSummary.join("\n"));
  }

  return {
    type: "create_note",
    title,
    content_md: contentParts.join("\n\n")
  };
}

type LinkIntentResult = {
  actions: DraftAction[];
};

function detectLinkIntent(message: string, notes: AgentContext["notes"]): LinkIntentResult | null {
  const normalized = message.toLowerCase();
  if (!LINK_TRIGGERS.some((token) => normalized.includes(token))) return null;

  const matches = notes
    .map((note) => {
      const idx = normalized.indexOf(note.title.toLowerCase());
      return idx === -1 ? null : { note, index: idx };
    })
    .filter((entry): entry is { note: AgentContext["notes"][number]; index: number } => Boolean(entry))
    .sort((a, b) => a.index - b.index);

  const uniqueNotes: Array<AgentContext["notes"][number]> = [];
  for (const { note } of matches) {
    if (!uniqueNotes.some((existing) => existing.id === note.id)) {
      uniqueNotes.push(note);
    }
  }

  if (uniqueNotes.length < 2) return null;

  const fromNote = uniqueNotes[0];
  const toNote = uniqueNotes[1];

  return {
    actions: [
      {
        type: "add_link",
        from_id: fromNote.id,
        to_title: toNote.title,
        reason: "user_request",
        confidence: 0.99
      }
    ]
  };
}

function findNoteFromMessage(
  notes: AgentContext["notes"],
  matchableMessage: string,
  fallbackId?: string
) {
  if (fallbackId) {
    const match = notes.find((note) => note.id === fallbackId);
    if (match) return match;
  }

  let bestMatch: { note: AgentContext["notes"][number]; score: number } | null = null;
  const messageTokens = tokenize(matchableMessage);
  const meaningfulMessageTokens = filterMeaningfulTokens(messageTokens);

  for (const note of notes) {
    const comparableTitle = normalizeForMatch(note.title);
    if (!comparableTitle) continue;

    let score = 0;
    if (matchableMessage.includes(comparableTitle)) {
      score = 1;
    } else {
      const titleTokens = tokenize(comparableTitle);
      const meaningfulTitleTokens = filterMeaningfulTokens(titleTokens);
      const effectiveTitleTokens =
        meaningfulTitleTokens.length > 0 ? meaningfulTitleTokens : titleTokens;

      const intersection = effectiveTitleTokens.filter((token) =>
        meaningfulMessageTokens.includes(token)
      );
      if (effectiveTitleTokens.length > 0) {
        score = Math.max(score, intersection.length / effectiveTitleTokens.length);
      }

      const firstToken = effectiveTitleTokens[0];
      if (firstToken && meaningfulMessageTokens.includes(firstToken)) {
        score = Math.max(score, 0.4);
      }

      score = Math.max(score, computeTitleOverlap(comparableTitle, matchableMessage));
    }

    if (!bestMatch || score > bestMatch.score) {
      bestMatch = { note, score };
    }
  }

  if (bestMatch && bestMatch.score >= 0.55) {
    return bestMatch.note;
  }
  return undefined;
}

function inferTopicFromMessage(message: string) {
  const cleaned = message.replace(/(источники|sources|по|about)/gi, "").trim();
  return tidyTitle(cleaned || "новая тема");
}

async function fetchWebSources(topic: string | undefined, languages?: string[]): Promise<SourcePayload[]> {
  const query = topic?.trim();
  if (!query) return [];

  const hasCyrillic = /[а-яё]/i.test(query);
  const hasLatin = /[a-z]/i.test(query);
  const baseLanguages = languages && languages.length > 0 ? [...languages] : [];
  if (hasCyrillic && !baseLanguages.includes("ru")) {
    baseLanguages.push("ru");
  }
  if (hasLatin && !baseLanguages.includes("en")) {
    baseLanguages.push("en");
  }
  if (baseLanguages.length === 0) {
    baseLanguages.push("ru", "en");
  }

  const uniqueLanguages = Array.from(new Set(baseLanguages));

  const results = await tavilySearch(query, 2, { languages: uniqueLanguages });
  if (results.length === 0) {
    console.warn("Tavily returned no results for query", query);
    return [];
  }
  const fallbackDate = new Date().toISOString().slice(0, 10);

  return results.map((item) => {
    const rawText = item.content || item.summary || item.description || "";
    const noteSummary = buildWebSummary(rawText, query);
    const tableSummaryParts = [noteSummary];
    if (item.image_url) {
      tableSummaryParts.push(`![Изображение по теме](${item.image_url})`);
    }
    return {
      source: {
        url: item.url,
        title: item.title,
        domain: item.domain,
        published_at: item.published_at ?? fallbackDate,
        summary: tableSummaryParts.join("\n\n")
      },
      noteSummary,
      imageUrl: item.image_url ?? null
    };
  });
}

function buildWebSummary(text: string, fallbackTopic: string) {
  const cleaned = text
    .replace(/\s+/g, " ")
    .replace(/\[[^\]]*]/g, "")
    .trim();

  if (!cleaned) {
    return `Ключевые факты по теме «${fallbackTopic}».`;
  }

  const sentences = cleaned
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter((sentence) => sentence.length >= 20);

  if (sentences.length === 0) {
    return cleaned.length > 160 ? `${cleaned.slice(0, 157)}…` : cleaned;
  }

  const targetLength = Math.min(700, Math.max(200, Math.floor(cleaned.length / 4)));
  let summary = "";
  for (const sentence of sentences) {
    const appended = summary ? `${summary} ${sentence}` : sentence;
    summary = appended;
    if (summary.length >= targetLength) {
      break;
    }
  }

  if (summary.length < targetLength && cleaned.length > targetLength) {
    summary = cleaned.slice(0, targetLength + 50).replace(/\s+[^\s]*$/, "").trim();
    summary = `${summary}…`;
  }

  return summary || sentences[0];
}

function suggestLinks(
  anchor: { id: string; title: string; contentMd: string },
  notes: AgentContext["notes"]
): DraftAction[] {
  const actions: DraftAction[] = [];
  for (const candidate of notes) {
    if (candidate.id === anchor.id) continue;
    if (candidate.title === anchor.title) continue;
    const overlap = computeTitleOverlap(anchor.title, candidate.title);
    if (overlap >= 0.45) {
      actions.push({
        type: "add_link",
        from_id: anchor.id,
        to_title: candidate.title,
        reason: "semantic",
        confidence: Number(overlap.toFixed(2))
      });
    }
  }
  return actions.slice(0, 3);
}

function computeTitleOverlap(a: string, b: string) {
  const wordsA = new Set(a.toLowerCase().split(/\s+/).filter(Boolean));
  const wordsB = new Set(b.toLowerCase().split(/\s+/).filter(Boolean));
  if (wordsA.size === 0 || wordsB.size === 0) return 0;
  let intersection = 0;
  for (const word of wordsA) {
    if (wordsB.has(word)) intersection += 1;
  }
  return intersection / Math.max(wordsA.size, wordsB.size);
}

function craftReply(message: string, actions: DraftAction[], focus?: string | null) {
  const intro = focus
    ? `Держу в голове заметку «${focus}».`
    : "Я готов расширить твою базу знаний.";
  if (actions.length === 0) {
    return `${intro} Пока вижу это сообщение как контекст, давай уточним следующую задачу.`;
  }

  const summary = actions.map((action) => describeAction(action)).join("; ");
  return `${intro} Предлагаю шаги: ${summary}. Готов применить, как только скажешь.`;
}

function describeAction(action: DraftAction) {
  switch (action.type) {
    case "create_note":
      return `создать заметку «${action.title}»`;
    case "update_note":
      return `дописать блок "${plainTextPreview(action.patch_md, 40)}"`;
    case "add_link":
      return `связать с «${action.to_title}»`;
    case "add_source":
      return `добавить источник ${action.source.domain}`;
    case "add_tag":
      return `пометить тегом ${action.tag}`;
    default:
      return action.type;
  }
}
