# Чек-лист по развертыванию Alex Bot v11.0

Привет, Полина! 🥃 Это Алекс. Я подготовил для тебя финальный чек-лист, чтобы ты ничего не забыла при развертывании меня на Oracle Cloud. Следуй ему шаг за шагом, и всё получится! 😏

---

## ✅ Шаг 1: Сбор всех ключей и ID

*   [ ] **Telegram Bot Token:** Получен от @BotFather.
*   [ ] **Твой Telegram ID:** Получен от @userinfobot.
*   [ ] **Groq API Key:** Получен с [Groq Console](https://console.groq.com/keys).
*   [ ] **Notion Internal Integration Token:** Получен с [Notion Integrations](https://www.notion.so/my-integrations).
*   [ ] **Notion: Доступ к базам данных:** Интеграция "Alex Bot Integration" приглашена во все 8 баз данных с правами "Can edit content".
*   [ ] **CallMeBot API Key:** Получен от [CallMeBot Telegram Bot](https://t.me/CallMeBot_bot) (опционально).
*   [ ] **Твой номер телефона:** Зарегистрирован в CallMeBot в международном формате (опционально).
*   [ ] **Telegram ID Алины:** Получен от @userinfobot (опционально, если нужен социальный пинок).

---

## ✅ Шаг 2: Подготовка Oracle VM

*   [ ] **Подключение по SSH:** Успешно подключилась к VM.
*   [ ] **Обновление системы:** Выполнено `sudo apt update && sudo apt upgrade -y`.
*   [ ] **Установка Python и Git:** Выполнено `sudo apt install -y python3.11 python3-pip git`.
*   [ ] **Создание папки для бота:** Выполнено `mkdir -p ~/alex_bot` и `cd ~/alex_bot`.

---

## ✅ Шаг 3: Загрузка файлов бота на сервер

*   [ ] **Архив `alex_bot_v11.0_complete.tar.gz`:** Загружен на сервер в папку `~/alex_bot/` с помощью `scp`.
*   [ ] **Распаковка архива:** Выполнено `tar -xzf alex_bot_v11.0_complete.tar.gz`.
*   [ ] **Удаление архива:** Выполнено `rm alex_bot_v11.0_complete.tar.gz`.
*   [ ] **Установка Python-зависимостей:** Выполнено `pip3 install -r requirements.txt --break-system-packages`.

---

## ✅ Шаг 4: Настройка файла `.env`

*   [ ] **Создание файла `.env`:** Выполнено `nano .env` в папке `~/alex_bot/`.
*   [ ] **Заполнение `.env`:** Все `YOUR_...` заменены на реальные значения.
*   [ ] **Сохранение файла:** `Ctrl+X`, `Y`, `Enter`.

---

## ✅ Шаг 5: Запуск Алекса в фоновом режиме (Systemd)

*   [ ] **Создание файла сервиса:** Выполнено `sudo nano /etc/systemd/system/alex_bot.service`.
*   [ ] **Заполнение файла сервиса:** Содержимое из `DEPLOYMENT_GUIDE_RU.md` вставлено и сохранено.
*   [ ] **Перезагрузка `systemd`:** Выполнено `sudo systemctl daemon-reload`.
*   [ ] **Запуск сервиса:** Выполнено `sudo systemctl start alex_bot`.
*   [ ] **Включение автозапуска:** Выполнено `sudo systemctl enable alex_bot`.

---

## ✅ Шаг 6: Проверка работы бота

*   [ ] **Проверка статуса сервиса:** `sudo systemctl status alex_bot` показывает `active (running)`.
*   [ ] **В Telegram:** Написала боту `/start`.
*   [ ] **Бот ответил:** Получила приветственное сообщение от Алекса.
*   [ ] **Тестирование команд:** Проверила `/mood 7`, `/achievements`, `/goals`, `/reschedule`.

---

**Поздравляю, Полина! Если все пункты отмечены, Алекс успешно развернут и готов к работе!** 🚀🤘✨

Если что-то пошло не так, не паникуй! Смотри раздел "Устранение неполадок" в `DEPLOYMENT_GUIDE_RU.md` или просто пришли мне ошибку. Я помогу! 🥃
