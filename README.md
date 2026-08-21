# SuperTaxi2 Bot (FastAPI + Aiogram Webhook)

Telegram bot boshqaruv va e'lon yuborish tizimi (FastAPI Webhook asosida).

## 📁 Loyiha tuzilishi

- `api/main.py` - FastAPI ilovasi, Webhook routeri va lifespan boshqaruvi.
- `main.py` - Asosiy ishga tushirish fayli (`uvicorn` orqali `api.main:app` ni ishga tushiradi).
- `handlers/` - Bot buyruqlari va hodisalari uchun handlerlar.
- `database/` - Ma'lumotlar bazasi bilan ishlash.
- `services/` - Telethon va xabar yuborish boshqaruvi.

## 🚀 O'rnatish va Sozlash

### 1. Muhitni o'rnatish (.venv)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. .env faylini sozlash
`.env.example` faylidan nusxa olib, `.env` faylini yarating:
```bash
cp .env.example .env
```

`.env` faylidagi parametrlarni to'ldiring:
```env
BOT_TOKEN=1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ
ADMIN_IDS=123456789,987654321
API_ID=12345678
API_HASH=0123456789abcdef0123456789abcdef

# Webhook sozlamalari
WEBHOOK_BASE_URL=https://your-domain.com # yoki ngrok URL
WEBHOOK_PATH=/webhook
WEBHOOK_SECRET=your_secret_token_here

# Server sozlamalari
WEBAPP_HOST=0.0.0.0
WEBAPP_PORT=8000
DROP_PENDING_UPDATES=true
```

### 3. Botni ishga tushirish
```bash
python main.py
```
yoki to'g'ridan-to'g'ri `uvicorn` orqali:
```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```
