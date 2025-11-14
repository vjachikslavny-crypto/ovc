from app.db.models import Base
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

        # Если таблицы не существует, создаем все таблицы
        try:
            Base.metadata.create_all(bind=conn)
        except Exception as e:
            print(f"Error creating tables: {e}")


if __name__ == "__main__":
    upgrade()
