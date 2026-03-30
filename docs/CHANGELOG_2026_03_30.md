# Changelog — 30.03.2026

## 1. Ротация вакансий — исправлена
- Celery worker перезапущен с новым кодом resend.py
- Ротация работает: search_active=True + 5 мин интервал + звуковое уведомление
- Добавлен disable_notification=False в TextStrategy.send()
- Добавлено подробное логирование ротации

## 2. Закрытие вакансий — кнопка меняется на "Вакансію закрито"
- VacancyStatusClosedObserver: ставит search_active=False + редактирует сообщение в канале
- VacancyDeleteMessagesChannelObserver: редактирует вместо удаления
- При закрытии/удалении вакансии кнопка "Я ГОТОВИЙ ПРАЦЮВАТИ" → "Вакансію закрито"

## 3. Блокировка пользователей из ЛК Администратора
- Исправлена форма block/unblock в admin_search_results.html (добавлены hidden fields action, block_type)
- Добавлена аннотация active_block_id для отображения правильной кнопки
- Синхронизация is_active при блокировке/разблокировке
- Добавлены заголовки Cache-Control для обновления страницы
- Убрано слово "постійно" из сообщения о блокировке
- Защита от двойного нажатия кнопки

## 4. Webhook стабильность
- Токен перегенерирован (старый утёк в git)
- .env убран из git
- Gunicorn EnvironmentFile → /home/webuser/robochi_bot/.env
- MenuButton и команды переустановлены

## 5. Фильтр телефонов в группах вакансий
- telegram/handlers/messages/group.py: regex фильтр UA телефонов (+380, 380, 0XX)
- Удаляет сообщения с телефонами от не-админов
- Отправляет уведомление автору в личку

## 6. Команда /help
- Заменены /start + /info на одну /help
- Inline-кнопка "Написати адміністратору" → @robochi_work_admin
- В группах: отправляет в личку, удаляет команду

## 7. collectstatic lifecycle.js
- Файл lifecycle.js отсутствовал в staticfiles → collectstatic
