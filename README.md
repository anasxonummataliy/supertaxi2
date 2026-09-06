# SuperTaxi2 Bot

Telegram bot orqali e'lonlar va guruhlarni boshqarish tizimi.

Ushbu loyiha bitta kod bazasida bir vaqtning o'zida **bir nechta alohida botlarni (1-bot, 2-bot, 3-bot, 4-bot...)** (har biri o'zining mustaqil ma'lumotlar bazasi va log fayli bilan) ishga tushirishni to'liq qo'llab-quvvatlaydi.

---

## 🚀 Sozlash va ishga tushirish

Har bir bot uchun o'zining alohida `.env` konfiguratsiya fayli yaratiladi:

| Bot | Misol fayl | Asl fayl | Baza fayli | Log fayli |
| :--- | :--- | :--- | :--- | :--- |
| **1-Bot** | `.env.bot1.example` | `.env.bot1` | `bot1.db` | `bot1.log` |
| **2-Bot** | `.env.bot2.example` | `.env.bot2` | `bot2.db` | `bot2.log` |
| **3-Bot** | `.env.bot3.example` | `.env.bot3` | `bot3.db` | `bot3.log` |
| **4-Bot** | `.env.bot4.example` | `.env.bot4` | `bot4.db` | `bot4.log` |

### 1. Fayllarni nusxalash va to'ldirish:
```bash
cp .env.bot1.example .env.bot1
cp .env.bot2.example .env.bot2
cp .env.bot3.example .env.bot3
cp .env.bot4.example .env.bot4
```
Har bir faylga tegishli `BOT_TOKEN`, `ADMIN_IDS`, `API_ID`, `API_HASH` ma'lumotlarini kiriting.

---

## ▶️ Ishga tushirish usullari:

### 1-usul: Barcha botlarni birdaniga ishga tushirish (`run_all.py` orqali)
Mavjud barcha `.env.bot*` fayllarni avtomatik topib, barchasini parallel ishga tushiradi:
```bash
python run_all.py
```
*(To'xtatish uchun: `Ctrl + C`)*

### 2-usul: Har bir botni alohida terminalda ishga tushirish
```bash
# 1-bot:
python main.py .env.bot1

# 2-bot:
python main.py .env.bot2

# 3-bot:
python main.py .env.bot3

# 4-bot:
python main.py .env.bot4
```

---

## 🖥 Linux Serverda (Systemd orqali fonda ishlatish):

Loyiha papkasida tayyor service fayllari mavjud:
- `supertaxi_bot1.service`
- `supertaxi_bot2.service`
- `supertaxi_bot3.service`
- `supertaxi_bot4.service`

### Serverga o'rnatish va ishga tushirish:
```bash
# Service fayllarini tizim papkasiga nusxalash
sudo cp supertaxi_bot1.service /etc/systemd/system/
sudo cp supertaxi_bot2.service /etc/systemd/system/
sudo cp supertaxi_bot3.service /etc/systemd/system/
sudo cp supertaxi_bot4.service /etc/systemd/system/

# Tizimni yangilash va xizmatlarni yoqish
sudo systemctl daemon-reload
sudo systemctl enable --now supertaxi_bot1 supertaxi_bot2 supertaxi_bot3 supertaxi_bot4
```

### Holatni tekshirish:
```bash
sudo systemctl status supertaxi_bot1 supertaxi_bot2 supertaxi_bot3 supertaxi_bot4
```

### Loglarni jonli kuzatish:
```bash
# 1-bot loglari:
tail -f bot1.log

# 3-bot loglari:
tail -f bot3.log
```
