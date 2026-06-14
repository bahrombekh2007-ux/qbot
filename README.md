# 🎓 QuizMaster Bot

Fayllardan **avtomatik test yaratuvchi** Telegram bot.
- 📄 PDF, DOCX, XLSX, TXT, PPTX formatlarni qo'llab-quvvatlaydi
- 🤖 **Bepul AI** - tashqi API kerak emas, lokal qoida-asosidagi generator
- 💎 Premium tariflar (Telegram Stars orqali to'lov)
- 🌐 WebApp orqali testlarni yechish va ulashish

---

## 🚀 Render.com ga deploy qilish (BEPUL)

### 1-qadam: Repoga yuklash

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/USERNAME/quizmaster-bot.git
git push -u origin main
```

### 2-qadam: Render.com da yaratish

1. [render.com](https://render.com) ga kiring (GitHub bilan)
2. **"New +"** → **"Web Service"**
3. GitHub repo ni tanlang
4. Quyidagi sozlamalar:
   - **Name:** quizmaster-bot
   - **Environment:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python -m bot`
   - **Plan:** Free

### 3-qadam: Environment Variables qo'shish

Render Dashboard → Environment → Add Environment Variable:

| Kalit | Qiymat |
|-------|--------|
| `BOT_TOKEN` | `7000000000:AAH...` (BotFather dan) |
| `BOT_USERNAME` | `YourBotUsername` |
| `JWT_SECRET` | Tasodifiy 32+ belgi (masalan: `openssl rand -hex 32`) |
| `ADMIN_IDS` | Telegram ID (masalan: `123456789`) |

> ⚠️ Boshqa o'zgaruvchilar **avtomatik** sozlanadi. `DATABASE_URL` SQLite uchun default.

### 4-qadam: Disk qo'shish (muhim!)

Render → Your Service → **Disks** → **Add Disk**:
- **Name:** quizmaster-data
- **Mount Path:** `/opt/render/project/src/data`
- **Size:** 1 GB

Bu SQLite bazasi uchun. **Disk bo'lmasa, restart da ma'lumotlar o'chib ketadi!**

### 5-qadam: WebApp URL sozlash

Deploy muvaffaqiyatli bo'lgandan keyin:
1. Render → Your Service → URL ni ko'ching (masalan: `https://quizmaster-bot.onrender.com`)
2. BotFather → `/setmenubutton` → WebApp URL ni o'sha URL ga o'rnating
3. Yoki Environment ga qo'shing: `WEBAPP_URL=https://quizmaster-bot.onrender.com`

---

## ⚙️ Lokal ishga tushirish

```bash
# Virtual env
python -m venv venv
source venv/bin/activate  # Linux/Mac
# yoki: venv\Scripts\activate  # Windows

# O'rnatish
pip install -r requirements.txt

# .env fayl
cp .env.example .env
# .env faylni tahrirlang: BOT_TOKEN va JWT_SECRET ni kiriting

# Ishga tushirish
python -m bot
```

---

## 📁 Loyiha tuzilmasi

```
quizmaster/
├── bot/
│   ├── config.py          # Sozlamalar
│   ├── keyboards.py       # Telegram klaviaturalar
│   ├── middlewares.py     # Auth, throttling
│   ├── __main__.py        # Entry point (bot + API)
│   ├── db/
│   │   ├── models.py      # SQLAlchemy modellari
│   │   └── session.py     # DB ulanish
│   ├── handlers/
│   │   ├── main.py        # /start, /help, /premium
│   │   ├── files.py       # Fayl yuklash va test yaratish
│   │   └── payments.py    # Telegram Stars to'lovlari
│   └── services/
│       ├── ai.py          # AI wrapper
│       ├── rule_based_ai.py  # Bepul lokal AI (asosiy)
│       ├── parser.py      # Fayl parserlari
│       └── subscription.py   # Tarif va limitlar
├── api/
│   └── server.py          # REST API (aiohttp)
├── webapp/
│   ├── index.html         # Telegram WebApp UI
│   ├── css/               # Stillar
│   └── js/                # JavaScript
├── requirements.txt
├── Procfile               # Render uchun
├── render.yaml            # Render blueprint
└── .env.example           # Sozlamalar namunasi
```

---

## 🆓 Nima uchun BEPUL?

- **AI:** Lokal qoida-asosidagi generator (OpenAI kerak emas)
- **Database:** SQLite (PostgreSQL kerak emas)
- **Cache:** MemoryStorage (Redis kerak emas)
- **Hosting:** Render.com Free tier

---

## 💎 Premium sozlash

### Telegram Stars
BotFather da to'lov yoqish talab qilinmaydi - Stars avtomatik ishlaydi.

### Payme/Click (O'zbekiston)
`.env` faylga qo'shing:
```
PROVIDER_PAYME=your_payme_merchant_id
PROVIDER_CLICK=your_click_service_id
```

---

## 🐛 Muammolar

**Bot javob bermayapti:**
- Render → Logs ni tekshiring
- BOT_TOKEN to'g'ri ekanligini tekshiring

**Database xatosi:**
- Disk o'rnatilganligini tekshiring
- `data/` papkasi write permission borligini tekshiring

**WebApp ochilmaydi:**
- WEBAPP_URL to'g'ri URL ekanligini tekshiring
- BotFather da WebApp URL ni to'g'ri o'rnatganligini tekshiring
