# AI Symptom Assistant

Flask asosidagi web ilova va Telegram bot. Tizim foydalanuvchi simptomlari, yoshi, jinsi va davomiyligini qabul qiladi, Gemini API yoki xavfsiz fallback orqali umumiy triage yo'l-yo'riq qaytaradi.

Muhim: bu loyiha tibbiy tashxis qo'ymaydi. Natijalar faqat umumiy axborot va yo'naltirish uchun.

## Imkoniyatlar
- Web orqali simptom tahlili
- Telegram bot orqali simptom tahlili
- Gemini API integratsiyasi
- API ishlamasa fallback tahlil
- Admin login va himoyalangan dashboard
- Telegram tahlillari uchun admin ko'rinishi
- Ko'p tilli interfeys: `uz_latn`, `uz_cyrl`, `en`, `ru`

## Stack
- Python 3.10+
- Flask 2.3.3
- SQLite
- Jinja2
- Bootstrap 5
- Google Gemini REST API

## Loyiha Tuzilishi
```text
AISymptom/
|- app.py
|- requirements.txt
|- .env.example
|- templates/
|- static/
`- symptom_checker.db
```

## Tez Ishga Tushirish
1. Virtual environment yarating.
```powershell
python -m venv venv
```

2. Uni yoqing.
```powershell
venv\Scripts\Activate.ps1
```

3. Dependency o'rnating.
```powershell
pip install -r requirements.txt
```

4. Namuna env fayldan lokal env yarating.
```powershell
Copy-Item .env.example .env
```

5. `.env` ni to'ldiring.
```env
GEMINI_API_KEY=your_real_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
GEMINI_RETRIES=3
AI_TIMEOUT_SECONDS=8

TELEGRAM_BOT_TOKEN=your_real_telegram_bot_token

FLASK_SECRET_KEY=replace_with_long_random_secret
ADMIN_USERNAME=admin
ADMIN_PASSWORD=replace_with_strong_password
# yoki:
# ADMIN_PASSWORD_HASH=pbkdf2:sha256:...

SESSION_COOKIE_SECURE=false
ADMIN_SESSION_MINUTES=30
ADMIN_LOGIN_WINDOW_SECONDS=900
ADMIN_LOGIN_MAX_ATTEMPTS=5
```

6. Ilovani ishga tushiring.
```powershell
venv\Scripts\python.exe app.py
```

7. Web manzil.
```text
http://127.0.0.1:5000
```

8. Admin sahifa.
```text
http://127.0.0.1:5000/admin/login
```

## Admin Xavfsizligi
Admin qismi uchun quyidagi himoyalar mavjud:
- Session cookie `HttpOnly`
- `SameSite=Lax`
- ixtiyoriy `SESSION_COOKIE_SECURE=true` orqali faqat HTTPS cookie
- CSRF token bilan himoyalangan login va logout
- brute-force login limit
- admin sahifalar uchun `no-store` cache policy
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: no-referrer`

Tavsiya:
- `ADMIN_PASSWORD` o'rniga `ADMIN_PASSWORD_HASH` ishlating
- `FLASK_SECRET_KEY` uzun va tasodifiy bo'lsin
- productionda albatta HTTPS ishlating va `SESSION_COOKIE_SECURE=true` qiling
- admin loginni reverse proxy bilan IP whitelist qilish yaxshi amaliyot

## Admin Dashboard
Admin dashboardda quyidagilar ko'rinadi:
- Telegram `username`
- telefon raqami, agar contact yuborilgan bo'lsa
- foydalanuvchi yozgan simptom matni
- AI qaytargan tahlil
- xavf darajasi
- tavsiya etilgan mutaxassis
- yozilgan vaqt

## Telegram Ishlash Tartibi
- `/start` bilan bot ishga tushadi
- `/analyze` bilan yangi tahlil boshlanadi
- bot simptom, yosh, jins va davomiylikni yig'adi
- natija formatlangan holda qaytadi
- analiz admin dashboard uchun bazaga yoziladi

Telefon raqami Telegram tomonidan avtomatik berilmaydi. U faqat foydalanuvchi `contact` yuborsa saqlanadi.

## Fallback Rejim
Quyidagi holatlarda fallback ishlaydi:
- `GEMINI_API_KEY` yo'q
- timeout yoki tarmoq xatosi
- Gemini `high demand`
- quota yoki billing muammosi
- bo'sh yoki noto'g'ri JSON javob

`high demand` holatida tizim fallbackdan oldin avtomatik qayta urinib ko'radi.

## Performance
Loyihada bir nechta optimizatsiya yoqilgan:
- Gemini timeout qisqartirilgan
- retry logikasi qo'shilgan
- i18n va language link cache
- SQLite `WAL` rejimi
- ba'zi ortiqcha DB so'rovlari olib tashlangan

## Muhim Fayllar
- [app.py](/D:/Proekt2026/AISymptom/app.py): backend, Telegram, Gemini, admin auth
- [templates/result.html](/D:/Proekt2026/AISymptom/templates/result.html): premium natija sahifasi
- [templates/admin_login.html](/D:/Proekt2026/AISymptom/templates/admin_login.html): admin login
- [templates/admin_dashboard.html](/D:/Proekt2026/AISymptom/templates/admin_dashboard.html): admin dashboard
- [templates/base.html](/D:/Proekt2026/AISymptom/templates/base.html): umumiy layout va navbar
- [static/css/styles.css](/D:/Proekt2026/AISymptom/static/css/styles.css): premium UI stillari

## Development
Sintaksis tekshiruv:
```powershell
venv\Scripts\python.exe -m py_compile app.py
```

Lokal import testi:
```powershell
venv\Scripts\python.exe -c "import app; print('ok')"
```

## Production Tavsiyalar
- SQLite o'rniga PostgreSQL ishlatish yaxshiroq
- Telegram polling o'rniga webhook ishlatish yaxshiroq
- Nginx yoki Caddy ortiga qo'yish kerak
- HTTPS majburiy bo'lishi kerak
- `.env` va DB backup fayllarini repo ga commit qilmang
- real API kalitlar oshkor bo'lsa darhol rotate qiling
