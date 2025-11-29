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

        # Если таблицы не существует, создаем все таблицы
        try:
            Base.metadata.create_all(bind=conn)
        except Exception as e:
            print(f"Error creating tables: {e}")


if __name__ == "__main__":
    upgrade()
