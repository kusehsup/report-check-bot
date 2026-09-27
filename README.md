# report-check-bot

Telegram-бот для ежедневной проверки ответов администраторов на [panel.exbot.su](https://panel.exbot.su/login).

Бот загружает логи `Report` и `FAQ` за день, показывает по одной карточке на каждый ответ администратора и по кнопке записывает вердикт в Google-таблицу.

## Возможности

- `/check` — выбрать «Сегодня» или «Вчера» (часовой пояс Москвы)
- Одна карточка = один ответ администратора
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
| `PANEL_REFRESH_NOW` | cookie `refresh_token` после входа на панель |
| `PANEL_ACCESS_NOW` | запасной access token |
| `SERVICE_ACCOUNT_PATH` | путь к JSON ключу Google service account |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | тот же ключ одной строкой (альтернатива пути) |
| `ADMIN_IDS` | необязательно: кто может пользоваться ботом |

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
