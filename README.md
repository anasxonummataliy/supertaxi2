# SuperTaxi2 Bot

Telegram bot orqali e'lonlar va guruhlarni boshqarish tizimi.

Ushbu loyiha bitta kod bazasida bir vaqtning o'zida **bir nechta alohida botlarni (1-bot, 2-bot, 3-bot, 4-bot, 5-bot, 6-bot, 7-bot, 8-bot, 9-bot...)** ishga tushirishni to'liq qo'llab-quvvatlaydi.

### 🌐 Yagona Guruhlar Bazasi (`groups.db`)
Barcha botlar **yagona umumiy guruhlar bazasiga (`groups.db`)** ulangan. Biror botdan yoki admin tomonidan guruh qo'shilsa yoki o'chirilsa, u barcha botlarda bir zumda yangilanadi va barcha botlar ushbu umumiy guruhlarga e'lonlar tarqatishi mumkin. Akkauntlar va e'lon vazifalari esa har bir botning o'z alohida bazasida (`bot1.db`, `bot2.db`, ...) mustaqil saqlanadi.

---

## 🚀 Sozlash va ishga tushirish

Har bir bot uchun o'zining alohida `.env` konfiguratsiya fayli mavjud:

| Bot | Misol fayl | Asl fayl | Akkauntlar bazasi | Guruhlar bazasi | Log fayli |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1-Bot** | `.env.bot1.example` | `.env.bot1` | `bot1.db` | `groups.db` | `bot1.log` |
| **2-Bot** | `.env.bot2.example` | `.env.bot2` | `bot2.db` | `groups.db` | `bot2.log` |
| **3-Bot** | `.env.bot3.example` | `.env.bot3` | `bot3.db` | `groups.db` | `bot3.log` |
| **4-Bot** | `.env.bot4.example` | `.env.bot4` | `bot4.db` | `groups.db` | `bot4.log` |
| **5-Bot** | `.env.bot5.example` | `.env.bot5` | `bot5.db` | `groups.db` | `bot5.log` |
| **6-Bot** | `.env.bot6.example` | `.env.bot6` | `bot6.db` | `groups.db` | `bot6.log` |
| **7-Bot** | `.env.bot7.example` | `.env.bot7` | `bot7.db` | `groups.db` | `bot7.log` |
| **8-Bot** | `.env.bot8.example` | `.env.bot8` | `bot8.db` | `groups.db` | `bot8.log` |
| **9-Bot** | `.env.bot9.example` | `.env.bot9` | `bot9.db` | `groups.db` | `bot9.log` |

Har bir `.env.bot*` fayliga tegishli `BOT_TOKEN`, `ADMIN_IDS`, `API_ID`, `API_HASH` ma'lumotlarini kiriting.

---

## ▶️ Ishga tushirish usullari:

### 1-usul: Barcha botlarni birdaniga ishga tushirish (`run_all.py` orqali)
Mavjud barcha to'ldirilgan `.env.bot*` fayllarni avtomatik topib, barchasini parallel ishga tushiradi:
```bash
python run_all.py
```
*(To'xtatish uchun: `Ctrl + C`)*

### 2-usul: Har bir botni alohida terminalda ishga tushirish
```bash
python main.py .env.bot1
python main.py .env.bot2
python main.py .env.bot5
# va h.k.
```

---

## 🖥 Linux Serverda (Systemd orqali fonda ishlatish):

Loyiha papkasida tayyor service fayllari mavjud:
- `supertaxi_bot1.service`
- `supertaxi_bot2.service`
- `supertaxi_bot3.service`
- `supertaxi_bot4.service`
- `supertaxi_bot5.service`
- `supertaxi_bot6.service`
- `supertaxi_bot7.service`
- `supertaxi_bot8.service`
- `supertaxi_bot9.service`

### Serverga o'rnatish va ishga tushirish:
```bash
# Yangi service fayllarini tizim papkasiga nusxalash
sudo cp supertaxi_bot*.service /etc/systemd/system/

# Tizimni yangilash va xizmatlarni yoqish
sudo systemctl daemon-reload
sudo systemctl enable --now supertaxi_bot5 supertaxi_bot6 supertaxi_bot7 supertaxi_bot8 supertaxi_bot9
```

### Holatni tekshirish:
```bash
sudo systemctl status supertaxi_bot5 supertaxi_bot6 supertaxi_bot7 supertaxi_bot8 supertaxi_bot9
```

### Loglarni jonli kuzatish:
```bash
tail -f bot5.log
tail -f bot6.log
```
