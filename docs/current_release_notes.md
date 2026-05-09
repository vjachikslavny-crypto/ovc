# OVC — Current Release Notes (vanya+max merge)

Этот документ фиксирует **актуальные нововведения** в текущем состоянии проекта после слияния ветки `ok10010-system-wide-performance-optimization-and-reliability-track` в локальную ветку от `develop`.

Назначение: быстрый ориентир для команды перед следующими задачами и слияниями.

## 1) Что изменилось на уровне продукта

- Главная страница (`/`) стала рабочим dashboard-экраном (`welcome.html`), а не прямым входом в редактор.
- Добавлена явная страница редактора `/editor` (плюс остается открытие заметки по `/notes/{id}`).
- Навигация в `base.html` обновлена: `Главная`, `База`, `Редактор`, `Граф`.
- На мобильных экранах верхняя навигация переведена в **горизонтальный скролл-ряд** с touch-friendly кнопками.

## 2) Новое в web UI

### Welcome Dashboard

- Новый сценарий работы на `/`:
  - блок аккаунта/профиля,
  - быстрые действия,
  - список недавних заметок,
  - отдельные вкладки для списка заметок и графа,
  - подгрузка графа/карточек через `src/static/js/welcome_dashboard.js`.

### База заметок (`/notes`)

- Сохранен deep-search по заметкам и файлам.
- Добавлена штатная кнопка удаления карточки заметки:
  - мягкая кнопка `×` в карточке,
  - модальное подтверждение удаления,
  - безопасный сценарий отмены.

### Редактор (`/editor`, `/notes/{id}`)

- Сохранены текущие инструменты и layout.
- Доработаны визуальные детали (рамки/фокус/hover), без удаления рабочих функций.
- Мини-граф и инспектор остались в рабочем контуре.

## 3) Auth / runtime / sync (актуальное поведение)

- Поддерживаются режимы `AUTH_MODE`: `local | supabase | both | none`.
- Для desktop dev-fallback действует явный флаг `ALLOW_DESKTOP_DEV_FALLBACK`.
- Runtime-диагностика: `GET /api/runtime/status` (если включено в конфиге).
- Sync-режимы остаются `off | shared-db | remote-shell | remote-sync | auto`.

## 4) Файлы и аудио

- В `src/app/services/files.py` сохранен fallback-алгоритм waveform для WAV без критической привязки к `audioop`.
- Это уменьшает риск несовместимости на новых версиях Python и позволяет держать текущую логику предпросмотра аудио.

## 5) Ключевые затронутые файлы

- `src/templates/base.html`
- `src/templates/welcome.html`
- `src/templates/editor.html`
- `src/static/js/welcome_dashboard.js` (новый)
- `src/static/js/notes_page.js`
- `src/static/js/notes_renderer.js`
- `src/static/js/editor.js`
- `src/static/js/auth.js`
- `src/static/js/inspector.js`
- `src/static/js/mini-graph.js`
- `src/static/css/styles.css`
- `src/app/main.py`
- `src/app/services/files.py`

## 6) Что важно проверить после следующих merge

Мини-чек:

1. Авторизация (local/supabase/both).
2. Создание/редактирование/удаление заметки.
3. Deep-search и pagination в `/notes`.
4. Welcome Dashboard (вкладки Notes/Graph, переходы в заметки).
5. Редактор + мини-граф + инспектор.
6. Загрузка файлов и предпросмотр (в т.ч. аудио-блоки).
7. Мобильный вид: отсутствие горизонтального перелома страницы и корректный скролл навигации.

