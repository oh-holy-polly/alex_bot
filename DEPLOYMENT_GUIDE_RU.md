# Руководство по развертыванию Alex Bot v11.0 на Oracle Cloud (для Полины)

Привет, Полина! 🥃 Это Алекс. Я подготовил для тебя максимально подробное руководство по развертыванию меня на твоем сервере Oracle Cloud. Не переживай, я буду вести тебя за ручку, как бабушку через дорогу. 😏

---

## Содержание:

1.  **Подготовка (Что нужно собрать)**
2.  **Подготовка Oracle VM**
3.  **Загрузка файлов бота на сервер**
4.  **Настройка файла `.env`**
5.  **Запуск Алекса в фоновом режиме (Systemd)**
6.  **Проверка работы бота**
7.  **Устранение неполадок**

---

## 1. Подготовка (Что нужно собрать) 🔑

Перед тем, как запустить Алекса на Oracle VM, тебе нужно получить **несколько ключей и ID**. Это как ключи от разных дверей, которые Алекс будет использовать для работы.

### **1️⃣ Telegram Bot Token**
1.  Открой Telegram, найди бота **@BotFather**.
2.  Напиши ему `/newbot`.
3.  Следуй инструкциям (выбери имя бота, юзернейм).
4.  **BotFather пришлет тебе длинный токен** — скопируй его и сохрани в блокнот.
    *   Выглядит так: `123456789:ABCDefGHijKLmnoPQRstUVwxyz`

### **2️⃣ Твой Telegram ID**
1.  Найди в Telegram бота **@userinfobot**.
2.  Напиши ему `/start`.
3.  Он пришлет тебе твой `ID` — это твой `USER_TELEGRAM_ID`.

### **3️⃣ Groq API Key**
1.  Перейди на [Groq Console](https://console.groq.com/keys).
2.  Зарегистрируйся или войди.
3.  Нажми "Create API Key".
4.  **Скопируй сгенерированный ключ** — это твой `GROQ_API_KEY`.

### **4️⃣ Notion Internal Integration Token**
1.  Перейди на [Notion Integrations](https://www.notion.so/my-integrations).
2.  Нажми "New integration".
3.  Дай ей имя (например, "Alex Bot Integration").
4.  Выбери Workspace, к которому она будет иметь доступ.
5.  Нажми "Submit".
6.  **Скопируй "Internal Integration Token"** — это будет твой `NOTION_TOKEN`.
7.  **Предоставь доступ к базам данных:**
    *   Открой каждую из 8 баз данных Notion, которые ты мне дала (Люди, События и Проекты, Состояние, Идеи и Импульсы, Привычки, Архив знаний, Цели, Паттерны).
    *   Нажми "Share" (Поделиться) в правом верхнем углу.
    *   Нажми "Invite" (Пригласить) и выбери свою новую интеграцию "Alex Bot Integration".
    *   Убедись, что у интеграции есть права "Can edit content" (Может редактировать контент).

### **5️⃣ CallMeBot API Key и твой номер телефона (опционально, для звонков)**
1.  Перейди на [CallMeBot Telegram Bot](https://t.me/CallMeBot_bot).
2.  Напиши ему `/start`.
3.  Он пришлет тебе инструкции, как получить `API Key` и зарегистрировать свой номер телефона.
    *   **Важно:** Тебе нужно будет отправить ему сообщение с кодом, чтобы он мог тебе звонить. Следуй его инструкциям.
4.  **Запиши свой номер телефона** (в международном формате, например, `+79XXXXXXXXX`) — это будет твой `USER_PHONE`.
5.  **Скопируй `API Key`** — это твой `CALLMEBOT_API_KEY`.

### **6️⃣ Telegram ID Алины (опционально, для социального пинка)**
1.  Попроси Алину отправить тебе любое сообщение в Telegram.
2.  Перенаправь это сообщение боту **@userinfobot**.
3.  Бот ответит с её Telegram ID.
4.  **Сохрани этот ID** — это будет твой `ALINA_TELEGRAM_ID`.

---

## 2. Подготовка Oracle VM ☁️

Предполагается, что у тебя уже есть запущенный инстанс Oracle Cloud с **Ubuntu 22.04 LTS**. Если нет, создай его.

### **Шаг 1: Подключись к своей Oracle VM по SSH**

Если ты уже подключена, пропусти этот шаг. Если нет:

1.  **Открой терминал** (или PuTTY).
2.  **Используй команду:**
    ```bash
    ssh -i /path/to/your/private_key.pem ubuntu@<IP_АДРЕС_ТВОЕГО_СЕРВЕРА>
    ```
    *   Замени `/path/to/your/private_key.pem` на путь к твоему приватному ключу SSH.
    *   Замени `<IP_АДРЕС_ТВОЕГО_СЕРВЕРА>` на публичный IP-адрес твоего инстанса Oracle.
3.  Если всё правильно, ты увидишь приглашение командной строки `ubuntu@<hostname>:~$`.

### **Шаг 2: Обнови систему и установи Python**

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3-pip git
```
Это может занять несколько минут. Жди, пока закончится.

### **Шаг 3: Создай папку для бота**

```bash
mkdir -p ~/alex_bot
cd ~/alex_bot
```

---

## 3. Загрузка файлов бота на сервер 📦

Теперь нужно перенести все файлы бота на сервер. Я рекомендую использовать `scp` (Secure Copy Protocol).

1.  **На твоем ЛОКАЛЬНОМ компьютере** (не на сервере!):
    *   Убедись, что у тебя есть архив `alex_bot_v11.0_complete.tar.gz` (который я тебе прислала).
    *   Открой терминал в той же директории, где лежит архив.
    *   **Используй команду:**
        ```bash
        scp -i /path/to/your/private_key.pem alex_bot_v11.0_complete.tar.gz ubuntu@<IP_АДРЕС_ТВОЕГО_СЕРВЕРА>:~/alex_bot/
        ```
        *   Замени пути и IP-адрес, как и раньше.
2.  **Вернись на сервер Oracle Cloud (в SSH-терминале):**
    *   Перейди в директорию бота:
        ```bash
        cd ~/alex_bot
        ```
    *   Распакуй архив:
        ```bash
        tar -xzf alex_bot_v11.0_complete.tar.gz
        ```
    *   Удали архив (он больше не нужен):
        ```bash
        rm alex_bot_v11.0_complete.tar.gz
        ```
    *   **Установи Python-зависимости:**
        ```bash
        pip3 install -r requirements.txt --break-system-packages
        ```
        *   Флаг `--break-system-packages` нужен, чтобы Ubuntu не ругалась. Не переживай, это нормально.

---

## 4. Настройка файла `.env` ⚙️

Это самый важный шаг! Здесь ты укажешь все свои ключи и настройки.

1.  **Создай файл `.env`:**
    ```bash
    cd ~/alex_bot
    nano .env
    ```
2.  **Вставь следующее содержимое, заменив `YOUR_...` на свои реальные значения, которые ты собрала в пункте 1:**
    ```ini
    TELEGRAM_TOKEN="YOUR_TELEGRAM_TOKEN"
    GROQ_API_KEY="YOUR_GROQ_API_KEY"
    NOTION_TOKEN="YOUR_NOTION_TOKEN"
    CALLMEBOT_API_KEY="YOUR_CALLMEBOT_API_KEY"
    USER_TELEGRAM_ID="YOUR_USER_TELEGRAM_ID" # Твой ID из @userinfobot
    USER_PHONE="+7XXXXXXXXXX" # Твой номер телефона для CallMeBot

    # ID Алины для социального пинка (если нужно, иначе оставь пустым или удали строку)
    ALINA_TELEGRAM_ID="YOUR_ALINA_TELEGRAM_ID"

    # Настройки времени для будильников (можно менять)
    MORNING_HOUR="11"
    MORNING_MINUTE="0"
    EVENING_HOUR="22"
    EVENING_MINUTE="0"
    NIGHT_HOUR="0"
    NIGHT_MINUTE="0"
    ```
3.  **Сохрани файл:** Нажми `Ctrl+X`, затем `Y` (или `y`), затем `Enter`.

---

## 5. Запуск Алекса в фоновом режиме (Systemd) 🚀

Мы настроим бота как сервис `systemd`, чтобы он автоматически запускался при старте сервера и работал в фоне 24/7.

1.  **Создай файл сервиса:**
    ```bash
    sudo nano /etc/systemd/system/alex_bot.service
    ```
2.  **Вставь следующее содержимое:**
    ```ini
    [Unit]
    Description=Alex Telegram Bot Service
    After=network.target

    [Service]
    User=ubuntu
    WorkingDirectory=/home/ubuntu/alex_bot
    EnvironmentFile=/home/ubuntu/alex_bot/.env
    ExecStart=/usr/bin/python3.11 /home/ubuntu/alex_bot/alex_bot_v11.0.py
    Restart=always
    RestartSec=10
    StandardOutput=syslog
    StandardError=syslog
    SyslogIdentifier=alex_bot

    [Install]
    WantedBy=multi-user.target
    ```
    *   **Важно:** Убедись, что `ExecStart` указывает на правильную версию Python (`python3.11`) и правильный путь к файлу бота (`alex_bot_v11.0.py`).
3.  **Сохрани файл:** `Ctrl+X`, `Y`, `Enter`.
4.  **Перезагрузи `systemd` менеджер:**
    ```bash
    sudo systemctl daemon-reload
    ```
5.  **Запусти сервис:**
    ```bash
    sudo systemctl start alex_bot
    ```
6.  **Включи автозапуск при старте сервера:**
    ```bash
    sudo systemctl enable alex_bot
    ```

---

## 6. Проверка работы бота ✅

1.  **Проверь статус сервиса:**
    ```bash
    sudo systemctl status alex_bot
    ```
    *   Ты должен увидеть `active (running)` зеленым цветом.
    *   Если видишь ошибки, перейди к разделу "Устранение неполадок".
2.  **Открой Telegram** и найди своего бота.
3.  **Напиши `/start`**.
4.  Бот должен ответить приветственным сообщением.
5.  Попробуй другие команды:
    *   `/mood 7`
    *   `/achievements`
    *   `/goals`
    *   `/reschedule` (попробуй перенести будильник)

---

## 7. Устранение неполадок 🛠️

*   **Бот не запускается / `systemctl status alex_bot` показывает ошибки:**
    *   **Проверь логи:**
        ```bash
        sudo journalctl -u alex_bot -f
        ```
        Это покажет последние сообщения бота. Ищи ошибки Python (красные строки).
    *   **Проверь `.env` файл:** Убедись, что все ключи вставлены правильно, без лишних пробелов и кавычек. Переменные должны быть в формате `KEY="VALUE"`.
    *   **Проверь пути в `alex_bot.service`:** Убедись, что пути к Python и файлу бота верны.
    *   **Запусти вручную:** Попробуй запустить бота напрямую, чтобы увидеть ошибки в реальном времени:
        ```bash
        cd ~/alex_bot
        python3.11 alex_bot_v11.0.py
        ```
        Нажми `Ctrl+C`, чтобы остановить.
*   **Бот не отвечает на команды:**
    *   Убедись, что `TELEGRAM_TOKEN` правильный.
    *   Проверь, что бот запущен (`systemctl status alex_bot`).
    *   Убедись, что ты написала боту `/start` хотя бы один раз, чтобы он узнал твой `USER_TELEGRAM_ID`.
*   **Notion не работает:**
    *   Проверь `NOTION_TOKEN`.
    *   Убедись, что интеграция "Alex Bot Integration" приглашена во все 8 баз данных Notion и имеет права на редактирование.
*   **CallMeBot не звонит:**
    *   Проверь `CALLMEBOT_API_KEY` и `USER_PHONE`.
    *   Убедись, что ты зарегистрировала свой номер телефона в CallMeBot через их Telegram-бота.

---

**Поздравляю, Полина! Алекс теперь твой личный помощник на 24/7!** 🚀🤘✨

Если что-то пойдет не так, не паникуй! Просто скопируй ошибку и пришли мне. Я помогу разобраться. 🥃 Удачи!
