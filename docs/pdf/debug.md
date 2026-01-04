# Диагностика проблемы загрузки PDF страниц

## Шаги для диагностики:

1. **Откройте консоль браузера** (F12 → Console)
2. **Откройте вкладку Network** (F12 → Network)
3. **Перезагрузите страницу** и нажмите "Просмотр" на PDF-блоке
4. **Проверьте логи в консоли:**

   Должны появиться следующие логи в порядке:
   - `PDF viewer: initPdfViewers called`
   - `PDF viewer: initializing block`
   - `PDF viewer: switching to inline view` (при нажатии "Просмотр")
   - `PDF viewer: mounting pages`
   - `PDF viewer: pages mounted and observed`
   - `PDF viewer: preparing to load pages`
   - `PDF viewer: starting to load pages`
   - `PDF viewer: scheduling page load`
   - `PDF viewer: starting load for page`
   - `PDF viewer: loading page`
   - `PDF viewer: starting fetch request`
   - `PDF viewer: fetch response received`
   - `PDF viewer: blob received`
   - `PDF viewer: setting img.src`
   - `PDF viewer: img.onload fired`
   - `PDF viewer: page loaded successfully`

5. **Проверьте запросы в Network:**

   - Фильтр: `Img` или `XHR`
   - Найдите запросы к `/files/{file_id}/page/{page_num}`
   - Проверьте статус: должен быть `200`
   - Проверьте размер ответа: должен быть ~100-500 КБ
   - Проверьте тип: должен быть `image/webp`

## Возможные проблемы:

### 1. Запросы не отправляются
   - **Симптом:** Нет запросов в Network tab
   - **Причина:** `loadPage()` не вызывается или блокируется проверкой
   - **Решение:** Проверьте логи `PDF viewer: scheduling page load` и `PDF viewer: starting load for page`

### 2. Запросы возвращают ошибку 500
   - **Симптом:** Запросы в Network с статусом 500
   - **Причина:** Ошибка на сервере (PyMuPDF не установлен или ошибка рендеринга)
   - **Решение:** Проверьте логи сервера и убедитесь, что PyMuPDF установлен

### 3. Запросы зависают (pending)
   - **Симптом:** Запросы в Network с статусом pending
   - **Причина:** Проблема с сетью или сервером
   - **Решение:** Проверьте, что сервер запущен и доступен

### 4. Изображения загружаются, но не отображаются
   - **Симптом:** Запросы успешны (200), но изображения не видны
   - **Причина:** Проблема с CSS или отображением
   - **Решение:** Проверьте логи `PDF viewer: image displayed` и проверьте CSS

## Что проверить в консоли:

1. **Есть ли ошибки JavaScript?** (красные сообщения)
2. **Есть ли логи `PDF viewer: starting fetch request`?** (если нет - `loadPage()` не вызывается)
3. **Есть ли логи `PDF viewer: fetch response received`?** (если нет - запросы не доходят до сервера)
4. **Есть ли логи `PDF viewer: page loaded successfully`?** (если нет - проблема с обработкой ответа)

## Что проверить в Network:

1. **Есть ли запросы к `/files/{file_id}/page/{page_num}`?**
2. **Какой статус у запросов?** (должен быть 200)
3. **Какой размер ответа?** (должен быть ~100-500 КБ)
4. **Какой тип контента?** (должен быть `image/webp`)
5. **Сколько времени выполняются запросы?** (должно быть < 2 секунд для кэшированных страниц)

## Быстрая проверка API:

Выполните в терминале:
```bash
curl "http://127.0.0.1:8000/files/{file_id}/page/1?scale=1" -o test.webp
file test.webp
```

Должен вернуть WebP изображение размером ~100-500 КБ.

