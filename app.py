from flask import Flask, abort, render_template, request
import html
import json
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from urllib.parse import urlencode

app = Flask(__name__)
app.config["AI_TIMEOUT_SECONDS"] = 12
app.config["TELEGRAM_POLL_TIMEOUT_SECONDS"] = 25
app.config["TELEGRAM_RETRY_DELAY_SECONDS"] = 5
app.config["TELEGRAM_SESSION_TIMEOUT_SECONDS"] = 1800
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024
app.config["MAX_SYMPTOMS_LENGTH"] = 1200
app.config["MAX_TELEGRAM_MESSAGE_LENGTH"] = 2000
app.config["WEB_RATE_LIMIT_WINDOW_SECONDS"] = 60
app.config["WEB_RATE_LIMIT_MAX_REQUESTS"] = 12

RATE_LIMIT_LOCK = threading.Lock()
WEB_RATE_LIMIT_STATE = {}


def load_env_file():
    env_path = ".env"
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ[key] = value


load_env_file()


def init_db():
    conn = sqlite3.connect("symptom_checker.db")
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS analyses
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  symptoms TEXT,
                  age INTEGER,
                  gender TEXT,
                  duration TEXT,
                  risk_level TEXT,
                  specialist TEXT,
                  advice TEXT,
                  emergency BOOLEAN,
                  date TIMESTAMP)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS telegram_sessions
                 (chat_id INTEGER PRIMARY KEY,
                  step TEXT NOT NULL,
                  symptoms TEXT,
                  age INTEGER,
                  gender TEXT,
                  updated_at TIMESTAMP NOT NULL)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS telegram_users
                 (chat_id INTEGER PRIMARY KEY,
                  language TEXT NOT NULL,
                  updated_at TIMESTAMP NOT NULL)"""
    )
    conn.commit()
    conn.close()


DURATION_LABELS = {
    "uz_latn": {
        "hours": "24 soatdan kam",
        "1-3_days": "1-3 kun",
        "4-7_days": "4-7 kun",
        "1-2_weeks": "1-2 hafta",
        "2-4_weeks": "2-4 hafta",
        "more_than_month": "Bir oydan ko'proq",
    },
    "uz_cyrl": {
        "hours": "24 соатдан кам",
        "1-3_days": "1-3 кун",
        "4-7_days": "4-7 кун",
        "1-2_weeks": "1-2 ҳафта",
        "2-4_weeks": "2-4 ҳафта",
        "more_than_month": "Бир ойдан кўпроқ",
    },
    "en": {
        "hours": "Less than 24 hours",
        "1-3_days": "1-3 days",
        "4-7_days": "4-7 days",
        "1-2_weeks": "1-2 weeks",
        "2-4_weeks": "2-4 weeks",
        "more_than_month": "More than a month",
    },
    "ru": {
        "hours": "Менее 24 часов",
        "1-3_days": "1-3 дня",
        "4-7_days": "4-7 дней",
        "1-2_weeks": "1-2 недели",
        "2-4_weeks": "2-4 недели",
        "more_than_month": "Больше месяца",
    },
}

DURATION_INPUT_ALIASES = {
    "hours": ["24 soatdan kam", "24 соатдан кам", "less than 24 hours", "24h", "24 hours"],
    "1-3_days": ["1-3 kun", "1-3 кун", "1-3 days"],
    "4-7_days": ["4-7 kun", "4-7 кун", "4-7 days"],
    "1-2_weeks": ["1-2 hafta", "1-2 ҳафта", "1-2 weeks"],
    "2-4_weeks": ["2-4 hafta", "2-4 ҳафта", "2-4 weeks"],
    "more_than_month": ["bir oydan ko'proq", "бир ойдан кўпроқ", "more than a month", "more than month"],
}

GENDER_LABELS = {
    "uz_latn": {"male": "Erkak", "female": "Ayol"},
    "uz_cyrl": {"male": "Эркак", "female": "Аёл"},
    "en": {"male": "Male", "female": "Female"},
}

GENDER_INPUT_ALIASES = {
    "male": ["erkak", "эркак", "male", "man", "m"],
    "female": ["ayol", "аёл", "female", "woman", "f"],
}

GENDER_LABELS["ru"] = {"male": "Мужчина", "female": "Женщина"}
GENDER_INPUT_ALIASES["male"].extend(["мужчина"])
GENDER_INPUT_ALIASES["female"].extend(["женщина"])

DURATION_INPUT_ALIASES["hours"].extend(["менее 24 часов"])
DURATION_INPUT_ALIASES["1-3_days"].extend(["1-3 дня"])
DURATION_INPUT_ALIASES["4-7_days"].extend(["4-7 дней"])
DURATION_INPUT_ALIASES["1-2_weeks"].extend(["1-2 недели"])
DURATION_INPUT_ALIASES["2-4_weeks"].extend(["2-4 недели"])
DURATION_INPUT_ALIASES["more_than_month"].extend(["больше месяца"])

GENDER_INPUT_ALIASES["male"].extend(["мужчина"])
GENDER_INPUT_ALIASES["female"].extend(["женщина"])

LANGUAGE_CHOICES = [
    ("🇺🇿 O'zbek", "uz_latn"),
    ("🇺🇿 Ўзбекча", "uz_cyrl"),
    ("🇬🇧 English", "en"),
]

LANGUAGE_CHOICES.append(("🇷🇺 Русский", "ru"))

LANGUAGE_LABELS = {
    "uz_latn": "O'zbek",
    "uz_cyrl": "Ўзбекча",
    "en": "English",
}

LANGUAGE_LABELS["ru"] = "Русский"

SPECIALIST_LABELS = {
    "Favqulodda tibbiyot": {"uz_latn": "Favqulodda tibbiyot", "uz_cyrl": "Шошилинч тиббиёт", "en": "Emergency medicine"},
    "Umumiy amaliyot shifokori": {"uz_latn": "Umumiy amaliyot shifokori", "uz_cyrl": "Умумий амалиёт шифокори", "en": "General practitioner"},
    "Kardiolog": {"uz_latn": "Kardiolog", "uz_cyrl": "Кардиолог", "en": "Cardiologist"},
    "Pulmonolog": {"uz_latn": "Pulmonolog", "uz_cyrl": "Пульмонолог", "en": "Pulmonologist"},
    "Nevrolog": {"uz_latn": "Nevrolog", "uz_cyrl": "Невролог", "en": "Neurologist"},
    "Gastroenterolog": {"uz_latn": "Gastroenterolog", "uz_cyrl": "Гастроэнтеролог", "en": "Gastroenterologist"},
    "Dermatolog": {"uz_latn": "Dermatolog", "uz_cyrl": "Дерматолог", "en": "Dermatologist"},
    "Infeksionist": {"uz_latn": "Infeksionist", "uz_cyrl": "Инфекционист", "en": "Infectious disease specialist"},
}

SPECIALIST_LABELS["Favqulodda tibbiyot"]["ru"] = "Неотложная медицина"
SPECIALIST_LABELS["Umumiy amaliyot shifokori"]["ru"] = "Врач общей практики"
SPECIALIST_LABELS["Kardiolog"]["ru"] = "Кардиолог"
SPECIALIST_LABELS["Pulmonolog"]["ru"] = "Пульмонолог"
SPECIALIST_LABELS["Nevrolog"]["ru"] = "Невролог"
SPECIALIST_LABELS["Gastroenterolog"]["ru"] = "Гастроэнтеролог"
SPECIALIST_LABELS["Dermatolog"]["ru"] = "Дерматолог"
SPECIALIST_LABELS["Infeksionist"]["ru"] = "Инфекционист"

RISK_META = {
    "past": {
        "label": {"uz_latn": "Past", "uz_cyrl": "Паст", "en": "Low"},
        "class_name": "past",
        "icon": "fa-shield-heart",
        "summary": {
            "uz_latn": "Hozircha xavf nisbatan past ko'rinadi, lekin alomatlarni kuzatishda davom eting.",
            "uz_cyrl": "Ҳозирча хавф нисбатан паст кўринади, лекин аломатларни кузатишда давом этинг.",
            "en": "The current risk appears relatively low, but continue monitoring your symptoms.",
        },
    },
    "o'rta": {
        "label": {"uz_latn": "O'rta", "uz_cyrl": "Ўрта", "en": "Medium"},
        "class_name": "orta",
        "icon": "fa-stethoscope",
        "summary": {
            "uz_latn": "Alomatlar shifokor bilan rejalashtirilgan maslahatni talab qilishi mumkin.",
            "uz_cyrl": "Аломатлар шифокор билан режалаштирилган маслаҳатни талаб қилиши мумкин.",
            "en": "Your symptoms may require a planned consultation with a doctor.",
        },
    },
    "yuqori": {
        "label": {"uz_latn": "Yuqori", "uz_cyrl": "Юқори", "en": "High"},
        "class_name": "yuqori",
        "icon": "fa-triangle-exclamation",
        "summary": {
            "uz_latn": "Alomatlar jiddiy holatga mos kelishi mumkin. Tezroq tibbiy yordam oling.",
            "uz_cyrl": "Аломатлар жиддий ҳолатга мос келиши мумкин. Тезроқ тиббий ёрдам олинг.",
            "en": "The symptoms may indicate a serious condition. Seek medical help as soon as possible.",
        },
    },
}

RISK_META["past"]["label"]["ru"] = "Низкий"
RISK_META["past"]["summary"]["ru"] = "Сейчас риск выглядит сравнительно низким, но продолжайте наблюдать за симптомами."
RISK_META["o'rta"]["label"]["ru"] = "Средний"
RISK_META["o'rta"]["summary"]["ru"] = "Ваши симптомы могут требовать плановой консультации с врачом."
RISK_META["yuqori"]["label"]["ru"] = "Высокий"
RISK_META["yuqori"]["summary"]["ru"] = "Симптомы могут указывать на серьёзное состояние. Обратитесь за медицинской помощью как можно скорее."

I18N = {
    "uz_latn": {
        "bot_description": "🩺 Alomatlaringiz uchun AI yordamida yo'l-yo'riq oling.\nBu faqat umumiy xabardorlik uchun ta'limiy vosita.\n\n⚠️ Tibbiy tashxis emas\n🤖 AI yordamida\n🚑 Favqulodda ogohlantirishlar\n📋 Tez alomat tekshiruvi",
        "bot_short_description": "🩺 AI yordamida tez alomat tekshiruvi va umumiy yo'l-yo'riq.",
        "welcome": "<b>🩺 AI Symptom Assistant</b>\n\n🤖 <b>Alomatlaringiz uchun AI yordamida yo'l-yo'riq oling.</b>\nℹ️ Bu faqat umumiy xabardorlik uchun ta'limiy vosita.\n\n⚠️ <b>Tibbiy tashxis emas</b>\n🤖 <b>AI yordamida</b>\n🚑 <b>Favqulodda ogohlantirishlar</b>\n📋 <b>Tez alomat tekshiruvi</b>",
        "commands_title": "Quyidagi buyruqlardan foydalaning:",
        "help": "<b>❓ Yordam</b>\n\n🤖 Bot simptomlarni navbat bilan so'raydi va AI tahlilini qaytaradi.\n\n<b>Buyruqlar:</b>\n▶️ /start - bosh menyu\n📝 /analyze - yangi simptom tahlili\n🌐 /language - tilni o'zgartirish\n🛑 /cancel - joriy jarayonni bekor qilish\n\n📌 Avval alomat yuborasiz, keyin yosh, jins va davomiylik tanlanadi.",
        "new_analysis": "<b>📝 Yangi tahlil boshlandi</b>\n\nAlomatlaringizni bitta xabarda yozing.\nMasalan: <i>3 kundan beri isitma, yo'tal va tomoq og'rig'i</i>",
        "ask_age": "🎂 <b>Yoshingizni kiriting</b>\nFaqat son yuboring, masalan: <b>28</b>",
        "ask_gender": "👤 <b>Jinsni tanlang:</b>",
        "ask_duration": "⏳ <b>Alomatlar qancha vaqtdan beri davom etmoqda?</b>",
        "processing": "⏳ <b>Tahlil qilinmoqda...</b>\nAI javobi tayyor bo'lishi uchun biroz kuting.",
        "cancelled": "🛑 Joriy jarayon bekor qilindi.",
        "text_only": "⚠️ Faqat matnli xabar yuboring.",
        "invalid_age": "⚠️ Yosh faqat son bo'lishi kerak. Masalan: <b>28</b>",
        "age_range": "⚠️ Yosh 1 dan 120 gacha bo'lishi kerak.",
        "invalid_gender": "⚠️ Variantlardan birini tanlang: Erkak yoki Ayol.",
        "invalid_duration": "⚠️ Tugmalardan birini tanlang.",
        "language_title": "<b>🌐 Tilni tanlang</b>",
        "language_changed": "✅ Til yangilandi: {language}",
        "result_title": "🩺 Tahlil Natijasi",
        "risk_level": "Xavf darajasi",
        "specialist": "Tavsiya etilgan mutaxassis",
        "emergency": "Favqulodda holat",
        "summary": "Qisqa xulosa",
        "advice": "Asosiy tavsiyalar",
        "causes": "Ehtimoliy izohlar",
        "seek_help": "Qachon darhol yordam olish kerak",
        "medical_disclaimer": "Bu natija tibbiy tashxis emas. Og'ir yoki kuchayib borayotgan alomatlarda shifokorga murojaat qiling.",
        "warning_prefix": "ℹ️ <b>Eslatma:</b> ",
        "server_error_safe": "⚠️ Server ichida xatolik bo'ldi, lekin xavfsiz natija chiqarildi. Qayta urinib ko'rishingiz mumkin.",
        "yes": "Ha",
        "no": "Yo'q",
        "new_analysis_btn": "📝 Yangi tahlil",
        "help_btn": "❓ Yordam",
        "home_btn": "🏠 Bosh menyu",
        "language_btn": "🌐 Til",
        "male": "Erkak",
        "female": "Ayol",
        "risk_badges": {"past": "🟢 Past xavf", "o'rta": "🟡 O'rta xavf", "yuqori": "🔴 Yuqori xavf"},
        "fallback_warning_missing_key": "`.env` ichida haqiqiy GEMINI_API_KEY topilmadi.",
        "fallback_warning_api": "{message} Fallback tahlil ishlatildi.",
        "fallback_empty": "Gemini bo'sh javob qaytardi, fallback tahlil ishlatildi.",
        "fallback_bad_json": "Gemini JSON formatda javob bermadi, fallback tahlil ishlatildi.",
        "api_gemini_error": "Gemini API bilan ulanishda xatolik bo'ldi.",
        "api_gemini_quota": "Gemini hisobida limit yoki billing muammosi bor.",
        "fallback_summary": "Server xatosi tufayli xavfsiz fallback natija ko'rsatildi.",
    },
    "uz_cyrl": {
        "bot_description": "🩺 Аломатларингиз учун AI ёрдамида йўл-йўриқ олинг.\nБу фақат умумий хабардорлик учун таълимий восита.\n\n⚠️ Тиббий ташхис эмас\n🤖 AI ёрдамида\n🚑 Фавқулодда огоҳлантиришлар\n📋 Тез аломат текшируви",
        "bot_short_description": "🩺 AI ёрдамида тез аломат текшируви ва умумий йўл-йўриқ.",
        "welcome": "<b>🩺 AI Symptom Assistant</b>\n\n🤖 <b>Аломатларингиз учун AI ёрдамида йўл-йўриқ олинг.</b>\nℹ️ Бу фақат умумий хабардорлик учун таълимий восита.\n\n⚠️ <b>Тиббий ташхис эмас</b>\n🤖 <b>AI ёрдамида</b>\n🚑 <b>Фавқулодда огоҳлантиришлар</b>\n📋 <b>Тез аломат текшируви</b>",
        "commands_title": "Қуйидаги буйруқлардан фойдаланинг:",
        "help": "<b>❓ Ёрдам</b>\n\n🤖 Бот симптомларни навбат билан сўрайди ва AI таҳлилини қайтаради.\n\n<b>Буйруқлар:</b>\n▶️ /start - бош меню\n📝 /analyze - янги симптом таҳлили\n🌐 /language - тилни ўзгартириш\n🛑 /cancel - жорий жараённи бекор қилиш\n\n📌 Аввал аломат юборасиз, кейин ёш, жинс ва давомийлик танланади.",
        "new_analysis": "<b>📝 Янги таҳлил бошланди</b>\n\nАломатларингизни битта хабарда ёзинг.\nМасалан: <i>3 кундан бери иситма, йўтал ва томоқ оғриғи</i>",
        "ask_age": "🎂 <b>Ёшингизни киритинг</b>\nФақат сон юборинг, масалан: <b>28</b>",
        "ask_gender": "👤 <b>Жинсни танланг:</b>",
        "ask_duration": "⏳ <b>Аломатлар қанча вақтдан бери давом этмоқда?</b>",
        "processing": "⏳ <b>Таҳлил қилинмоқда...</b>\nAI жавоби тайёр бўлиши учун бироз кутинг.",
        "cancelled": "🛑 Жорий жараён бекор қилинди.",
        "text_only": "⚠️ Фақат матнли хабар юборинг.",
        "invalid_age": "⚠️ Ёш фақат сон бўлиши керак. Масалан: <b>28</b>",
        "age_range": "⚠️ Ёш 1 дан 120 гача бўлиши керак.",
        "invalid_gender": "⚠️ Вариантлардан бирини танланг: Эркак ёки Аёл.",
        "invalid_duration": "⚠️ Тугмалардан бирини танланг.",
        "language_title": "<b>🌐 Тилни танланг</b>",
        "language_changed": "✅ Тил янгиланди: {language}",
        "result_title": "🩺 Таҳлил Натижаси",
        "risk_level": "Хавф даражаси",
        "specialist": "Тавсия этилган мутахассис",
        "emergency": "Фавқулодда ҳолат",
        "summary": "Қисқа хулоса",
        "advice": "Асосий тавсиялар",
        "causes": "Эҳтимолий изоҳлар",
        "seek_help": "Қачон дарҳол ёрдам олиш керак",
        "medical_disclaimer": "Бу натижа тиббий ташхис эмас. Оғир ёки кучайиб бораётган аломатларда шифокорга мурожаат қилинг.",
        "warning_prefix": "ℹ️ <b>Эслатма:</b> ",
        "server_error_safe": "⚠️ Сервер ичида хатолик бўлди, лекин хавфсиз натижа чиқарилди. Қайта уриниб кўришингиз мумкин.",
        "yes": "Ҳа",
        "no": "Йўқ",
        "new_analysis_btn": "📝 Янги таҳлил",
        "help_btn": "❓ Ёрдам",
        "home_btn": "🏠 Бош меню",
        "language_btn": "🌐 Тил",
        "male": "Эркак",
        "female": "Аёл",
        "risk_badges": {"past": "🟢 Паст хавф", "o'rta": "🟡 Ўрта хавф", "yuqori": "🔴 Юқори хавф"},
        "fallback_warning_missing_key": "`.env` ичида ҳақиқий GEMINI_API_KEY топилмади.",
        "fallback_warning_api": "{message} Fallback таҳлил ишлатилди.",
        "fallback_empty": "Gemini бўш жавоб қайтарди, fallback таҳлил ишлатилди.",
        "fallback_bad_json": "Gemini JSON форматда жавоб бермади, fallback таҳлил ишлатилди.",
        "api_gemini_error": "Gemini API билан уланишда хатолик бўлди.",
        "api_gemini_quota": "Gemini ҳисоби лимити ёки billing муаммоси бор.",
        "fallback_summary": "Сервер хатоси туфайли хавфсиз fallback натижа кўрсатилди.",
    },
    "en": {
        "bot_description": "🩺 Get AI-guided symptom direction.\nThis is an educational tool for general awareness only.\n\n⚠️ Not a medical diagnosis\n🤖 AI-assisted\n🚑 Emergency alerts\n📋 Quick symptom check",
        "bot_short_description": "🩺 Quick AI-assisted symptom check and general guidance.",
        "welcome": "<b>🩺 AI Symptom Assistant</b>\n\n🤖 <b>Get AI-guided direction for your symptoms.</b>\nℹ️ This is an educational tool for general awareness only.\n\n⚠️ <b>Not a medical diagnosis</b>\n🤖 <b>AI-assisted</b>\n🚑 <b>Emergency alerts</b>\n📋 <b>Quick symptom check</b>",
        "commands_title": "Use these commands:",
        "help": "<b>❓ Help</b>\n\n🤖 The bot asks for symptoms step by step and returns an AI analysis.\n\n<b>Commands:</b>\n▶️ /start - main menu\n📝 /analyze - start a new symptom analysis\n🌐 /language - change language\n🛑 /cancel - cancel current flow\n\n📌 First send symptoms, then age, gender, and duration.",
        "new_analysis": "<b>📝 New analysis started</b>\n\nSend your symptoms in one message.\nExample: <i>I have had fever, cough, and sore throat for 3 days</i>",
        "ask_age": "🎂 <b>Enter your age</b>\nSend numbers only, for example: <b>28</b>",
        "ask_gender": "👤 <b>Select gender:</b>",
        "ask_duration": "⏳ <b>How long have the symptoms been going on?</b>",
        "processing": "⏳ <b>Analyzing...</b>\nPlease wait while the AI prepares the response.",
        "cancelled": "🛑 The current flow was cancelled.",
        "text_only": "⚠️ Please send text messages only.",
        "invalid_age": "⚠️ Age must be a number. Example: <b>28</b>",
        "age_range": "⚠️ Age must be between 1 and 120.",
        "invalid_gender": "⚠️ Please choose one option: Male or Female.",
        "invalid_duration": "⚠️ Please choose one of the buttons.",
        "language_title": "<b>🌐 Choose a language</b>",
        "language_changed": "✅ Language updated: {language}",
        "result_title": "🩺 Analysis Result",
        "risk_level": "Risk level",
        "specialist": "Recommended specialist",
        "emergency": "Emergency",
        "summary": "Summary",
        "advice": "Main advice",
        "causes": "Possible explanations",
        "seek_help": "When to seek urgent help",
        "medical_disclaimer": "This result is not a medical diagnosis. Seek medical care if symptoms are severe or worsening.",
        "warning_prefix": "ℹ️ <b>Note:</b> ",
        "server_error_safe": "⚠️ An internal server error occurred, but a safe fallback result was shown. You can try again.",
        "yes": "Yes",
        "no": "No",
        "new_analysis_btn": "📝 New analysis",
        "help_btn": "❓ Help",
        "home_btn": "🏠 Main menu",
        "language_btn": "🌐 Language",
        "male": "Male",
        "female": "Female",
        "risk_badges": {"past": "🟢 Low risk", "o'rta": "🟡 Medium risk", "yuqori": "🔴 High risk"},
        "fallback_warning_missing_key": "A real GEMINI_API_KEY was not found in `.env`.",
        "fallback_warning_api": "{message} A fallback analysis was used.",
        "fallback_empty": "Gemini returned an empty response, so a fallback analysis was used.",
        "fallback_bad_json": "Gemini did not return valid JSON, so a fallback analysis was used.",
        "api_gemini_error": "There was an error connecting to the Gemini API.",
        "api_gemini_quota": "There is a Gemini account quota or billing issue.",
        "fallback_summary": "A safe fallback result was shown due to a server-side issue.",
    },
}

I18N["ru"] = {
    "bot_description": "🩺 Получите AI-подсказки по своим симптомам.\nЭто образовательный инструмент только для общей информированности.\n\n⚠️ Это не медицинский диагноз\n🤖 С помощью AI\n🚑 Экстренные предупреждения\n📋 Быстрая проверка симптомов",
    "bot_short_description": "🩺 Быстрая AI-проверка симптомов и общие рекомендации.",
    "welcome": "<b>🩺 AI Symptom Assistant</b>\n\n🤖 <b>Получите AI-подсказки по своим симптомам.</b>\nℹ️ Это образовательный инструмент только для общей информированности.\n\n⚠️ <b>Это не медицинский диагноз</b>\n🤖 <b>С помощью AI</b>\n🚑 <b>Экстренные предупреждения</b>\n📋 <b>Быстрая проверка симптомов</b>",
    "commands_title": "Используйте команды:",
    "help": "<b>❓ Помощь</b>\n\n🤖 Бот пошагово спрашивает о симптомах и возвращает AI-анализ.\n\n<b>Команды:</b>\n▶️ /start - главное меню\n📝 /analyze - новый анализ симптомов\n🌐 /language - сменить язык\n🛑 /cancel - отменить текущий процесс\n\n📌 Сначала вы отправляете симптомы, затем возраст, пол и длительность.",
    "new_analysis": "<b>📝 Новый анализ начат</b>\n\nОпишите симптомы одним сообщением.\nПример: <i>У меня 3 дня температура, кашель и боль в горле</i>",
    "ask_age": "🎂 <b>Введите ваш возраст</b>\nОтправьте только число, например: <b>28</b>",
    "ask_gender": "👤 <b>Выберите пол:</b>",
    "ask_duration": "⏳ <b>Как долго продолжаются симптомы?</b>",
    "processing": "⏳ <b>Идёт анализ...</b>\nПожалуйста, подождите, пока AI подготовит ответ.",
    "cancelled": "🛑 Текущий процесс отменён.",
    "text_only": "⚠️ Пожалуйста, отправляйте только текстовые сообщения.",
    "invalid_age": "⚠️ Возраст должен быть числом. Пример: <b>28</b>",
    "age_range": "⚠️ Возраст должен быть от 1 до 120.",
    "invalid_gender": "⚠️ Пожалуйста, выберите один вариант: Мужчина или Женщина.",
    "invalid_duration": "⚠️ Пожалуйста, выберите один из вариантов.",
    "language_title": "<b>🌐 Выберите язык</b>",
    "language_changed": "✅ Язык обновлён: {language}",
    "result_title": "🩺 Результат анализа",
    "risk_level": "Уровень риска",
    "specialist": "Рекомендуемый специалист",
    "emergency": "Экстренная ситуация",
    "summary": "Краткий вывод",
    "advice": "Основные рекомендации",
    "causes": "Возможные объяснения",
    "seek_help": "Когда срочно обращаться за помощью",
    "medical_disclaimer": "Этот результат не является медицинским диагнозом. Обратитесь за медицинской помощью, если симптомы тяжёлые или усиливаются.",
    "warning_prefix": "ℹ️ <b>Примечание:</b> ",
    "server_error_safe": "⚠️ Произошла внутренняя ошибка сервера, но был показан безопасный резервный результат. Вы можете попробовать снова.",
    "yes": "Да",
    "no": "Нет",
    "new_analysis_btn": "📝 Новый анализ",
    "help_btn": "❓ Помощь",
    "home_btn": "🏠 Главное меню",
    "language_btn": "🌐 Язык",
    "male": "Мужчина",
    "female": "Женщина",
    "risk_badges": {"past": "🟢 Низкий риск", "o'rta": "🟡 Средний риск", "yuqori": "🔴 Высокий риск"},
    "fallback_warning_missing_key": "В `.env` не найден реальный GEMINI_API_KEY.",
    "fallback_warning_api": "{message} Был использован резервный анализ.",
    "fallback_empty": "Gemini вернул пустой ответ, поэтому был использован резервный анализ.",
    "fallback_bad_json": "Gemini не вернул корректный JSON, поэтому был использован резервный анализ.",
    "api_gemini_error": "Произошла ошибка при подключении к Gemini API.",
    "api_gemini_quota": "Есть проблема с квотой или биллингом Gemini.",
    "fallback_summary": "Из-за серверной ошибки был показан безопасный резервный результат.",
}

TELEGRAM_POLL_THREAD = None
TELEGRAM_POLL_STARTED = False
TELEGRAM_POLL_LOCK = threading.Lock()

SPECIALIST_ICONS = {
    "Favqulodda tibbiyot": "fa-truck-medical",
    "Umumiy amaliyot shifokori": "fa-user-doctor",
    "Kardiolog": "fa-heart-pulse",
    "Pulmonolog": "fa-lungs",
    "Nevrolog": "fa-brain",
    "Gastroenterolog": "fa-notes-medical",
    "Dermatolog": "fa-hand-dots",
    "Infeksionist": "fa-shield-virus",
}

ADVICE_ICON_MAP = [
    ("darhol", "fa-bolt", "danger"),
    ("tez yordam", "fa-phone-volume", "danger"),
    ("qo'ng'iroq", "fa-phone", "danger"),
    ("suv", "fa-glass-water", "info"),
    ("dam", "fa-bed", "primary"),
    ("kuzat", "fa-eye", "success"),
    ("shifokor", "fa-user-doctor", "warning"),
    ("dori", "fa-pills", "secondary"),
    ("nafas", "fa-lungs", "info"),
    ("isitma", "fa-temperature-high", "warning"),
]


def normalize_risk_level(risk_level):
    normalized = (risk_level or "").strip().lower()
    aliases = {
        "low": "past",
        "medium": "o'rta",
        "high": "yuqori",
        "moderate": "o'rta",
    }
    return aliases.get(normalized, normalized if normalized in RISK_META else "o'rta")


def get_lang(lang_code):
    return lang_code if lang_code in I18N else "uz_latn"


def t(lang_code, key, **kwargs):
    template = I18N[get_lang(lang_code)][key]
    return template.format(**kwargs) if kwargs else template


def get_duration_label(duration_key, lang_code):
    return DURATION_LABELS[get_lang(lang_code)].get(duration_key, duration_key)


def get_gender_label(gender_key, lang_code):
    return GENDER_LABELS[get_lang(lang_code)].get(gender_key, gender_key)


def get_gender_keyboard(lang_code):
    labels = GENDER_LABELS[get_lang(lang_code)]
    return [[labels["male"], labels["female"]]]


def get_duration_keyboard(lang_code):
    labels = DURATION_LABELS[get_lang(lang_code)]
    return [
        [labels["hours"], labels["1-3_days"]],
        [labels["4-7_days"], labels["1-2_weeks"]],
        [labels["2-4_weeks"], labels["more_than_month"]],
    ]


def localize_specialist(specialist, lang_code):
    mapping = SPECIALIST_LABELS.get(specialist)
    if not mapping:
        return specialist
    return mapping.get(get_lang(lang_code), specialist)


def get_risk_label(risk_level, lang_code):
    return RISK_META[risk_level]["label"][get_lang(lang_code)]


def get_risk_summary(risk_level, lang_code):
    return RISK_META[risk_level]["summary"][get_lang(lang_code)]


def sanitize_text(value, max_length):
    cleaned = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", " ", (value or "").strip())
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned[:max_length]


def parse_age_value(raw_age):
    try:
        age = int(str(raw_age).strip())
    except (TypeError, ValueError):
        raise ValueError("Invalid age")
    if age < 1 or age > 120:
        raise ValueError("Age out of range")
    return age


def validate_gender_value(raw_gender):
    normalized = (raw_gender or "").strip().lower()
    if normalized not in {"male", "female"}:
        raise ValueError("Invalid gender")
    return normalized


def validate_duration_value(raw_duration):
    normalized = (raw_duration or "").strip()
    if normalized not in DURATION_LABELS["uz_latn"]:
        raise ValueError("Invalid duration")
    return normalized


def validate_analysis_input(symptoms, age, gender, duration):
    safe_symptoms = sanitize_text(symptoms, app.config["MAX_SYMPTOMS_LENGTH"])
    if len(safe_symptoms) < 3:
        raise ValueError("Symptoms too short")
    return (
        safe_symptoms,
        parse_age_value(age),
        validate_gender_value(gender),
        validate_duration_value(duration),
    )


def check_web_rate_limit():
    client_ip = sanitize_text(request.headers.get("X-Forwarded-For") or request.remote_addr or "unknown", 128)
    now = time.time()
    window = app.config["WEB_RATE_LIMIT_WINDOW_SECONDS"]
    limit = app.config["WEB_RATE_LIMIT_MAX_REQUESTS"]
    with RATE_LIMIT_LOCK:
        timestamps = WEB_RATE_LIMIT_STATE.get(client_ip, [])
        timestamps = [stamp for stamp in timestamps if now - stamp < window]
        if len(timestamps) >= limit:
            return False
        timestamps.append(now)
        WEB_RATE_LIMIT_STATE[client_ip] = timestamps
    return True


def get_request_language():
    lang = request.values.get("lang") or request.args.get("lang") or "uz_latn"
    return get_lang(lang)


def get_language_switch_links():
    current_path = request.path
    return [
        {"code": code, "label": label, "url": f"{current_path}?lang={code}"}
        for code, label in LANGUAGE_LABELS.items()
    ]


def get_web_texts(language):
    language = get_lang(language)
    if language == "ru":
        texts = {
            "brand": "AI Symptom Assistant",
            "home_title": "Главная",
            "app_title": "Анализ симптомов",
            "result_title": "Результаты анализа",
            "history_title": "История анализов",
            "start_check": "Начать проверку",
            "how_it_works": "Как это работает",
            "hero_text": t(language, "bot_description").replace("\n", " "),
            "not_diagnosis": "Это не медицинский диагноз",
            "ai_powered": "С помощью AI",
            "emergency_alerts": "Экстренные предупреждения",
            "quick_check": "Быстрая проверка симптомов",
            "symptoms_label": "Опишите ваши симптомы",
            "symptoms_placeholder": "например, головная боль, температура, слабость, кашель...",
            "symptoms_help": "Постарайтесь быть как можно точнее. Укажите интенсивность, локализацию и другие важные детали.",
            "common_symptoms": "Частые симптомы",
            "chip_hint": "(Нажмите, чтобы добавить)",
            "age": "Возраст",
            "years": "лет",
            "gender": "Пол",
            "duration_question": "Как долго продолжаются симптомы?",
            "choose_duration": "Выберите длительность",
            "analyze_btn": "Анализировать симптомы",
            "loading_btn": "Идёт анализ...",
            "retry_btn": "Попробовать снова",
            "required_alert": "Пожалуйста, заполните все обязательные поля.",
            "timeout_alert": "Ответ занял больше времени, чем ожидалось. Сервер или API могут работать медленно, попробуйте снова.",
            "safety_note_title": "Важное примечание",
            "safety_note_body": "Этот анализ предназначен только для общей информации. Если у вас тяжёлые симптомы или вы беспокоитесь о здоровье, немедленно обратитесь к врачу.",
            "source": "Источник",
            "gemini_source": "Gemini API",
            "fallback_source": "безопасный резервный анализ",
            "entered_data": "Введённые данные",
            "symptoms": "Симптомы",
            "risk_level": t(language, "risk_level"),
            "specialist": t(language, "specialist"),
            "advice": t(language, "advice"),
            "causes": t(language, "causes"),
            "seek_help": t(language, "seek_help"),
            "other_analysis": "Анализировать другие симптомы",
            "back_home": "Вернуться на главную",
            "final_note": "Итоговое примечание",
            "history_empty": "История анализов пока пуста",
        }
        texts["symptom_chips"] = ["головная боль", "температура", "слабость", "боль в груди", "одышка", "тошнота", "головокружение", "кашель", "боль в горле", "боль в животе", "боль в суставах", "сыпь"]
        return texts
    texts = {
        "brand": "AI Symptom Assistant" if language == "en" else "AI Symptom Assistant",
        "home_title": "Home" if language == "en" else "Бош саҳифа" if language == "uz_cyrl" else "Bosh sahifa",
        "app_title": "Symptom Analysis" if language == "en" else "Аломат таҳлили" if language == "uz_cyrl" else "Alomat tahlili",
        "result_title": "Analysis Results" if language == "en" else "Таҳлил натижалари" if language == "uz_cyrl" else "Tahlil natijalari",
        "history_title": "Analysis History" if language == "en" else "Таҳлил тарихи" if language == "uz_cyrl" else "Tahlil tarixi",
        "start_check": "Start Check" if language == "en" else "Текширувни бошлаш" if language == "uz_cyrl" else "Tekshiruvni boshlash",
        "how_it_works": "How it works" if language == "en" else "Қандай ишлайди" if language == "uz_cyrl" else "Qanday ishlaydi",
        "hero_text": t(language, "bot_description").replace("\n", " "),
        "not_diagnosis": "Not a medical diagnosis" if language == "en" else "Тиббий ташхис эмас" if language == "uz_cyrl" else "Tibbiy tashxis emas",
        "ai_powered": "AI-assisted" if language == "en" else "AI ёрдамида" if language == "uz_cyrl" else "AI yordamida",
        "emergency_alerts": "Emergency alerts" if language == "en" else "Фавқулодда огоҳлантиришлар" if language == "uz_cyrl" else "Favqulodda ogohlantirishlar",
        "quick_check": "Quick symptom check" if language == "en" else "Тез аломат текшируви" if language == "uz_cyrl" else "Tez alomat tekshiruvi",
        "symptoms_label": "Describe your symptoms" if language == "en" else "Аломатларингизни тасвирланг" if language == "uz_cyrl" else "Alomatlaringizni tasvirlang",
        "symptoms_placeholder": "e.g. headache, fever, fatigue, cough..." if language == "en" else "масалан, бош оғриғи, иситма, чарчоқ, йўтал..." if language == "uz_cyrl" else "masalan, bosh og'rig'i, isitma, charchoq, yo'tal...",
        "symptoms_help": "Be as specific as possible. Include severity, location, and other relevant details." if language == "en" else "Иложи борича аниқроқ бўлинг. Оғирлик, жойлашув ва бошқа тегишли тафсилотларни қўшинг." if language == "uz_cyrl" else "Iloji boricha aniqroq bo'ling. Og'irlik, joylashuv va boshqa tegishli tafsilotlarni qo'shing.",
        "common_symptoms": "Common symptoms" if language == "en" else "Умумий аломатлар" if language == "uz_cyrl" else "Umumiy alomatlar",
        "chip_hint": "(Click to add)" if language == "en" else "(Қўшиш учун босинг)" if language == "uz_cyrl" else "(Qo'shish uchun bosing)",
        "age": "Age" if language == "en" else "Ёш" if language == "uz_cyrl" else "Yosh",
        "years": "years" if language == "en" else "ёш" if language == "uz_cyrl" else "yosh",
        "gender": "Gender" if language == "en" else "Жинс" if language == "uz_cyrl" else "Jins",
        "duration_question": "How long have the symptoms lasted?" if language == "en" else "Аломатларингиз қанча вақтдан бери давом этмоқда?" if language == "uz_cyrl" else "Alomatlaringiz qancha vaqtdan beri davom etmoqda?",
        "choose_duration": "Choose duration" if language == "en" else "Давомийликни танланг" if language == "uz_cyrl" else "Davomiylikni tanlang",
        "analyze_btn": "Analyze symptoms" if language == "en" else "Аломатларни таҳлил қилиш" if language == "uz_cyrl" else "Alomatlarni tahlil qilish",
        "loading_btn": "Analyzing..." if language == "en" else "Таҳлил қилинмоқда..." if language == "uz_cyrl" else "Tahlil qilinmoqda...",
        "retry_btn": "Try again" if language == "en" else "Қайта уриниб кўриш" if language == "uz_cyrl" else "Qayta urinib ko'rish",
        "required_alert": "Please fill in all required fields." if language == "en" else "Илтимос, барча мажбурий майдонларни тўлдиринг." if language == "uz_cyrl" else "Iltimos, barcha majburiy maydonlarni to'ldiring.",
        "timeout_alert": "The response took longer than expected. The server or API may be slow, please try again." if language == "en" else "Жавоб кутилганидан узоқ давом этди. Сервер ёки API секин ишламоқда, қайта уриниб кўринг." if language == "uz_cyrl" else "Javob kutilganidan uzoq davom etdi. Server yoki API sekin ishlayapti, qayta urinib ko'ring.",
        "safety_note_title": "Safety note" if language == "en" else "Хавфсизлик эслатмаси" if language == "uz_cyrl" else "Xavfsizlik eslatmasi",
        "safety_note_body": "This analysis is for general information only. If you have severe symptoms or are worried about your health, contact a medical professional immediately." if language == "en" else "Бу таҳлил фақат умумий ахборот мақсадларида. Агар сизда оғир аломатлар бўлса ёки соғлиғингиз ҳақида ташвишлансангиз, дарҳол тиббий мутахассис билан боғланинг." if language == "uz_cyrl" else "Bu tahlil faqat umumiy axborot maqsadlarida. Agar sizda og'ir alomatlar bo'lsa yoki sog'lig'ingiz haqida tashvishlansangiz, darhol tibbiy mutaxassis bilan bog'laning.",
        "source": "Source" if language == "en" else "Манба" if language == "uz_cyrl" else "Manba",
        "gemini_source": "Gemini API",
        "fallback_source": "safe fallback analysis" if language == "en" else "хавфсиз fallback таҳлил" if language == "uz_cyrl" else "xavfsiz fallback tahlil",
        "entered_data": "Entered data" if language == "en" else "Сиз киритган маълумотлар" if language == "uz_cyrl" else "Siz kiritgan ma'lumotlar",
        "symptoms": "Symptoms" if language == "en" else "Аломатлар" if language == "uz_cyrl" else "Alomatlar",
        "risk_level": t(language, "risk_level"),
        "specialist": t(language, "specialist"),
        "advice": t(language, "advice"),
        "causes": t(language, "causes"),
        "seek_help": t(language, "seek_help"),
        "other_analysis": "Analyze other symptoms" if language == "en" else "Бошқа аломатларни таҳлил қилиш" if language == "uz_cyrl" else "Boshqa alomatlarni tahlil qilish",
        "back_home": "Back to home" if language == "en" else "Бош саҳифага қайтиш" if language == "uz_cyrl" else "Bosh sahifaga qaytish",
        "final_note": "Final note" if language == "en" else "Якуний эслатма" if language == "uz_cyrl" else "Yakuniy eslatma",
        "history_empty": "No analysis history yet" if language == "en" else "Ҳали таҳлил тарихи йўқ" if language == "uz_cyrl" else "Tahlil tarixi yo'q",
    }
    texts["symptom_chips"] = {
        "uz_latn": ["bosh og'rig'i", "isitma", "charchoq", "ko'krak og'rig'i", "nafas qisilishi", "ko'ngil aynishi", "bosh aylanishi", "yo'tal", "tomoq og'rig'i", "qorin og'rig'i", "bo'g'im og'rig'i", "toshma"],
        "uz_cyrl": ["бош оғриғи", "иситма", "чарчоқ", "кўкрак оғриғи", "нафас қисилиши", "кўнгил айниши", "бош айланиши", "йўтал", "томоқ оғриғи", "қорин оғриғи", "бўғим оғриғи", "тошма"],
        "en": ["headache", "fever", "fatigue", "chest pain", "shortness of breath", "nausea", "dizziness", "cough", "sore throat", "abdominal pain", "joint pain", "rash"],
    }[language]
    return texts


def get_db_connection():
    conn = sqlite3.connect("symptom_checker.db")
    conn.row_factory = sqlite3.Row
    return conn


def save_analysis_record(result):
    conn = get_db_connection()
    conn.execute(
        """INSERT INTO analyses
           (symptoms, age, gender, duration, risk_level, specialist, advice, emergency, date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            result.get("symptoms"),
            result.get("age"),
            result.get("gender"),
            result.get("duration"),
            result.get("risk_level"),
            result.get("specialist"),
            json.dumps(result.get("advice", []), ensure_ascii=False),
            1 if result.get("emergency") else 0,
            datetime.utcnow().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()
    conn.close()


def get_user_language(chat_id):
    conn = get_db_connection()
    row = conn.execute("SELECT language FROM telegram_users WHERE chat_id = ?", (chat_id,)).fetchone()
    conn.close()
    if not row:
        return "uz_latn"
    return get_lang(row["language"])


def save_user_language(chat_id, language):
    conn = get_db_connection()
    conn.execute(
        """INSERT INTO telegram_users (chat_id, language, updated_at)
           VALUES (?, ?, ?)
           ON CONFLICT(chat_id) DO UPDATE SET
             language=excluded.language,
             updated_at=excluded.updated_at""",
        (chat_id, get_lang(language), datetime.utcnow().isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()


def load_telegram_session(chat_id):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT chat_id, step, symptoms, age, gender, updated_at FROM telegram_sessions WHERE chat_id = ?",
        (chat_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None

    try:
        updated_at = datetime.fromisoformat(row["updated_at"])
    except ValueError:
        clear_telegram_session(chat_id)
        return None

    if (datetime.utcnow() - updated_at).total_seconds() > app.config["TELEGRAM_SESSION_TIMEOUT_SECONDS"]:
        clear_telegram_session(chat_id)
        return None

    return dict(row)


def save_telegram_session(chat_id, step, symptoms=None, age=None, gender=None):
    conn = get_db_connection()
    conn.execute(
        """INSERT INTO telegram_sessions (chat_id, step, symptoms, age, gender, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(chat_id) DO UPDATE SET
             step=excluded.step,
             symptoms=excluded.symptoms,
             age=excluded.age,
             gender=excluded.gender,
             updated_at=excluded.updated_at""",
        (chat_id, step, symptoms, age, gender, datetime.utcnow().isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()


def clear_telegram_session(chat_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM telegram_sessions WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()


def detect_emergency(symptoms_text):
    symptoms_lower = (symptoms_text or "").lower()
    emergency_keywords = [
        "ko'krak og'rig'i",
        "кўкрак оғриғи",
        "nafas qisilishi",
        "нафас қисилиши",
        "hushdan ketish",
        "ҳушдан кетиш",
        "qattiq qon ketish",
        "қаттиқ қон кетиш",
        "insult",
        "yurak xuruji",
        "юрак хуружи",
        "chest pain",
        "shortness of breath",
        "unconscious",
    ]
    return any(keyword in symptoms_lower for keyword in emergency_keywords)


def infer_specialist(symptoms_text, emergency=False):
    symptoms_lower = (symptoms_text or "").lower()
    if emergency:
        return "Favqulodda tibbiyot"
    if "ko'krak" in symptoms_lower or "kўkrak" in symptoms_lower or "юрак" in symptoms_lower or "yurak" in symptoms_lower or "chest" in symptoms_lower or "heart" in symptoms_lower:
        return "Kardiolog"
    if "nafas" in symptoms_lower or "yo'tal" in symptoms_lower or "нафас" in symptoms_lower or "йўтал" in symptoms_lower or "cough" in symptoms_lower or "breath" in symptoms_lower:
        return "Pulmonolog"
    if "bosh og'rig" in symptoms_lower or "bosh aylanish" in symptoms_lower or "бош оғри" in symptoms_lower or "бош айлан" in symptoms_lower or "headache" in symptoms_lower or "dizziness" in symptoms_lower:
        return "Nevrolog"
    if "qorin" in symptoms_lower or "ko'ngil ayn" in symptoms_lower or "қорин" in symptoms_lower or "кўнгил айн" in symptoms_lower or "stomach" in symptoms_lower or "nausea" in symptoms_lower:
        return "Gastroenterolog"
    if "toshma" in symptoms_lower or "teri" in symptoms_lower or "тошма" in symptoms_lower or "тери" in symptoms_lower or "rash" in symptoms_lower or "skin" in symptoms_lower:
        return "Dermatolog"
    if "isitma" in symptoms_lower or "иситма" in symptoms_lower or "fever" in symptoms_lower:
        return "Infeksionist"
    return "Umumiy amaliyot shifokori"


def enrich_advice_items(advice_list):
    items = []
    for advice in advice_list:
        icon = "fa-circle-check"
        tone = "success"
        lowered = advice.lower()
        for keyword, mapped_icon, mapped_tone in ADVICE_ICON_MAP:
            if keyword in lowered:
                icon = mapped_icon
                tone = mapped_tone
                break
        items.append({"text": advice, "icon": icon, "tone": tone})
    return items


def fallback_analysis(symptoms, age, gender, duration, language="uz_latn"):
    language = get_lang(language)
    emergency = detect_emergency(symptoms)
    symptoms_lower = (symptoms or "").lower()

    if emergency:
        risk_level = "yuqori"
        advice = {
            "uz_latn": ["Darhol tibbiy yordamga murojaat qiling.", "Agar alomatlar kuchli bo'lsa tez yordamga qo'ng'iroq qiling.", "Yolg'iz qolmang va yaqin insonni xabardor qiling."],
            "uz_cyrl": ["Дарҳол тиббий ёрдамга мурожаат қилинг.", "Агар аломатлар кучли бўлса тез ёрдамга қўнғироқ қилинг.", "Ёлғиз қолманг ва яқин инсонни хабардор қилинг."],
            "en": ["Seek medical help immediately.", "Call emergency services if the symptoms are severe.", "Do not stay alone and alert someone nearby."],
            "ru": ["Немедленно обратитесь за медицинской помощью.", "Если симптомы тяжёлые, вызовите скорую помощь.", "Не оставайтесь одни и сообщите близкому человеку."],
        }[language]
    elif age > 65 or ("isitma" in symptoms_lower and "yo'tal" in symptoms_lower):
        risk_level = "o'rta"
        advice = {
            "uz_latn": ["Bugun yoki ertaga shifokor bilan bog'lanishni rejalashtiring.", "Suyuqlik ichishni oshiring va dam oling.", "Harorat, yo'tal yoki nafasni kuzatib boring."],
            "uz_cyrl": ["Бугун ёки эртага шифокор билан боғланишни режалаштиринг.", "Суюқлик ичишни оширинг ва дам олинг.", "Ҳарорат, йўтал ёки нафасни кузатиб боринг."],
            "en": ["Plan to contact a doctor today or tomorrow.", "Increase fluid intake and get rest.", "Monitor temperature, cough, or breathing changes."],
            "ru": ["Запланируйте связаться с врачом сегодня или завтра.", "Пейте больше жидкости и отдыхайте.", "Следите за температурой, кашлем и дыханием."],
        }[language]
    else:
        risk_level = "past"
        advice = {
            "uz_latn": ["Alomatlarni 24-48 soat davomida kuzating.", "Yetarli suyuqlik iching va dam oling.", "Agar alomatlar kuchaysa shifokorga murojaat qiling."],
            "uz_cyrl": ["Аломатларни 24-48 соат давомида кузатинг.", "Етарли суюқлик ичинг ва дам олинг.", "Агар аломатлар кучайса шифокорга мурожаат қилинг."],
            "en": ["Monitor the symptoms for 24-48 hours.", "Drink enough fluids and get rest.", "Contact a doctor if the symptoms get worse."],
            "ru": ["Наблюдайте за симптомами в течение 24-48 часов.", "Пейте достаточно жидкости и отдыхайте.", "Обратитесь к врачу, если симптомы усилятся."],
        }[language]

    specialist = infer_specialist(symptoms, emergency)
    return {
        "risk_level": risk_level,
        "specialist": specialist,
        "advice": advice,
        "possible_causes": {
            "uz_latn": ["Aniq tashxis qo'yib bo'lmaydi, bu faqat umumiy AI yo'l-yo'riq.", "Virusli yoki yengil yallig'lanish holati ehtimoli bor."],
            "uz_cyrl": ["Аниқ ташхис қўйиб бўлмайди, бу фақат умумий AI йўл-йўриқ.", "Вирусли ёки енгил яллиғланиш ҳолати эҳтимоли бор."],
            "en": ["An exact diagnosis cannot be made; this is only general AI guidance.", "A viral or mild inflammatory condition is possible."],
            "ru": ["Точный диагноз поставить нельзя; это только общая AI-рекомендация.", "Возможна вирусная инфекция или лёгкое воспалительное состояние."],
        }[language],
        "when_to_seek_help": {
            "uz_latn": ["Nafas qisilishi, ko'krak og'rig'i yoki hushdan ketish kuzatilsa darhol yordam oling.", "Alomatlar kuchaysa yoki bir necha kun ichida kamaymasa shifokorga uchrang."],
            "uz_cyrl": ["Нафас қисилиши, кўкрак оғриғи ёки ҳушдан кетиш кузатилса дарҳол ёрдам олинг.", "Аломатлар кучайса ёки бир неча кун ичида камаймаса шифокорга учранг."],
            "en": ["Seek immediate help if there is shortness of breath, chest pain, or fainting.", "See a doctor if symptoms worsen or do not improve within a few days."],
            "ru": ["Немедленно обращайтесь за помощью при одышке, боли в груди или потере сознания.", "Обратитесь к врачу, если симптомы усиливаются или не уменьшаются в течение нескольких дней."],
        }[language],
        "source": "fallback",
        "warning": t(language, "fallback_warning_api", message=t(language, "api_gemini_error")),
    }


def build_prompt(symptoms, age, gender, duration_label, language="uz_latn"):
    language = get_lang(language)
    prompt_language = {
        "uz_latn": "O'zbek (Latin)",
        "uz_cyrl": "Uzbek (Cyrillic)",
        "en": "English",
        "ru": "Russian",
    }[language]
    gender_label = get_gender_label(gender or "male", language) if gender else ("ko'rsatilmagan" if language == "uz_latn" else "кўрсатилмаган" if language == "uz_cyrl" else "not specified" if language == "en" else "не указано")
    return f"""
Siz ehtiyotkor medical triage assistant sifatida ishlaysiz. Tashxis qo'ymang.
Foydalanuvchi ma'lumotlari:
- Alomatlar: {symptoms}
- Yosh: {age}
- Jins: {gender_label}
- Davomiylik: {duration_label}

Faqat quyidagi JSON formatda javob qaytaring:
{{
  "risk_level": "past|o'rta|yuqori",
  "specialist": "qisqa mutaxassis nomi",
  "summary": "1-2 gaplik umumiy tahlil",
  "advice": ["3 ta qisqa tavsiya"],
  "possible_causes": ["2-3 ta ehtimoliy, no-diagnosis izoh"],
  "when_to_seek_help": ["2-3 ta qachon shifokorga murojaat qilish kerak"],
  "emergency": true
}}

Qoida:
- Javob tilini {prompt_language} qiling.
- Juda qisqa va aniq bo'ling.
- Agar ko'krak og'rig'i, nafas qisilishi, hushdan ketish, falaj belgisi bo'lsa emergency=true va risk_level="yuqori".
""".strip()


def extract_api_error(exc, provider, language="uz_latn"):
    language = get_lang(language)
    if isinstance(exc, urllib.error.HTTPError):
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            error = payload.get("error", {})
            message = error.get("message")
            code = error.get("code")
            if code in {"insufficient_quota", "RESOURCE_EXHAUSTED", 429}:
                if provider == "gemini":
                    return t(language, "api_gemini_quota")
                return "OpenAI hisobida quota yetarli emas. Billing yoki limitni tekshiring."
            if message and provider == "gemini":
                return f"{t(language, 'api_gemini_error')} {message}"
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    if provider == "gemini":
        return t(language, "api_gemini_error")
    return "OpenAI API bilan ulanishda xatolik bo'ldi."


def build_user_notice(warning, source, language="uz_latn"):
    if source != "fallback" or not warning:
        return None
    return {
        "title": "Demo rejimda natija chiqarildi" if language == "uz_latn" else "Демо режимида натижа чиқарилди" if language == "uz_cyrl" else "Fallback result shown",
        "title": "Демо-результат показан" if language == "ru" else "Demo rejimda natija chiqarildi" if language == "uz_latn" else "Демо режимида натижа чиқарилди" if language == "uz_cyrl" else "Fallback result shown",
        "message": warning,
        "details": "",
        "icon": "fa-circle-info",
        "tone": "soft-info",
    }


def extract_gemini_text(response_payload):
    candidates = response_payload.get("candidates") or []
    if not candidates:
        return ""

    parts = ((candidates[0].get("content") or {}).get("parts")) or []
    text_chunks = [part.get("text", "") for part in parts if part.get("text")]
    return "".join(text_chunks).strip()


def call_gemini_analysis(symptoms, age, gender, duration, language="uz_latn"):
    language = get_lang(language)
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_api_key_here":
        fallback = fallback_analysis(symptoms, age, gender, duration, language)
        fallback["warning"] = t(language, "fallback_warning_missing_key")
        return fallback

    duration_label = get_duration_label(duration, language)
    schema = {
        "type": "object",
        "properties": {
            "risk_level": {"type": "string"},
            "specialist": {"type": "string"},
            "summary": {"type": "string"},
            "advice": {"type": "array", "items": {"type": "string"}},
            "possible_causes": {"type": "array", "items": {"type": "string"}},
            "when_to_seek_help": {"type": "array", "items": {"type": "string"}},
            "emergency": {"type": "boolean"},
        },
        "required": [
            "risk_level",
            "specialist",
            "summary",
            "advice",
            "possible_causes",
            "when_to_seek_help",
            "emergency",
        ],
    }
    payload = {
        "system_instruction": {
            "parts": [
                {
                    "text": f"You are a careful medical symptom triage assistant. Do not diagnose. Return concise JSON in { {'uz_latn':'Uzbek Latin','uz_cyrl':'Uzbek Cyrillic','en':'English','ru':'Russian'}[language] } only."
                }
            ]
        },
        "contents": [
            {
                "parts": [
                    {
                        "text": build_prompt(symptoms, age, gender, duration_label, language)
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseJsonSchema": schema,
            "temperature": 0.3,
        },
    }

    request_obj = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request_obj, timeout=app.config["AI_TIMEOUT_SECONDS"]) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        fallback = fallback_analysis(symptoms, age, gender, duration, language)
        fallback["warning"] = t(language, "fallback_warning_api", message=extract_api_error(exc, "gemini", language))
        return fallback

    output_text = extract_gemini_text(response_payload)
    if not output_text:
        fallback = fallback_analysis(symptoms, age, gender, duration, language)
        fallback["warning"] = t(language, "fallback_empty")
        return fallback

    cleaned_output = output_text.replace("```json", "").replace("```", "").strip()
    try:
        ai_result = json.loads(cleaned_output)
    except json.JSONDecodeError:
        fallback = fallback_analysis(symptoms, age, gender, duration, language)
        fallback["warning"] = t(language, "fallback_bad_json")
        return fallback

    fallback_base = fallback_analysis(symptoms, age, gender, duration, language)
    return {
        "risk_level": normalize_risk_level(ai_result.get("risk_level")),
        "specialist": ai_result.get("specialist") or infer_specialist(symptoms, detect_emergency(symptoms)),
        "summary": ai_result.get("summary") or get_risk_summary(normalize_risk_level(ai_result.get("risk_level")), language),
        "advice": ai_result.get("advice") or fallback_base["advice"],
        "possible_causes": ai_result.get("possible_causes") or [],
        "when_to_seek_help": ai_result.get("when_to_seek_help") or [],
        "emergency": bool(ai_result.get("emergency", False)) or detect_emergency(symptoms),
        "source": "gemini",
        "warning": None,
    }


def analyze_symptoms(symptoms, age, gender, duration, language="uz_latn"):
    language = get_lang(language)
    analysis = call_gemini_analysis(symptoms, age, gender, duration, language)
    risk_level = normalize_risk_level(analysis.get("risk_level"))
    specialist = analysis.get("specialist") or infer_specialist(symptoms, analysis.get("emergency", False))

    result = {
        "risk_level": risk_level,
        "risk_label": get_risk_label(risk_level, language),
        "risk_class": RISK_META[risk_level]["class_name"],
        "risk_icon": RISK_META[risk_level]["icon"],
        "risk_summary": analysis.get("summary") or get_risk_summary(risk_level, language),
        "specialist": localize_specialist(specialist, language),
        "specialist_icon": SPECIALIST_ICONS.get(specialist, "fa-user-doctor"),
        "advice": analysis.get("advice", []),
        "advice_items": enrich_advice_items(analysis.get("advice", [])),
        "possible_causes": analysis.get("possible_causes", []),
        "when_to_seek_help": analysis.get("when_to_seek_help", []),
        "emergency": bool(analysis.get("emergency", False)),
        "symptoms": symptoms,
        "age": age,
        "gender": get_gender_label(gender, language),
        "duration": get_duration_label(duration, language),
        "language": language,
        "source": analysis.get("source", "fallback"),
        "warning": analysis.get("warning"),
    }
    result["user_notice"] = build_user_notice(result["warning"], result["source"], language)

    return result


def telegram_api_request(method, token, payload=None, timeout=None):
    if not token:
        raise RuntimeError("Telegram bot token topilmadi.")

    url = f"https://api.telegram.org/bot{token}/{method}"
    data = None
    headers = {}

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif "?" in url:
        headers["Content-Type"] = "application/json"

    request_obj = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(request_obj, timeout=timeout or app.config["AI_TIMEOUT_SECONDS"]) as response:
        raw_payload = response.read().decode("utf-8")

    response_payload = json.loads(raw_payload)
    if not response_payload.get("ok"):
        description = response_payload.get("description", "Noma'lum Telegram API xatosi")
        raise RuntimeError(description)
    return response_payload["result"]


def build_reply_keyboard(button_rows, one_time=True):
    return {
        "keyboard": [[{"text": text} for text in row] for row in button_rows],
        "resize_keyboard": True,
        "one_time_keyboard": one_time,
    }


def remove_reply_keyboard():
    return {"remove_keyboard": True}


def build_inline_keyboard(button_rows):
    return {
        "inline_keyboard": [[{"text": text, "callback_data": callback_data} for text, callback_data in row] for row in button_rows]
    }


def send_telegram_message(chat_id, text, token, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": sanitize_text(text, app.config["MAX_TELEGRAM_MESSAGE_LENGTH"]),
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return telegram_api_request("sendMessage", token, payload=payload, timeout=app.config["AI_TIMEOUT_SECONDS"])


def answer_callback_query(callback_query_id, token, text=None):
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    return telegram_api_request("answerCallbackQuery", token, payload=payload, timeout=app.config["AI_TIMEOUT_SECONDS"])


def result_actions_keyboard():
    return result_actions_keyboard_for_language("uz_latn")


def result_actions_keyboard_for_language(language):
    return build_inline_keyboard(
        [
            [(t(language, "new_analysis_btn"), "action_analyze"), (t(language, "help_btn"), "action_help")],
            [(t(language, "home_btn"), "action_start"), (t(language, "language_btn"), "action_language")],
        ]
    )


def language_keyboard():
    return build_inline_keyboard(
        [[(label, f"lang_{code}")] for label, code in LANGUAGE_CHOICES]
    )


def set_telegram_commands(token):
    commands = [
        {"command": "start", "description": "Botni ishga tushirish"},
        {"command": "analyze", "description": "Yangi simptom tahlilini boshlash"},
        {"command": "language", "description": "Tilni o'zgartirish"},
        {"command": "help", "description": "Foydalanish bo'yicha yordam"},
        {"command": "cancel", "description": "Joriy jarayonni bekor qilish"},
    ]
    telegram_api_request("setMyCommands", token, payload={"commands": commands}, timeout=app.config["AI_TIMEOUT_SECONDS"])


def set_telegram_profile(token):
    telegram_api_request(
        "setMyDescription",
        token,
        payload={"description": t("uz_latn", "bot_description")},
        timeout=app.config["AI_TIMEOUT_SECONDS"],
    )
    telegram_api_request(
        "setMyShortDescription",
        token,
        payload={"short_description": t("uz_latn", "bot_short_description")},
        timeout=app.config["AI_TIMEOUT_SECONDS"],
    )


def get_risk_badge(result, language):
    risk_level = normalize_risk_level(result.get("risk_level"))
    return I18N[get_lang(language)]["risk_badges"].get(risk_level, I18N[get_lang(language)]["risk_badges"]["o'rta"])


def format_telegram_list(items, icon, fallback_text):
    safe_items = items or [fallback_text]
    return "\n".join(f"{icon} {html.escape(item)}" for item in safe_items)


def build_welcome_message(language):
    language = get_lang(language)
    return (
        f"{t(language, 'welcome')}\n\n"
        f"{t(language, 'commands_title')}\n"
        "▶️ /start\n"
        "📝 /analyze\n"
        "🌐 /language\n"
        "❓ /help\n"
        "🛑 /cancel"
    )


def format_telegram_result(result, language):
    language = get_lang(language)
    fallback_advice = {
        "uz_latn": "Tavsiya topilmadi.",
        "uz_cyrl": "Тавсия топилмади.",
        "en": "No advice was returned.",
        "ru": "Рекомендации не были получены.",
    }[language]
    fallback_causes = {
        "uz_latn": "AI qo'shimcha ehtimollar bermadi.",
        "uz_cyrl": "AI қўшимча эҳтимоллар бермади.",
        "en": "The AI did not provide additional possibilities.",
        "ru": "AI не дал дополнительных предположений.",
    }[language]
    fallback_help = {
        "uz_latn": "Alomatlar kuchaysa shifokorga murojaat qiling.",
        "uz_cyrl": "Аломатлар кучайса шифокорга мурожаат қилинг.",
        "en": "Contact a doctor if symptoms get worse.",
        "ru": "Обратитесь к врачу, если симптомы усилятся.",
    }[language]
    advice_lines = format_telegram_list(result.get("advice", []), "✅", fallback_advice)
    causes_lines = format_telegram_list(result.get("possible_causes", []), "🧠", fallback_causes)
    help_lines = format_telegram_list(
        result.get("when_to_seek_help", []),
        "🚨",
        fallback_help,
    )
    emergency_line = f"🚨 {t(language, 'yes')}" if result.get("emergency") else f"✅ {t(language, 'no')}"
    risk_label = html.escape(result.get("risk_label", "Noma'lum"))
    specialist = html.escape(result.get("specialist", "Umumiy amaliyot shifokori"))
    summary = html.escape(result.get("risk_summary", "Qisqa xulosa mavjud emas."))
    risk_badge = get_risk_badge(result, language)

    return (
        "<b>━━━━━━━━━━  {result_title}  ━━━━━━━━━━</b>\n\n"
        "<b>{risk_badge}</b>\n"
        "📊 <b>{risk_level_title}:</b> {risk_label}\n"
        "👨‍⚕️ <b>{specialist_title}:</b> {specialist}\n"
        "🚑 <b>{emergency_title}:</b> {emergency_line}\n\n"
        "📝 <b>{summary_title}</b>\n"
        "{summary}\n\n"
        "✅ <b>{advice_title}</b>\n"
        "{advice_lines}\n\n"
        "🧠 <b>{causes_title}</b>\n"
        "{causes_lines}\n\n"
        "🚨 <b>{seek_help_title}</b>\n"
        "{help_lines}\n\n"
        "ℹ️ <i>{medical_disclaimer}</i>"
    ).format(
        result_title=t(language, "result_title"),
        risk_badge=risk_badge,
        risk_level_title=t(language, "risk_level"),
        specialist_title=t(language, "specialist"),
        emergency_title=t(language, "emergency"),
        summary_title=t(language, "summary"),
        advice_title=t(language, "advice"),
        causes_title=t(language, "causes"),
        seek_help_title=t(language, "seek_help"),
        medical_disclaimer=t(language, "medical_disclaimer"),
        risk_label=risk_label,
        specialist=specialist,
        emergency_line=emergency_line,
        summary=summary,
        advice_lines=advice_lines,
        causes_lines=causes_lines,
        help_lines=help_lines,
    )


def normalize_gender_input(text):
    normalized = (text or "").strip().lower()
    for gender_key, aliases in GENDER_INPUT_ALIASES.items():
        if normalized in aliases:
            return gender_key
    return None


def normalize_duration_input(text):
    normalized = (text or "").strip().lower()
    for duration_key, aliases in DURATION_INPUT_ALIASES.items():
        if normalized in aliases:
            return duration_key
    return None


def send_telegram_help(chat_id, token, language=None):
    language = get_lang(language or get_user_language(chat_id))
    send_telegram_message(
        chat_id,
        t(language, "help"),
        token,
        reply_markup=result_actions_keyboard_for_language(language),
    )


def start_telegram_analysis(chat_id, token, language=None):
    language = get_lang(language or get_user_language(chat_id))
    clear_telegram_session(chat_id)
    save_telegram_session(chat_id, "await_symptoms")
    send_telegram_message(
        chat_id,
        t(language, "new_analysis"),
        token,
        reply_markup=remove_reply_keyboard(),
    )


def send_welcome_panel(chat_id, token, language=None):
    language = get_lang(language or get_user_language(chat_id))
    send_telegram_message(
        chat_id,
        build_welcome_message(language),
        token,
        reply_markup=result_actions_keyboard_for_language(language),
    )


def send_language_panel(chat_id, token, language=None):
    language = get_lang(language or get_user_language(chat_id))
    send_telegram_message(chat_id, t(language, "language_title"), token, reply_markup=language_keyboard())


def handle_telegram_callback(callback_query, token):
    callback_id = callback_query.get("id")
    message = callback_query.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    action = callback_query.get("data")
    language = get_user_language(chat_id)

    if not callback_id or not chat_id:
        return

    if action == "action_analyze":
        answer_callback_query(callback_id, token, t(language, "new_analysis_btn"))
        start_telegram_analysis(chat_id, token, language)
        return

    if action == "action_help":
        answer_callback_query(callback_id, token, t(language, "help_btn"))
        send_telegram_help(chat_id, token, language)
        return

    if action == "action_start":
        answer_callback_query(callback_id, token, t(language, "home_btn"))
        send_welcome_panel(chat_id, token, language)
        return

    if action == "action_language":
        answer_callback_query(callback_id, token, t(language, "language_btn"))
        send_language_panel(chat_id, token, language)
        return

    if action and action.startswith("lang_"):
        new_language = action.replace("lang_", "", 1)
        save_user_language(chat_id, new_language)
        answer_callback_query(callback_id, token, t(new_language, "language_changed", language=LANGUAGE_LABELS[new_language]))
        send_welcome_panel(chat_id, token, new_language)
        return

    answer_callback_query(callback_id, token)


def handle_telegram_message(message, token):
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if not chat_id:
        return
    language = get_user_language(chat_id)

    text = sanitize_text(message.get("text") or "", app.config["MAX_SYMPTOMS_LENGTH"])
    if not text:
        send_telegram_message(chat_id, t(language, "text_only"), token)
        return

    lowered = text.lower()
    if lowered == "/cancel":
        clear_telegram_session(chat_id)
        send_telegram_message(chat_id, t(language, "cancelled"), token, reply_markup=remove_reply_keyboard())
        return
    if lowered in {"/start", "/analyze"}:
        if lowered == "/start":
            send_welcome_panel(chat_id, token, language)
            return
        start_telegram_analysis(chat_id, token, language)
        return
    if lowered == "/language":
        send_language_panel(chat_id, token, language)
        return
    if lowered == "/help":
        send_telegram_help(chat_id, token, language)
        return

    session = load_telegram_session(chat_id)
    if not session:
        save_telegram_session(chat_id, "await_age", symptoms=text)
        send_telegram_message(chat_id, t(language, "ask_age"), token)
        return

    step = session["step"]
    if step == "await_symptoms":
        save_telegram_session(chat_id, "await_age", symptoms=text)
        send_telegram_message(chat_id, t(language, "ask_age"), token)
        return

    if step == "await_age":
        try:
            age = int(text)
        except ValueError:
            send_telegram_message(chat_id, t(language, "invalid_age"), token)
            return
        if age < 1 or age > 120:
            send_telegram_message(chat_id, t(language, "age_range"), token)
            return

        save_telegram_session(chat_id, "await_gender", symptoms=session["symptoms"], age=age)
        send_telegram_message(
            chat_id,
            t(language, "ask_gender"),
            token,
            reply_markup=build_reply_keyboard(get_gender_keyboard(language)),
        )
        return

    if step == "await_gender":
        gender = normalize_gender_input(text)
        if gender is None:
            send_telegram_message(
                chat_id,
                t(language, "invalid_gender"),
                token,
                reply_markup=build_reply_keyboard(get_gender_keyboard(language)),
            )
            return

        save_telegram_session(
            chat_id,
            "await_duration",
            symptoms=session["symptoms"],
            age=session["age"],
            gender=gender,
        )
        send_telegram_message(
            chat_id,
            t(language, "ask_duration"),
            token,
            reply_markup=build_reply_keyboard(get_duration_keyboard(language)),
        )
        return

    if step == "await_duration":
        duration = normalize_duration_input(text)
        if duration is None:
            send_telegram_message(
                chat_id,
                t(language, "invalid_duration"),
                token,
                reply_markup=build_reply_keyboard(get_duration_keyboard(language)),
            )
            return

        symptoms = session["symptoms"] or ""
        age = int(session["age"] or 30)
        gender = session["gender"] or ""
        clear_telegram_session(chat_id)
        send_telegram_message(
            chat_id,
            t(language, "processing"),
            token,
            reply_markup=remove_reply_keyboard(),
        )

        try:
            result = analyze_symptoms(symptoms, age, gender, duration, language)
            save_analysis_record(result)
            send_telegram_message(chat_id, format_telegram_result(result, language), token, reply_markup=result_actions_keyboard_for_language(language))
            if result.get("warning"):
                send_telegram_message(chat_id, f"{t(language, 'warning_prefix')}{html.escape(result['warning'])}", token)
        except Exception:
            fallback_base = fallback_analysis(symptoms, age, gender, duration, language)
            risk_level = normalize_risk_level(fallback_base.get("risk_level"))
            fallback = {
                "risk_level": risk_level,
                "risk_label": get_risk_label(risk_level, language),
                "specialist": localize_specialist(fallback_base.get("specialist") or infer_specialist(symptoms, detect_emergency(symptoms)), language),
                "risk_summary": t(language, "fallback_summary"),
                "advice": fallback_base.get("advice", []),
                "possible_causes": fallback_base.get("possible_causes", []),
                "when_to_seek_help": fallback_base.get("when_to_seek_help", []),
                "emergency": bool(fallback_base.get("emergency", False)) or detect_emergency(symptoms),
            }
            send_telegram_message(chat_id, format_telegram_result(fallback, language), token, reply_markup=result_actions_keyboard_for_language(language))
            send_telegram_message(
                chat_id,
                t(language, "server_error_safe"),
                token,
            )
        return

    clear_telegram_session(chat_id)
    start_telegram_analysis(chat_id, token, language)


def poll_telegram_updates(token):
    offset = None
    while True:
        try:
            query = {
                "timeout": app.config["TELEGRAM_POLL_TIMEOUT_SECONDS"],
                "allowed_updates": json.dumps(["message", "callback_query"]),
            }
            if offset is not None:
                query["offset"] = offset

            url = f"https://api.telegram.org/bot{token}/getUpdates?{urlencode(query)}"
            updates = telegram_api_request(
                url.replace(f"https://api.telegram.org/bot{token}/", ""),
                token,
                timeout=app.config["TELEGRAM_POLL_TIMEOUT_SECONDS"] + 5,
            )
            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message")
                if message:
                    handle_telegram_message(message, token)
                callback_query = update.get("callback_query")
                if callback_query:
                    handle_telegram_callback(callback_query, token)
        except Exception:
            time.sleep(app.config["TELEGRAM_RETRY_DELAY_SECONDS"])


def start_telegram_bot():
    global TELEGRAM_POLL_THREAD, TELEGRAM_POLL_STARTED

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return False

    with TELEGRAM_POLL_LOCK:
        if TELEGRAM_POLL_STARTED:
            return True
        set_telegram_profile(token)
        set_telegram_commands(token)
        TELEGRAM_POLL_THREAD = threading.Thread(
            target=poll_telegram_updates,
            args=(token,),
            name="telegram-polling",
            daemon=True,
        )
        TELEGRAM_POLL_THREAD.start()
        TELEGRAM_POLL_STARTED = True
    return True


init_db()


@app.route("/")
def index():
    language = get_request_language()
    return render_template("index.html", lang=language, ui=get_web_texts(language), language_links=get_language_switch_links())


@app.route("/app")
def app_page():
    language = get_request_language()
    return render_template("app.html", lang=language, ui=get_web_texts(language), language_links=get_language_switch_links(), duration_labels=DURATION_LABELS[language], gender_labels=GENDER_LABELS[language])


@app.route("/analyze", methods=["POST"])
def analyze():
    if not check_web_rate_limit():
        abort(429)

    language = get_request_language()
    try:
        symptoms, age, gender, duration = validate_analysis_input(
            request.form.get("symptoms"),
            request.form.get("age"),
            request.form.get("gender"),
            request.form.get("duration"),
        )
    except ValueError:
        abort(400)

    try:
        result = analyze_symptoms(symptoms, age, gender, duration, language)
        save_analysis_record(result)
    except Exception:
        result = fallback_analysis(symptoms, age, gender, duration, language)
        risk_level = normalize_risk_level(result.get("risk_level"))
        specialist = result.get("specialist") or infer_specialist(symptoms, result.get("emergency", False))
        result = {
            "risk_level": risk_level,
            "risk_label": get_risk_label(risk_level, language),
            "risk_class": RISK_META[risk_level]["class_name"],
            "risk_icon": RISK_META[risk_level]["icon"],
            "risk_summary": get_risk_summary(risk_level, language),
            "specialist": localize_specialist(specialist, language),
            "specialist_icon": SPECIALIST_ICONS.get(specialist, "fa-user-doctor"),
            "advice": result.get("advice", []),
            "advice_items": enrich_advice_items(result.get("advice", [])),
            "possible_causes": result.get("possible_causes", []),
            "when_to_seek_help": result.get("when_to_seek_help", []),
            "emergency": bool(result.get("emergency", False)),
            "symptoms": symptoms,
            "age": age,
            "gender": get_gender_label(gender, language) if gender in {"male", "female"} else gender,
            "duration": get_duration_label(duration, language),
            "language": language,
            "source": "fallback",
            "warning": "Server ichida xatolik bo'ldi. Xavfsiz fallback tahlil ko'rsatildi.",
        }
        result["user_notice"] = build_user_notice(result["warning"], result["source"], language)
        save_analysis_record(result)

    return render_template("result.html", result=result, lang=language, ui=get_web_texts(language), language_links=get_language_switch_links())


@app.route("/history")
def history():
    language = get_request_language()
    conn = get_db_connection()
    rows = conn.execute(
        """SELECT date, symptoms, risk_level, specialist, duration
           FROM analyses
           ORDER BY id DESC
           LIMIT 20"""
    ).fetchall()
    conn.close()
    history_items = [
        {
            "date": row["date"],
            "symptoms": row["symptoms"],
            "risk_level": row["risk_level"],
            "risk_label": get_risk_label(normalize_risk_level(row["risk_level"]), language),
            "specialist": row["specialist"],
            "duration": row["duration"],
        }
        for row in rows
    ]
    return render_template("history.html", history=history_items, lang=language, ui=get_web_texts(language), language_links=get_language_switch_links())


@app.errorhandler(400)
def handle_bad_request(_error):
    return "Bad request", 400


@app.errorhandler(413)
def handle_payload_too_large(_error):
    return "Payload too large", 413


@app.errorhandler(429)
def handle_rate_limited(_error):
    return "Too many requests", 429


if __name__ == "__main__":
    start_telegram_bot()
    app.run(
        debug=os.environ.get("FLASK_DEBUG", "").strip().lower() == "true",
        use_reloader=False,
        host=os.environ.get("FLASK_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLASK_PORT", "5000")),
    )
