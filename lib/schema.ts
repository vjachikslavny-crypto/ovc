import {
  index,
  integer,
  jsonb,
  pgTable,
  primaryKey,
  real,
  text,
  timestamp,
  uuid,
  uniqueIndex
} from "drizzle-orm/pg-core";
import { vector } from "pgvector/drizzle-orm";

export const notes = pgTable(
  "notes",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    title: text("title").notNull(),
    contentMd: text("content_md").notNull(),
    createdAt: timestamp("created_at", { withTimezone: true })
      .defaultNow()
      .notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true })
      .defaultNow()
      .notNull()
  },
  (table) => ({
    titleIdx: index("notes_title_idx").on(table.title)
  })
);

export const noteChunks = pgTable(
  "note_chunks",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    noteId: uuid("note_id")
      .notNull()
      .references(() => notes.id, { onDelete: "cascade" }),
    idx: integer("idx").notNull(),
    text: text("text").notNull(),
    embedding: vector("embedding", { dimensions: 384 }).notNull()
  },
  (table) => ({
    noteIdx: index("note_chunks_note_idx").on(table.noteId)
  })
);

export const noteLinks = pgTable(
  "note_links",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    fromId: uuid("from_id")
      .notNull()
      .references(() => notes.id, { onDelete: "cascade" }),
    toId: uuid("to_id")
      .notNull()
      .references(() => notes.id, { onDelete: "cascade" }),
    reason: text("reason").notNull(),
    confidence: real("confidence").default(0.5).notNull()
  },
  (table) => ({
    fromIdx: index("note_links_from_idx").on(table.fromId),
    toIdx: index("note_links_to_idx").on(table.toId),
    uniquePair: uniqueIndex("note_links_unique").on(
      table.fromId,
      table.toId,
      table.reason
    )
  })
);

export const noteTags = pgTable(
  "note_tags",
  {
    noteId: uuid("note_id")
      .notNull()
      .references(() => notes.id, { onDelete: "cascade" }),
    tag: text("tag").notNull(),
    weight: real("weight").default(1)
  },
  (table) => ({
    pk: primaryKey({ columns: [table.noteId, table.tag] })
  })
);

export const sources = pgTable(
  "sources",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    url: text("url").notNull(),
    domain: text("domain").notNull(),
    title: text("title").notNull(),
    publishedAt: timestamp("published_at", { mode: "string" }),
    summary: text("summary").notNull()
  },
  (table) => ({
    urlIdx: uniqueIndex("sources_url_unique").on(table.url)
  })
);

export const noteSources = pgTable(
  "note_sources",
  {
    noteId: uuid("note_id")
      .notNull()
      .references(() => notes.id, { onDelete: "cascade" }),
    sourceId: uuid("source_id")
      .notNull()
      .references(() => sources.id, { onDelete: "cascade" }),
    relevance: real("relevance").default(0.5).notNull()
  },
  (table) => ({
    noteSourceIdx: index("note_sources_note_idx").on(table.noteId)
  })
);

export const agentActionLog = pgTable("agent_action_log", {
  hash: text("hash").primaryKey(),
  userId: text("user_id"),
  actionType: text("action_type"),
  createdAt: timestamp("created_at", { withTimezone: true })
    .defaultNow()
    .notNull()
});

export const messages = pgTable("messages", {
  id: uuid("id").defaultRandom().primaryKey(),
  role: text("role").notNull(),
  text: text("text").notNull(),
  meta: jsonb("meta"),
  createdAt: timestamp("created_at", { withTimezone: true })
    .defaultNow()
    .notNull()
});

export const draftActions = pgTable("draft_actions", {
  id: uuid("id").defaultRandom().primaryKey(),
  payload: jsonb("payload").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true })
    .defaultNow()
    .notNull()
});

export const reminders = pgTable("reminders", {
  id: uuid("id").defaultRandom().primaryKey(),
  text: text("text").notNull(),
  dueAt: timestamp("due_at", { withTimezone: true }).notNull(),
  channel: text("channel").notNull(),
  status: text("status").default("pending").notNull()
});

export type Note = typeof notes.$inferSelect;
export type NoteChunk = typeof noteChunks.$inferSelect;
export type NoteLink = typeof noteLinks.$inferSelect;
export type NoteTag = typeof noteTags.$inferSelect;
export type Source = typeof sources.$inferSelect;
export type Reminder = typeof reminders.$inferSelect;
export type AgentAction = typeof agentActionLog.$inferSelect;
