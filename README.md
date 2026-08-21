# SuperTaxi2 Bot

Telegram bot orqali e'lonlar va guruhlarni boshqarish tizimi.

Ushbu loyiha bitta kod bazasida bir vaqtning o'zida **bir nechta alohida botlarni** (har biri o'zining mustaqil ma'lumotlar bazasi va log fayli bilan) ishga tushirishni to'liq qo'llab-quvvatlaydi.

---

## 🚀 1 ta yoki bir nechta botni ishga tushirish

### 1. Bitta bot uchun (Standart rejim):
`.env` faylini yarating:
```bash
cp .env.example .env
```
Faylni to'ldirib, botni ishga tushiring:
```bash
python main.py
```

---

### 2. 2 ta (yoki undan ortiq) alohida botni ishga tushirish:

Har bir bot uchun alohida `.env` fayl yarating:

#### 1-bot uchun `.env.bot1`:
```env
BOT_TOKEN=1111111111:AAAbbbCcc...
ADMIN_IDS=123456789
API_ID=12345678
API_HASH=0123456789abcdef0123456789abcdef
DB_PATH=bot1.db
LOG_FILE=bot1.log
```

#### 2-bot uchun `.env.bot2`:
```env
BOT_TOKEN=2222222222:DDDeeeFff...
ADMIN_IDS=987654321
API_ID=12345678
API_HASH=0123456789abcdef0123456789abcdef
DB_PATH=bot2.db
LOG_FILE=bot2.log
```

---

### ▶️ Ishga tushirish usullari:

#### 1-usul: CLI argument orqali
```bash
# 1-botni ishga tushirish:
python main.py .env.bot1

# 2-botni alohida terminal/processda ishga tushirish:
python main.py .env.bot2
```

#### 2-usul: `ENV_FILE` o'zgaruvchisi orqali
```bash
ENV_FILE=.env.bot1 python main.py
ENV_FILE=.env.bot2 python main.py
```

---

### 🖥 Linux Serverda (Systemd orqali fonda ishlatish):

**1-bot xizmati:** `/etc/systemd/system/supertaxi_bot1.service`
```ini
[Unit]
Description=SuperTaxi Bot 1 Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/supertaxi2
ExecStart=/root/supertaxi2/.venv/bin/python main.py .env.bot1
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

**2-bot xizmati:** `/etc/systemd/system/supertaxi_bot2.service`
```ini
[Unit]
Description=SuperTaxi Bot 2 Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/supertaxi2
ExecStart=/root/supertaxi2/.venv/bin/python main.py .env.bot2
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Xizmatlarni yoqish va ishga tushirish:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now supertaxi_bot1 supertaxi_bot2
```
