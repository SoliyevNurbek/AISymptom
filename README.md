# AI Symptom Assistant

Flask asosidagi web ilova va Telegram bot. Tizim foydalanuvchi simptomlari, yoshi, jinsi va simptom davomiyligini qabul qiladi, so'ng Gemini API orqali umumiy triage yo'l-yo'riq, xavf darajasi va tavsiya etilgan mutaxassisni qaytaradi.

Muhim: bu loyiha tibbiy tashxis vositasi emas. Natijalar faqat umumiy axborot va yo'naltirish uchun.

## Nimalar Bor
- Web interfeys
- Telegram bot
- Gemini API integratsiyasi
- API ishlamasa fallback tahlil
- SQLite tarix saqlash
- Ko'p tilli interfeys
  `uz_latn`, `uz_cyrl`, `en`, `ru`

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
1. Virtual environment yarating:
```powershell
python -m venv venv
```

2. Uni yoqing:
```powershell
venv\Scripts\Activate.ps1
```

3. Dependency o'rnating:
```powershell
pip install -r requirements.txt
```

4. Env fayl yarating:
```powershell
Copy-Item .env.example .env
```

5. `.env` ni to'ldiring:
```env
GEMINI_API_KEY=your_real_gemini_api_key
TELEGRAM_BOT_TOKEN=your_real_telegram_bot_token
```

6. Ilovani ishga tushiring:
```powershell
venv\Scripts\python.exe app.py
```

7. Web:
```text
http://127.0.0.1:5000
```

8. Telegram:
- botni oching
- `/start` yuboring
- `/language` bilan til tanlang
- `/analyze` bilan tahlil boshlang

## Konfiguratsiya
Qo'llab-quvvatlanadigan environment variable lar:

```env
GEMINI_API_KEY=your_real_gemini_api_key
TELEGRAM_BOT_TOKEN=your_real_telegram_bot_token
```

`.env` gitga kirmaydi. Namuna fayl: [.env.example](/D:/Proekt2026/AISymptom/.env.example)

## Qanday Ishlaydi
1. Foydalanuvchi web yoki Telegram orqali simptom yuboradi.
2. Tizim yosh, jins va davomiylikni yig'adi.
3. Backend Gemini uchun structured prompt tayyorlaydi.
4. Gemini JSON formatda quyidagilarni qaytaradi:
   `risk_level`, `specialist`, `summary`, `advice`, `possible_causes`, `when_to_seek_help`, `emergency`
5. Natija tanlangan tilga va kanalga mos formatlanadi.
6. Agar API ishlamasa, xavfsiz fallback javob ishlatiladi.
7. Tahlil SQLite bazaga yoziladi.

## Web
- Til switcher yuqori o'ng burchakda
- Query param bilan ham ishlaydi:
  `/?lang=uz_latn`
  `/?lang=uz_cyrl`
  `/?lang=en`
  `/?lang=ru`

## Telegram
- Long-polling asosida ishlaydi
- Qo'llab-quvvatlanadigan buyruqlar:
  `/start`
  `/analyze`
  `/help`
  `/cancel`
  `/language`
- Natija ikonlar va bo'limlar bilan formatlanadi
- Til tanlansa, keyingi javoblar o'sha tilda chiqadi

## Fallback Rejim
Quyidagi holatlarda fallback javob ishlaydi:
- `GEMINI_API_KEY` yo'q
- API quota yoki billing muammosi
- timeout yoki tarmoq xatosi
- Gemini bo'sh yoki noto'g'ri JSON qaytarsa

## Muhim Fayllar
- [app.py](/D:/Proekt2026/AISymptom/app.py): asosiy backend, Gemini, Telegram, i18n, fallback
- [templates/app.html](/D:/Proekt2026/AISymptom/templates/app.html): web forma
- [templates/result.html](/D:/Proekt2026/AISymptom/templates/result.html): natija sahifasi
- [templates/history.html](/D:/Proekt2026/AISymptom/templates/history.html): tarix sahifasi
- [templates/base.html](/D:/Proekt2026/AISymptom/templates/base.html): umumiy layout va web til switcher
- [static/js/app.js](/D:/Proekt2026/AISymptom/static/js/app.js): frontend form behaviour

## Xavfsizlik
- API kalitlarni repoga commit qilmang
- `.env` lokal saqlansin
- Bu loyiha diagnostika vositasi emas
- Og'ir simptomlarda foydalanuvchini darhol shifokor yoki tez yordamga yo'naltirish kerak

## Hozirgi Cheklovlar
- Telegram integratsiya long-pollingda, webhook emas
- Network bo'lmasa real Gemini tekshiruvi ishlamaydi
- SQLite lokal storage sifatida ishlatiladi

## Development
Sintaksis tekshiruv:
```powershell
venv\Scripts\python.exe -m py_compile app.py
```

Lokal import testi:
```powershell
venv\Scripts\python.exe -c "import app; print('ok')"
```

## Eslatma
Kod SDKsiz, `urllib` orqali Gemini REST API bilan ishlaydi. Bu dependency sonini kichik tutadi va deployni soddalashtiradi.
