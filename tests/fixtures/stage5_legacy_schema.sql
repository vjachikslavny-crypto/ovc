-- Schema-only fixture captured from the pre-Stage-5 manual SQLite DB. No user data.
CREATE TABLE action_log (
	id VARCHAR NOT NULL,
	hash VARCHAR NOT NULL,
	payload TEXT NOT NULL,
	created_at DATETIME NOT NULL,
	CONSTRAINT pk_action_log PRIMARY KEY (id),
	CONSTRAINT uq_action_log_hash UNIQUE (hash)
);
CREATE TABLE audit_logs (
	id VARCHAR NOT NULL,
	user_id VARCHAR,
	event VARCHAR NOT NULL,
	ip VARCHAR,
	user_agent VARCHAR,
	metadata JSON,
	created_at DATETIME NOT NULL,
	CONSTRAINT pk_audit_logs PRIMARY KEY (id),
	CONSTRAINT fk_audit_logs_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL
);
CREATE TABLE files (
	id VARCHAR NOT NULL,
	note_id VARCHAR,
	user_id VARCHAR,
	kind VARCHAR NOT NULL,
	mime VARCHAR NOT NULL,
	filename VARCHAR NOT NULL,
	size INTEGER NOT NULL,
	path_original VARCHAR NOT NULL,
	path_preview VARCHAR,
	path_doc_html VARCHAR,
	path_waveform VARCHAR,
	path_slides_json VARCHAR,
	path_slides_dir VARCHAR,
	path_excel_summary VARCHAR,
	path_excel_charts_json VARCHAR,
	path_excel_charts_dir VARCHAR,
	path_excel_chart_sheets_json VARCHAR,
	excel_charts_pages_keep TEXT,
	excel_default_sheet VARCHAR,
	path_video_original VARCHAR,
	path_video_poster VARCHAR,
	path_code_original VARCHAR,
	path_markdown_raw VARCHAR,
	hash_sha256 VARCHAR,
	width INTEGER,
	height INTEGER,
	pages INTEGER,
	duration FLOAT,
	words INTEGER,
	slides_count INTEGER,
	video_duration FLOAT,
	video_width INTEGER,
	video_height INTEGER,
	video_mime VARCHAR,
	code_language VARCHAR,
	code_line_count INTEGER,
	markdown_line_count INTEGER,
	created_at DATETIME NOT NULL, upload_op_id VARCHAR, revision INTEGER DEFAULT 0, tombstone BOOLEAN DEFAULT 0, updated_at DATETIME,
	CONSTRAINT pk_files PRIMARY KEY (id),
	CONSTRAINT fk_files_note_id_notes FOREIGN KEY(note_id) REFERENCES notes (id) ON DELETE SET NULL,
	CONSTRAINT fk_files_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE TABLE group_preferences (
	"key" VARCHAR NOT NULL,
	label VARCHAR NOT NULL,
	color VARCHAR NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	CONSTRAINT pk_group_preferences PRIMARY KEY ("key")
);
CREATE TABLE messages (
	id VARCHAR NOT NULL,
	role VARCHAR NOT NULL,
	text TEXT NOT NULL,
	created_at DATETIME NOT NULL, user_id VARCHAR, note_id VARCHAR, mode VARCHAR,
	CONSTRAINT pk_messages PRIMARY KEY (id)
);
CREATE TABLE note_chunks (
	id VARCHAR NOT NULL,
	note_id VARCHAR NOT NULL,
	idx FLOAT NOT NULL,
	text TEXT NOT NULL,
	embedding TEXT NOT NULL,
	CONSTRAINT pk_note_chunks PRIMARY KEY (id),
	CONSTRAINT fk_note_chunks_note_id_notes FOREIGN KEY(note_id) REFERENCES notes (id) ON DELETE CASCADE
);
CREATE TABLE note_links (
	id VARCHAR NOT NULL,
	from_id VARCHAR NOT NULL,
	to_id VARCHAR NOT NULL,
	reason VARCHAR,
	confidence FLOAT,
	created_at DATETIME NOT NULL,
	CONSTRAINT pk_note_links PRIMARY KEY (id),
	CONSTRAINT uq_note_links UNIQUE (from_id, to_id, reason),
	CONSTRAINT fk_note_links_from_id_notes FOREIGN KEY(from_id) REFERENCES notes (id) ON DELETE CASCADE,
	CONSTRAINT fk_note_links_to_id_notes FOREIGN KEY(to_id) REFERENCES notes (id) ON DELETE CASCADE
);
CREATE TABLE note_sources (
	id VARCHAR NOT NULL,
	note_id VARCHAR NOT NULL,
	source_id VARCHAR NOT NULL,
	relevance FLOAT,
	CONSTRAINT pk_note_sources PRIMARY KEY (id),
	CONSTRAINT fk_note_sources_note_id_notes FOREIGN KEY(note_id) REFERENCES notes (id) ON DELETE CASCADE,
	CONSTRAINT fk_note_sources_source_id_sources FOREIGN KEY(source_id) REFERENCES sources (id) ON DELETE CASCADE
);
CREATE TABLE note_tags (
	id VARCHAR NOT NULL,
	note_id VARCHAR NOT NULL,
	tag VARCHAR NOT NULL,
	weight FLOAT,
	CONSTRAINT pk_note_tags PRIMARY KEY (id),
	CONSTRAINT uq_note_tags UNIQUE (note_id, tag),
	CONSTRAINT fk_note_tags_note_id_notes FOREIGN KEY(note_id) REFERENCES notes (id) ON DELETE CASCADE
);
CREATE TABLE notes (
	id VARCHAR NOT NULL,
	user_id VARCHAR,
	title VARCHAR NOT NULL,
	style_theme VARCHAR NOT NULL,
	layout_hints TEXT NOT NULL,
	blocks_json TEXT NOT NULL,
	passport_json TEXT NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	revision INTEGER NOT NULL,
	tombstone BOOLEAN NOT NULL,
	client_origin VARCHAR,
	last_client_ts DATETIME,
	CONSTRAINT pk_notes PRIMARY KEY (id),
	CONSTRAINT fk_notes_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE TABLE refresh_tokens (
	id VARCHAR NOT NULL,
	user_id VARCHAR NOT NULL,
	token_hash VARCHAR NOT NULL,
	created_at DATETIME NOT NULL,
	expires_at DATETIME NOT NULL,
	rotated_at DATETIME,
	revoked_at DATETIME,
	fingerprint_hash VARCHAR,
	ip VARCHAR,
	user_agent VARCHAR,
	CONSTRAINT pk_refresh_tokens PRIMARY KEY (id),
	CONSTRAINT fk_refresh_tokens_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE TABLE sources (
	id VARCHAR NOT NULL,
	url TEXT NOT NULL,
	domain VARCHAR NOT NULL,
	title TEXT NOT NULL,
	summary TEXT NOT NULL,
	published_at VARCHAR,
	CONSTRAINT pk_sources PRIMARY KEY (id),
	CONSTRAINT uq_sources_url UNIQUE (url)
);
CREATE TABLE sync_applied_ops (
                        op_id VARCHAR PRIMARY KEY,
                        user_id VARCHAR NOT NULL,
                        entity_type VARCHAR NOT NULL,
                        entity_id VARCHAR,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
CREATE TABLE sync_change_log (
                        id VARCHAR PRIMARY KEY,
                        user_id VARCHAR NOT NULL,
                        entity_type VARCHAR NOT NULL,
                        entity_id VARCHAR NOT NULL,
                        op_type VARCHAR NOT NULL,
                        server_version INTEGER NOT NULL DEFAULT 0,
                        deleted BOOLEAN NOT NULL DEFAULT 0,
                        payload_json TEXT NOT NULL DEFAULT '{}',
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
CREATE TABLE sync_conflicts (
	id VARCHAR NOT NULL,
	local_note_id VARCHAR,
	remote_note_id VARCHAR,
	kind VARCHAR NOT NULL,
	payload_json TEXT NOT NULL,
	created_at DATETIME NOT NULL,
	CONSTRAINT pk_sync_conflicts PRIMARY KEY (id),
	CONSTRAINT fk_sync_conflicts_local_note_id_notes FOREIGN KEY(local_note_id) REFERENCES notes (id) ON DELETE SET NULL
);
CREATE TABLE sync_note_map (
	local_note_id VARCHAR NOT NULL,
	remote_note_id VARCHAR NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL, remote_version INTEGER DEFAULT 0, last_server_ts DATETIME,
	CONSTRAINT pk_sync_note_map PRIMARY KEY (local_note_id),
	CONSTRAINT fk_sync_note_map_local_note_id_notes FOREIGN KEY(local_note_id) REFERENCES notes (id) ON DELETE CASCADE
);
CREATE TABLE sync_outbox (
	id VARCHAR NOT NULL,
	op_type VARCHAR NOT NULL,
	note_id VARCHAR,
	payload_json TEXT NOT NULL,
	status VARCHAR NOT NULL,
	tries INTEGER NOT NULL,
	last_error TEXT,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL, user_id VARCHAR, entity_type VARCHAR, entity_id VARCHAR, dependency_key VARCHAR, next_retry_at DATETIME,
	CONSTRAINT pk_sync_outbox PRIMARY KEY (id),
	CONSTRAINT fk_sync_outbox_note_id_notes FOREIGN KEY(note_id) REFERENCES notes (id) ON DELETE SET NULL
);
CREATE TABLE sync_state (
                        user_id VARCHAR PRIMARY KEY,
                        last_pull_since DATETIME,
                        last_success_at DATETIME,
                        last_error TEXT,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
CREATE TABLE users (
	id VARCHAR NOT NULL,
	username VARCHAR NOT NULL,
	email VARCHAR,
	password_hash VARCHAR NOT NULL,
	display_name VARCHAR,
	avatar_url VARCHAR,
	failed_login_count INTEGER NOT NULL,
	locked_until DATETIME,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	is_active BOOLEAN NOT NULL,
	role VARCHAR NOT NULL, supabase_id VARCHAR, email_verified_at DATETIME,
	CONSTRAINT pk_users PRIMARY KEY (id)
);
CREATE INDEX idx_files_upload_op_id ON files(upload_op_id);
CREATE INDEX idx_sync_applied_ops_entity ON sync_applied_ops(entity_type, entity_id);
CREATE INDEX idx_sync_applied_ops_user ON sync_applied_ops(user_id);
CREATE INDEX idx_sync_change_log_entity ON sync_change_log(entity_type, entity_id);
CREATE INDEX idx_sync_change_log_user_created ON sync_change_log(user_id, created_at);
CREATE INDEX idx_sync_outbox_dependency_key ON sync_outbox(dependency_key);
CREATE INDEX idx_sync_outbox_entity_id ON sync_outbox(entity_id);
CREATE INDEX idx_sync_outbox_entity_type ON sync_outbox(entity_type);
CREATE INDEX idx_sync_outbox_next_retry_at ON sync_outbox(next_retry_at);
CREATE INDEX idx_sync_outbox_user_id ON sync_outbox(user_id);
CREATE UNIQUE INDEX idx_users_supabase_id ON users(supabase_id);
CREATE INDEX ix_audit_logs_created_at ON audit_logs (created_at);
CREATE INDEX ix_audit_logs_event ON audit_logs (event);
CREATE INDEX ix_audit_logs_user_id ON audit_logs (user_id);
CREATE INDEX ix_files_user_id ON files (user_id);
CREATE INDEX ix_notes_user_id ON notes (user_id);
CREATE INDEX ix_refresh_tokens_expires_at ON refresh_tokens (expires_at);
CREATE INDEX ix_refresh_tokens_token_hash ON refresh_tokens (token_hash);
CREATE INDEX ix_refresh_tokens_user_id ON refresh_tokens (user_id);
CREATE INDEX ix_sync_conflicts_created_at ON sync_conflicts (created_at);
CREATE INDEX ix_sync_conflicts_local_note_id ON sync_conflicts (local_note_id);
CREATE INDEX ix_sync_conflicts_remote_note_id ON sync_conflicts (remote_note_id);
CREATE UNIQUE INDEX ix_sync_note_map_remote_note_id ON sync_note_map (remote_note_id);
CREATE INDEX ix_sync_outbox_created_at ON sync_outbox (created_at);
CREATE INDEX ix_sync_outbox_note_id ON sync_outbox (note_id);
CREATE INDEX ix_sync_outbox_op_type ON sync_outbox (op_type);
CREATE INDEX ix_sync_outbox_status ON sync_outbox (status);
CREATE UNIQUE INDEX ix_users_email ON users (email);
CREATE UNIQUE INDEX ix_users_username ON users (username);
