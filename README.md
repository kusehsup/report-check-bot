# report-check-bot

Telegram-бот для ежедневной проверки ответов администраторов на [panel.exbot.su](https://panel.exbot.su/login).

Бот загружает за день два источника и пишет в таблицу тип `Report` или `FAQ`:

- **Report** — ответы на репорты в админ-чат (уровень 2+), API `report-log`
- **FAQ** — ответы на z-request (вопросы игроков в поддержку), API `player-requests-z`

## Возможности

- `/check` — выбрать «Сегодня» или «Вчера» (часовой пояс Москвы)
- Одна карточка = один ответ администратора; тип показан как Report/FAQ
- Проверка идёт в одном сообщении бота: дальше/назад/вердикт правят его, а не спамят чат
- Если на вопрос ответили несколько человек, соседние ответы показаны списком
- Кнопки: **Плохой ответ** → вердикт (`Устная беседа` / `Предупреждение` / `Выговор` / свой текст), **Дальше**, **Назад**
- Уже записанные в таблицу ответы пропускаются
- Состояние проверки хранится в SQLite и переживает перезапуск

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Заполните `.env` (или Runtime Secrets):

| Переменная | Назначение |
|---|---|
| `BOT_TOKEN` | токен Telegram-бота |
| `PANEL_REFRESH_NOW` | cookie `refresh_token` (один раз; дальше крутится сам) |
| `PANEL_ACCESS_NOW` | необязательно; access обновляется автоматически |
| `SERVICE_ACCOUNT_PATH` | путь к JSON ключу Google service account |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | тот же ключ одной строкой (альтернатива пути) |
| `ADMIN_IDS` | кто может пользоваться ботом |

Сессия панели пишется в `data/panel_session.json`. Access обновляется сам; если панель ротирует refresh — новое значение сохраняется туда же. Команды: `/panel_status`, `/panel_auth`.

Таблицу нужно расшарить на email сервисного аккаунта с правом редактора.

## Запуск

```bash
python -m bot
```

## Тесты

```bash
pytest -q
```

## API панели

- `GET /api/v1/auth` — обновление access token по cookie `refresh_token`
- `GET /api/v1/report-log?serverId=6&startDate=...&endDate=...`
- `GET /api/v1/player-requests-z?serverId=6&category=answer_text&startTime=...&endTime=...`
