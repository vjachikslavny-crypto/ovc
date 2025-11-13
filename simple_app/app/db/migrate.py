from app.db.models import Base
from app.db.session import engine
from sqlalchemy import text


def upgrade() -> None:
    # OVC: audio - добавляем колонку path_waveform в таблицу files, если её нет
    with engine.begin() as conn:
        # Проверяем, существует ли колонка path_waveform
        result = conn.execute(text("PRAGMA table_info(files)"))
        columns = [row[1] for row in result.fetchall()]
        
        if 'path_waveform' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN path_waveform VARCHAR"))
                print("Added path_waveform column to files table")
            except Exception as e:
                print(f"Error adding path_waveform column: {e}")
        
        # Проверяем, существует ли колонка duration (для аудио)
        if 'duration' not in columns:
            try:
                conn.execute(text("ALTER TABLE files ADD COLUMN duration FLOAT"))
                print("Added duration column to files table")
            except Exception as e:
                print(f"Error adding duration column: {e}")
        
        # Если таблицы не существует, создаем все таблицы
        try:
            Base.metadata.create_all(bind=conn)
        except Exception as e:
            print(f"Error creating tables: {e}")


if __name__ == "__main__":
    upgrade()
