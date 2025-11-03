CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

CREATE TABLE IF NOT EXISTS notes (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  title TEXT NOT NULL,
  content_md TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS notes_title_idx ON notes USING GIN (to_tsvector('simple', title));

CREATE TABLE IF NOT EXISTS note_chunks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  note_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
  idx INTEGER NOT NULL,
  text TEXT NOT NULL,
  embedding vector(384) NOT NULL
);

CREATE INDEX IF NOT EXISTS note_chunks_note_idx ON note_chunks(note_id);
CREATE INDEX IF NOT EXISTS note_chunks_embedding_idx ON note_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE TABLE IF NOT EXISTS note_links (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  from_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
  to_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
  reason TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0.5
);

CREATE INDEX IF NOT EXISTS note_links_from_idx ON note_links(from_id);
CREATE INDEX IF NOT EXISTS note_links_to_idx ON note_links(to_id);
ALTER TABLE note_links
  ADD CONSTRAINT note_links_unique UNIQUE (from_id, to_id, reason);

CREATE TABLE IF NOT EXISTS note_tags (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  note_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
  tag TEXT NOT NULL,
  weight REAL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS sources (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  url TEXT NOT NULL,
  domain TEXT NOT NULL,
  title TEXT NOT NULL,
  published_at TIMESTAMPTZ,
  summary TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS note_sources (
  note_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
  source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  relevance REAL NOT NULL DEFAULT 0.5
);

ALTER TABLE note_sources
  ADD CONSTRAINT note_sources_pk PRIMARY KEY (note_id, source_id);

CREATE INDEX IF NOT EXISTS note_sources_note_idx ON note_sources(note_id);

CREATE TABLE IF NOT EXISTS messages (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  role TEXT NOT NULL,
  text TEXT NOT NULL,
  meta JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS draft_actions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reminders (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  text TEXT NOT NULL,
  due_at TIMESTAMPTZ NOT NULL,
  channel TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
);
