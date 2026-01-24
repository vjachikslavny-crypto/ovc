from app.db.models import Base
from app.models.user import User  # noqa: F401
from app.models.session import RefreshToken  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
from app.db.session import engine
from sqlalchemy import text


def upgrade() -> None:
    # OVC: audio - добавляем колонку path_waveform в таблицу files, если её нет
    with engine.begin() as conn:
        result = conn.execute(text("PRAGMA table_info(files)"))
        columns = [row[1] for row in result.fetchall()]

        if 'path_waveform' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN path_waveform VARCHAR"))
                print("Added path_waveform column to files table")
            except Exception as e:
                print(f"Error adding path_waveform column: {e}")

        if 'path_doc_html' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN path_doc_html VARCHAR"))
                print("Added path_doc_html column to files table")
            except Exception as e:
                print(f"Error adding path_doc_html column: {e}")

        if 'path_slides_json' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN path_slides_json VARCHAR"))
                print("Added path_slides_json column to files table")
            except Exception as e:
                print(f"Error adding path_slides_json column: {e}")

        if 'path_slides_dir' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN path_slides_dir VARCHAR"))
                print("Added path_slides_dir column to files table")
            except Exception as e:
                print(f"Error adding path_slides_dir column: {e}")

        if 'path_excel_summary' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN path_excel_summary VARCHAR"))
                print("Added path_excel_summary column to files table")
            except Exception as e:
                print(f"Error adding path_excel_summary column: {e}")

        if 'excel_default_sheet' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN excel_default_sheet VARCHAR"))
                print("Added excel_default_sheet column to files table")
            except Exception as e:
                print(f"Error adding excel_default_sheet column: {e}")

        # Проверяем, существует ли колонка duration (для аудио)
        if 'duration' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN duration FLOAT"))
                print("Added duration column to files table")
            except Exception as e:
                print(f"Error adding duration column: {e}")

        if 'words' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN words INTEGER"))
                print("Added words column to files table")
            except Exception as e:
                print(f"Error adding words column: {e}")

        if 'slides_count' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN slides_count INTEGER"))
                print("Added slides_count column to files table")
            except Exception as e:
                print(f"Error adding slides_count column: {e}")

        # OVC: excel - добавляем поля для диаграмм Excel
        if 'path_excel_charts_json' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN path_excel_charts_json VARCHAR"))
                print("Added path_excel_charts_json column to files table")
            except Exception as e:
                print(f"Error adding path_excel_charts_json column: {e}")

        if 'path_excel_charts_dir' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN path_excel_charts_dir VARCHAR"))
                print("Added path_excel_charts_dir column to files table")
            except Exception as e:
                print(f"Error adding path_excel_charts_dir column: {e}")

        # OVC: excel - добавляем поля для структурного обнаружения диаграмм и ручного выбора страниц
        if 'path_excel_chart_sheets_json' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN path_excel_chart_sheets_json VARCHAR"))
                print("Added path_excel_chart_sheets_json column to files table")
            except Exception as e:
                print(f"Error adding path_excel_chart_sheets_json column: {e}")

        if 'excel_charts_pages_keep' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN excel_charts_pages_keep TEXT"))
                print("Added excel_charts_pages_keep column to files table")
            except Exception as e:
                print(f"Error adding excel_charts_pages_keep column: {e}")

        if 'path_video_original' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN path_video_original VARCHAR"))
                print("Added path_video_original column to files table")
            except Exception as e:
                print(f"Error adding path_video_original column: {e}")

        if 'path_video_poster' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN path_video_poster VARCHAR"))
                print("Added path_video_poster column to files table")
            except Exception as e:
                print(f"Error adding path_video_poster column: {e}")

        if 'video_duration' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN video_duration FLOAT"))
                print("Added video_duration column to files table")
            except Exception as e:
                print(f"Error adding video_duration column: {e}")

        if 'video_width' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN video_width INTEGER"))
                print("Added video_width column to files table")
            except Exception as e:
                print(f"Error adding video_width column: {e}")

        if 'video_height' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN video_height INTEGER"))
                print("Added video_height column to files table")
            except Exception as e:
                print(f"Error adding video_height column: {e}")

        if 'video_mime' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN video_mime VARCHAR"))
                print("Added video_mime column to files table")
            except Exception as e:
                print(f"Error adding video_mime column: {e}")

        if 'path_code_original' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN path_code_original VARCHAR"))
                print("Added path_code_original column to files table")
            except Exception as e:
                print(f"Error adding path_code_original column: {e}")

        if 'code_language' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN code_language VARCHAR"))
                print("Added code_language column to files table")
            except Exception as e:
                print(f"Error adding code_language column: {e}")

        if 'code_line_count' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN code_line_count INTEGER"))
                print("Added code_line_count column to files table")
            except Exception as e:
                print(f"Error adding code_line_count column: {e}")

        if 'path_markdown_raw' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN path_markdown_raw VARCHAR"))
                print("Added path_markdown_raw column to files table")
            except Exception as e:
                print(f"Error adding path_markdown_raw column: {e}")

        if 'markdown_line_count' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN markdown_line_count INTEGER"))
                print("Added markdown_line_count column to files table")
            except Exception as e:
                print(f"Error adding markdown_line_count column: {e}")

        if 'user_id' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN user_id VARCHAR"))
                print("Added user_id column to files table")
            except Exception as e:
                print(f"Error adding user_id column to files table: {e}")

        # OVC: добавляем поля в users при необходимости
        result = conn.execute(text("PRAGMA table_info(users)"))
        user_columns = [row[1] for row in result.fetchall()]
        
        if 'username' not in user_columns:
            try:
                # Добавляем username колонку (сначала nullable)
                conn.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR"))
                print("Added username column to users table")
                
                # Генерируем username из email для существующих пользователей
                # Извлекаем часть до @ и заменяем . на _
                conn.execute(text("""
                    UPDATE users 
                    SET username = REPLACE(LOWER(SUBSTR(email, 1, INSTR(email, '@') - 1)), '.', '_')
                    WHERE username IS NULL AND email IS NOT NULL
                """))
                print("Generated usernames from emails for existing users")
                
                # Создаем уникальный индекс на username
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)"))
                print("Created unique index on username")
            except Exception as e:
                print(f"Error adding username column to users table: {e}")
        
        if 'failed_login_count' not in user_columns:
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN failed_login_count INTEGER DEFAULT 0 NOT NULL"))
                print("Added failed_login_count column to users table")
            except Exception as e:
                print(f"Error adding failed_login_count column to users table: {e}")
        
        if 'locked_until' not in user_columns:
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN locked_until DATETIME"))
                print("Added locked_until column to users table")
            except Exception as e:
                print(f"Error adding locked_until column to users table: {e}")
        
        if 'supabase_id' not in user_columns:
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN supabase_id VARCHAR"))
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_supabase_id ON users(supabase_id)"))
                print("Added supabase_id column to users table")
            except Exception as e:
                print(f"Error adding supabase_id column to users table: {e}")

        # OVC: добавляем поля в notes при необходимости
        result = conn.execute(text("PRAGMA table_info(notes)"))
        note_columns = [row[1] for row in result.fetchall()]
        if 'user_id' not in note_columns:
            try:
                conn.execute(text("ALTER TABLE notes ADD COLUMN user_id VARCHAR"))
                print("Added user_id column to notes table")
            except Exception as e:
                print(f"Error adding user_id column to notes table: {e}")
        if 'revision' not in note_columns:
            try:
                conn.execute(text("ALTER TABLE notes ADD COLUMN revision INTEGER DEFAULT 0"))
                print("Added revision column to notes table")
            except Exception as e:
                print(f"Error adding revision column to notes table: {e}")
        if 'tombstone' not in note_columns:
            try:
                conn.execute(text("ALTER TABLE notes ADD COLUMN tombstone BOOLEAN DEFAULT 0"))
                print("Added tombstone column to notes table")
            except Exception as e:
                print(f"Error adding tombstone column to notes table: {e}")
        if 'client_origin' not in note_columns:
            try:
                conn.execute(text("ALTER TABLE notes ADD COLUMN client_origin VARCHAR"))
                print("Added client_origin column to notes table")
            except Exception as e:
                print(f"Error adding client_origin column to notes table: {e}")
        if 'last_client_ts' not in note_columns:
            try:
                conn.execute(text("ALTER TABLE notes ADD COLUMN last_client_ts DATETIME"))
                print("Added last_client_ts column to notes table")
            except Exception as e:
                print(f"Error adding last_client_ts column to notes table: {e}")

        # Если таблицы не существует, создаем все таблицы
        try:
            Base.metadata.create_all(bind=conn)
        except Exception as e:
            print(f"Error creating tables: {e}")


if __name__ == "__main__":
    upgrade()
