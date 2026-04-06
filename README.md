# AI Alomat Tekshiruvi

Gemini API bilan ishlovchi Flask ilova. Foydalanuvchi alomatlari, yoshi, jinsi va davomiyligini kiritadi, tizim esa umumiy xavf darajasi, tavsiya etilgan mutaxassis va amaliy tavsiyalarni ko'rsatadi.

Muhim: bu ilova tibbiy tashxis bermaydi. Natijalar faqat umumiy yo'l-yo'riq uchun.

## Imkoniyatlar
- Gemini API orqali structured AI tahlil
- API ishlamasa xavfsiz fallback tahlil
- Iconkali natija sahifasi va yumshoq status xabarlari
- Responsive Bootstrap UI
- `.env` orqali maxfiy kalit boshqaruvi

## Texnologiyalar
- Python 3.10+
- Flask 2.3.3
- Google Gemini API
- Jinja2 templates
- Bootstrap 5

## Loyiha Tuzilishi
```text
AISymptom/
|- app.py
|- requirements.txt
|- .env.example
|- templates/
|  |- base.html
|  |- index.html
|  |- app.html
|  |- result.html
|  `- history.html
`- static/
   |- css/
   |  `- styles.css
   `- js/
      `- app.js
```

## Tez Start
1. Virtual environment yarating:
```powershell
python -m venv venv
```

2. Uni yoqing:
```powershell
venv\Scripts\Activate.ps1
```

3. Kutubxonalarni o'rnating:
```powershell
pip install -r requirements.txt
```

4. `.env` fayl yarating:
```powershell
Copy-Item .env.example .env
```

5. `.env` ichiga Gemini kalit yozing:
```env
GEMINI_API_KEY=your_real_gemini_api_key
```

6. Ilovani ishga tushiring:
```powershell
venv\Scripts\python.exe app.py
```

7. Brauzerda oching:
```text
http://127.0.0.1:5000
```

## Konfiguratsiya
Qo'llab-quvvatlanadigan environment variable:

```env
GEMINI_API_KEY=your_real_gemini_api_key
```

`.env.example` repoga kiradi, `.env` esa `.gitignore` orqali yopilgan.

## Qanday Ishlaydi
1. Foydalanuvchi alomatlarni forma orqali yuboradi.
2. Backend prompt tayyorlaydi va Gemini `generateContent` endpointiga so'rov yuboradi.
3. Gemini JSON formatda quyidagi maydonlarni qaytaradi:
   `risk_level`, `specialist`, `summary`, `advice`, `possible_causes`, `when_to_seek_help`, `emergency`.
4. Javob UI uchun boyitiladi: iconlar, ranglar va tavsiya bloklari.
5. API xatosi bo'lsa fallback tahlil ko'rsatiladi.

## Muhim Fayllar
- `app.py`: backend, API integratsiya va fallback logikasi
- `templates/app.html`: alomat kiritish formasi
- `templates/result.html`: tahlil natijalari UI
- `static/css/styles.css`: dizayn va komponent stillari
- `static/js/app.js`: forma validatsiyasi va loading holatlari

## Fallback Rejimi
Quyidagi holatlarda tizim avtomatik fallback tahlilga o'tadi:
- Gemini API kaliti yo'q bo'lsa
- API limit yoki billing muammosi bo'lsa
- Tarmoq yoki timeout xatosi bo'lsa
- Gemini noto'g'ri formatdagi javob qaytarsa

Bu rejim foydalanuvchini bo'sh sahifada qoldirmaydi va minimal xavfsiz tavsiyalarni chiqaradi.

## Xavfsizlik Eslatmasi
- API kalitni hech qachon repoga commit qilmang
- `.env` lokal saqlansin
- Bu ilova diagnostika vositasi emas
- Og'ir simptomlarda foydalanuvchi darhol tibbiy yordamga yo'naltirilishi kerak

## Keyingi Yaxshilanishlar
- Tahlil tarixini haqiqiy bazaga saqlash
- Unit test va integration test qo'shish
- Logging va monitoring qo'shish
- Rate limiting
- Ko'p tilli qo'llab-quvvatlash

## Rivojlantirish Uchun Eslatma
Kod hozir SDKsiz, standart `urllib` orqali Gemini REST API bilan ishlaydi. Bu dependency sonini kichik tutadi va deployni soddalashtiradi.
