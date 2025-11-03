import { DraftAction } from "@/lib/actions";
import { plainTextPreview } from "@/lib/markdown";

export type AgentContext = {
  notes: Array<{ id: string; title: string; contentMd: string }>;
  noteId?: string;
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
    actions.push({
      type: "update_note",
      id: targetNote.id,
      patch_md: "## Сводка\n\n- Ключевые факты\n- Новые выводы",
      position: "append"
    });
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

  if (hasSourceIntent(text)) {
    const topic = titleForCreate ?? targetNote?.title ?? inferTopicFromMessage(text);
    const sources = await mockWebSearch(topic);
    if (targetNote) {
      for (const item of sources) {
        actions.push({
          type: "add_source",
          note_id: targetNote.id,
          source: item
        });
      }
    }
  }

  if (targetNote) {
    const linkSuggestions = suggestLinks(targetNote, notes);
    actions.push(...linkSuggestions);
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

const SOURCE_INTENT_REGEXES = [
  /найд[аиоё]?(?:те)?/i,
  /поищи?(?:те)?/i,
  /подбер[еи](?:те)?/i,
  /добав(?:ь|ьте).*(инф|инфо|данн)/i,
  /узнай(?:те)?/i,
  /собер(?:и|ите)/i,
  /проверь(?:те)?/i,
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

function hasSourceIntent(message: string) {
  const normalized = message.toLowerCase();
  const hasKeyword = INTERNET_KEYWORDS.some((keyword) => normalized.includes(keyword));
  const hasDirectPhrase = SOURCE_TRIGGERS.some((trigger) => normalized.includes(trigger));
  const hasVerb = SOURCE_INTENT_REGEXES.some((regex) => regex.test(normalized));
  const mentionsInfo =
    normalized.includes("инфо") ||
    normalized.includes("информац") ||
    normalized.includes("данн") ||
    normalized.includes("ссылк");
  return hasDirectPhrase || (hasKeyword && (hasVerb || mentionsInfo));
}

type QuickLogResult = {
  actions: DraftAction[];
};

const PREPOSITIONS = new Set(["на", "в", "по", "для", "о", "об", "от", "про"]);
const STOP_WORDS = new Set([
  "заметка",
  "заметку",
  "заметке",
  "заметок",
  "note",
  "notes",
  "запись",
  "записи",
  "лог",
  "журнал",
  "заметочка"
]);

function detectQuickLogIntent(message: string, notes: AgentContext["notes"]): QuickLogResult | null {
  const text = message.trim();
  if (!text) return null;
  if (text.length < 10) return null;
  if (/[?]/.test(text)) return null;
  const lower = text.toLowerCase();
  if (CREATE_TRIGGERS.some((trigger) => lower.includes(trigger))) return null;
  if (UPDATE_TRIGGERS.some((trigger) => lower.includes(trigger))) return null;

  const hasNumericContext = /\d/.test(text) || /(сегодня|завтра|вчера|понедельник|вторник|среду|четверг|пятницу|субботу|воскресенье)/i.test(text);
  if (!hasNumericContext) return null;

  const tokens = text.split(/\s+/).filter(Boolean);
  if (tokens.length < 2) return null;

  const baseTokens: string[] = [];
  for (const token of tokens) {
    if (PREPOSITIONS.has(token.toLowerCase())) break;
    baseTokens.push(token);
  }
  if (baseTokens.length === 0) baseTokens.push(tokens[0]);

  const baseTitle = tidyTitle(baseTokens.join(" "));
  if (!baseTitle) return null;

  const remainderTokens = tokens.slice(baseTokens.length);
  const remainder = remainderTokens.join(" ");

  const locationMatch = text.match(/(?:на|в)\s+[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9\s-]+/u);
  const locationText = locationMatch ? tidyTitle(locationMatch[0]) : "";

  const dateMatch = text.match(/\d{1,2}[./]\d{1,2}[./]\d{2,4}/);
  const timeMatch = text.match(/(?:лучшее\s+время|время)\s+([0-9]+(?:[.,][0-9]+)?\s*(?:с|сек|секунд))/i);

  let detailPart = remainder;
  if (dateMatch && detailPart.includes(dateMatch[0])) {
    detailPart = detailPart.slice(0, detailPart.indexOf(dateMatch[0]));
  }
  if (timeMatch && detailPart.includes(timeMatch[0])) {
    detailPart = detailPart.slice(0, detailPart.indexOf(timeMatch[0]));
  }
  detailPart = detailPart.replace(/^\W+/, "").trim();

  const childTitleCandidates: string[] = [baseTitle];
  if (locationText) {
    childTitleCandidates.push(locationText);
  } else if (detailPart) {
    childTitleCandidates.push(detailPart);
  }
  const childTitle = tidyTitle(childTitleCandidates.join(" "));

  const detailLines: string[] = [];
  if (locationText) {
    detailLines.push(`- Локация: ${locationText}`);
  }
  if (dateMatch) {
    detailLines.push(`- Дата: ${dateMatch[0]}`);
  }
  if (timeMatch) {
    detailLines.push(`- Время: ${timeMatch[1]}`);
  }
  detailLines.push(`- Детали: ${text}`);

  const childContent = [
    `# ${childTitle}`,
    `[[${baseTitle}]]`,
    detailLines.join("\n"),
    "## Источник",
    `> ${text}`
  ].join("\n\n");

  const actions: DraftAction[] = [];

  const baseNote = notes.find((note) => note.title.toLowerCase() === baseTitle.toLowerCase());
  if (!baseNote) {
    actions.push({
      type: "create_note",
      title: baseTitle,
      content_md: `# ${baseTitle}\n\n## Журнал событий\n- [[${childTitle}]]\n\n## Идеи\n- Добавьте подробности по мероприятию.`
    });
  } else {
    actions.push({
      type: "update_note",
      id: baseNote.id,
      patch_md: `- [[${childTitle}]] — ${new Date().toLocaleDateString("ru-RU")}`,
      position: "append"
    });
  }

  actions.push({
    type: "create_note",
    title: childTitle,
    content_md: childContent
  });

  return { actions };
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

  for (const note of notes) {
    const comparableTitle = normalizeForMatch(note.title);
    if (!comparableTitle) continue;

    let score = 0;
    if (matchableMessage.includes(comparableTitle)) {
      score = 1;
    } else {
      const titleTokens = tokenize(comparableTitle).filter((token) => !STOP_WORDS.has(token));
      const effectiveTitleTokens = titleTokens.length > 0 ? titleTokens : tokenize(comparableTitle);

      const intersection = effectiveTitleTokens.filter((token) => messageTokens.includes(token));
      if (effectiveTitleTokens.length > 0) {
        score = Math.max(score, intersection.length / effectiveTitleTokens.length);
      }

      const firstToken = effectiveTitleTokens[0];
      if (firstToken && messageTokens.includes(firstToken)) {
        score = Math.max(score, 0.4);
      }

      score = Math.max(score, computeTitleOverlap(comparableTitle, matchableMessage));
    }

    if (!bestMatch || score > bestMatch.score) {
      bestMatch = { note, score };
    }
  }

  if (bestMatch && bestMatch.score >= 0.35) {
    return bestMatch.note;
  }
  return undefined;
}

function inferTopicFromMessage(message: string) {
  const cleaned = message.replace(/(источники|sources|по|about)/gi, "").trim();
  return tidyTitle(cleaned || "новая тема");
}

async function mockWebSearch(topic: string | undefined) {
  const baseTitle = topic ?? "Общая тема";
  const domain = "example.com";
  const today = new Date().toISOString().slice(0, 10);
  return [
    {
      url: `https://${domain}/articles/${encodeURIComponent(baseTitle)}`,
      title: `${baseTitle} — текущие тенденции`,
      domain,
      published_at: today,
      summary: `Подборка свежих фактов и цитат по теме «${baseTitle}».`
    },
    {
      url: `https://${domain}/reports/${encodeURIComponent(baseTitle)}-deep-dive`,
      title: `${baseTitle}: аналитический отчёт`,
      domain,
      published_at: today,
      summary: `Краткое изложение ключевых чисел и прогнозов, связанных с «${baseTitle}».`
    }
  ];
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
