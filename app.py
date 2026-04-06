from flask import Flask, render_template, request
import json
import os
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime

app = Flask(__name__)
app.config["AI_TIMEOUT_SECONDS"] = 12


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
    conn.commit()
    conn.close()


DURATION_LABELS = {
    "hours": "24 soatdan kam",
    "1-3_days": "1-3 kun",
    "4-7_days": "4-7 kun",
    "1-2_weeks": "1-2 hafta",
    "2-4_weeks": "2-4 hafta",
    "more_than_month": "Bir oydan ko'proq",
}

RISK_META = {
    "past": {
        "label": "Past",
        "class_name": "past",
        "icon": "fa-shield-heart",
        "summary": "Hozircha xavf nisbatan past ko'rinadi, lekin alomatlarni kuzatishda davom eting.",
    },
    "o'rta": {
        "label": "O'rta",
        "class_name": "orta",
        "icon": "fa-stethoscope",
        "summary": "Alomatlar shifokor bilan rejalashtirilgan maslahatni talab qilishi mumkin.",
    },
    "yuqori": {
        "label": "Yuqori",
        "class_name": "yuqori",
        "icon": "fa-triangle-exclamation",
        "summary": "Alomatlar jiddiy holatga mos kelishi mumkin. Tezroq tibbiy yordam oling.",
    },
}

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


def detect_emergency(symptoms_text):
    symptoms_lower = (symptoms_text or "").lower()
    emergency_keywords = [
        "ko'krak og'rig'i",
        "nafas qisilishi",
        "hushdan ketish",
        "qattiq qon ketish",
        "insult",
        "yurak xuruji",
        "chest pain",
        "shortness of breath",
        "unconscious",
    ]
    return any(keyword in symptoms_lower for keyword in emergency_keywords)


def infer_specialist(symptoms_text, emergency=False):
    symptoms_lower = (symptoms_text or "").lower()
    if emergency:
        return "Favqulodda tibbiyot"
    if "ko'krak" in symptoms_lower or "yurak" in symptoms_lower:
        return "Kardiolog"
    if "nafas" in symptoms_lower or "yo'tal" in symptoms_lower:
        return "Pulmonolog"
    if "bosh og'rig" in symptoms_lower or "bosh aylanish" in symptoms_lower:
        return "Nevrolog"
    if "qorin" in symptoms_lower or "ko'ngil ayn" in symptoms_lower:
        return "Gastroenterolog"
    if "toshma" in symptoms_lower or "teri" in symptoms_lower:
        return "Dermatolog"
    if "isitma" in symptoms_lower:
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


def fallback_analysis(symptoms, age, gender, duration):
    emergency = detect_emergency(symptoms)
    symptoms_lower = (symptoms or "").lower()

    if emergency:
        risk_level = "yuqori"
        advice = [
            "Darhol tibbiy yordamga murojaat qiling.",
            "Agar alomatlar kuchli bo'lsa tez yordamga qo'ng'iroq qiling.",
            "Yolg'iz qolmang va yaqin insonni xabardor qiling.",
        ]
    elif age > 65 or ("isitma" in symptoms_lower and "yo'tal" in symptoms_lower):
        risk_level = "o'rta"
        advice = [
            "Bugun yoki ertaga shifokor bilan bog'lanishni rejalashtiring.",
            "Suyuqlik ichishni oshiring va dam oling.",
            "Harorat, yo'tal yoki nafasni kuzatib boring.",
        ]
    else:
        risk_level = "past"
        advice = [
            "Alomatlarni 24-48 soat davomida kuzating.",
            "Yetarli suyuqlik iching va dam oling.",
            "Agar alomatlar kuchaysa shifokorga murojaat qiling.",
        ]

    specialist = infer_specialist(symptoms, emergency)
    return {
        "risk_level": risk_level,
        "specialist": specialist,
        "advice": advice,
        "possible_causes": [
            "Aniq tashxis qo'yib bo'lmaydi, bu faqat umumiy AI yo'l-yo'riq.",
            "Virusli yoki yengil yallig'lanish holati ehtimoli bor.",
        ],
        "when_to_seek_help": [
            "Nafas qisilishi, ko'krak og'rig'i yoki hushdan ketish kuzatilsa darhol yordam oling.",
            "Alomatlar kuchaysa yoki bir necha kun ichida kamaymasa shifokorga uchrang.",
        ],
        "source": "fallback",
        "warning": "API javobi olinmadi, shuning uchun xavfsiz fallback tahlil ishlatildi.",
    }


def build_prompt(symptoms, age, gender, duration_label):
    return f"""
Siz ehtiyotkor medical triage assistant sifatida ishlaysiz. Tashxis qo'ymang.
Foydalanuvchi ma'lumotlari:
- Alomatlar: {symptoms}
- Yosh: {age}
- Jins: {gender or "ko'rsatilmagan"}
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
- O'zbek tilida yozing.
- Juda qisqa va aniq bo'ling.
- Agar ko'krak og'rig'i, nafas qisilishi, hushdan ketish, falaj belgisi bo'lsa emergency=true va risk_level="yuqori".
""".strip()


def extract_api_error(exc, provider):
    if isinstance(exc, urllib.error.HTTPError):
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            error = payload.get("error", {})
            message = error.get("message")
            code = error.get("code")
            if code in {"insufficient_quota", "RESOURCE_EXHAUSTED", 429}:
                if provider == "gemini":
                    return "Gemini hisobida limit yoki billing muammosi bor."
                return "OpenAI hisobida quota yetarli emas. Billing yoki limitni tekshiring."
            if message:
                if provider == "gemini":
                    return f"Gemini API xatosi: {message}"
                return f"OpenAI API xatosi: {message}"
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    if provider == "gemini":
        return "Gemini API bilan ulanishda xatolik bo'ldi."
    return "OpenAI API bilan ulanishda xatolik bo'ldi."


def build_user_notice(warning, source):
    if source != "fallback" or not warning:
        return None

    lowered = warning.lower()
    if "quota" in lowered or "billing" in lowered or "limit" in lowered:
        return {
            "title": "Hozircha demo tahlil ko'rsatildi",
            "message": "AI xizmatiga ulanish vaqtincha cheklanganligi sababli sizga xavfsiz demo natija chiqarildi.",
            "details": "Hisob limiti yoki billing tiklangach real AI tahlili avtomatik ishlaydi.",
            "icon": "fa-wallet",
            "tone": "soft-warning",
        }
    if "api_key" in lowered:
        return {
            "title": "AI xizmat sozlamasi topilmadi",
            "message": "Tizim hozir real AI xizmatiga ulanmagan, shuning uchun demo tahlil ko'rsatildi.",
            "details": "Sozlama to'g'rilangach natijalar real AI orqali shakllanadi.",
            "icon": "fa-key",
            "tone": "soft-warning",
        }
    return {
        "title": "Demo rejimda natija chiqarildi",
        "message": "AI xizmatida vaqtinchalik uzilish bo'lgani uchun sizga xavfsiz zaxira tahlil ko'rsatildi.",
        "details": "Bir ozdan keyin qayta urinib ko'rsangiz, real AI javobi chiqishi mumkin.",
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


def call_gemini_analysis(symptoms, age, gender, duration):
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_api_key_here":
        fallback = fallback_analysis(symptoms, age, gender, duration)
        fallback["warning"] = "`.env` ichida haqiqiy GEMINI_API_KEY topilmadi."
        return fallback

    duration_label = DURATION_LABELS.get(duration, duration)
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
                    "text": "You are a careful medical symptom triage assistant. Do not diagnose. Return concise Uzbek JSON only."
                }
            ]
        },
        "contents": [
            {
                "parts": [
                    {
                        "text": build_prompt(symptoms, age, gender, duration_label)
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
        fallback = fallback_analysis(symptoms, age, gender, duration)
        fallback["warning"] = f"{extract_api_error(exc, 'gemini')} Fallback tahlil ishlatildi."
        return fallback

    output_text = extract_gemini_text(response_payload)
    if not output_text:
        fallback = fallback_analysis(symptoms, age, gender, duration)
        fallback["warning"] = "Gemini bo'sh javob qaytardi, fallback tahlil ishlatildi."
        return fallback

    cleaned_output = output_text.replace("```json", "").replace("```", "").strip()
    try:
        ai_result = json.loads(cleaned_output)
    except json.JSONDecodeError:
        fallback = fallback_analysis(symptoms, age, gender, duration)
        fallback["warning"] = "Gemini JSON formatda javob bermadi, fallback tahlil ishlatildi."
        return fallback

    return {
        "risk_level": normalize_risk_level(ai_result.get("risk_level")),
        "specialist": ai_result.get("specialist") or infer_specialist(symptoms, detect_emergency(symptoms)),
        "summary": ai_result.get("summary") or "AI alomatlaringiz bo'yicha umumiy yo'l-yo'riq tuzdi.",
        "advice": ai_result.get("advice") or fallback_analysis(symptoms, age, gender, duration)["advice"],
        "possible_causes": ai_result.get("possible_causes") or [],
        "when_to_seek_help": ai_result.get("when_to_seek_help") or [],
        "emergency": bool(ai_result.get("emergency", False)) or detect_emergency(symptoms),
        "source": "gemini",
        "warning": None,
    }


def analyze_symptoms(symptoms, age, gender, duration):
    analysis = call_gemini_analysis(symptoms, age, gender, duration)
    risk_level = normalize_risk_level(analysis.get("risk_level"))
    specialist = analysis.get("specialist") or infer_specialist(symptoms, analysis.get("emergency", False))

    result = {
        "risk_level": risk_level,
        "risk_label": RISK_META[risk_level]["label"],
        "risk_class": RISK_META[risk_level]["class_name"],
        "risk_icon": RISK_META[risk_level]["icon"],
        "risk_summary": analysis.get("summary") or RISK_META[risk_level]["summary"],
        "specialist": specialist,
        "specialist_icon": SPECIALIST_ICONS.get(specialist, "fa-user-doctor"),
        "advice": analysis.get("advice", []),
        "advice_items": enrich_advice_items(analysis.get("advice", [])),
        "possible_causes": analysis.get("possible_causes", []),
        "when_to_seek_help": analysis.get("when_to_seek_help", []),
        "emergency": bool(analysis.get("emergency", False)),
        "symptoms": symptoms,
        "age": age,
        "gender": gender,
        "duration": DURATION_LABELS.get(duration, duration),
        "source": analysis.get("source", "fallback"),
        "warning": analysis.get("warning"),
    }
    result["user_notice"] = build_user_notice(result["warning"], result["source"])

    return result


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/app")
def app_page():
    return render_template("app.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    symptoms = (request.form.get("symptoms") or "").strip()
    age = int(request.form.get("age") or 30)
    gender = request.form.get("gender") or ""
    duration = request.form.get("duration") or ""

    try:
        result = analyze_symptoms(symptoms, age, gender, duration)
    except Exception:
        result = fallback_analysis(symptoms, age, gender, duration)
        risk_level = normalize_risk_level(result.get("risk_level"))
        specialist = result.get("specialist") or infer_specialist(symptoms, result.get("emergency", False))
        result = {
            "risk_level": risk_level,
            "risk_label": RISK_META[risk_level]["label"],
            "risk_class": RISK_META[risk_level]["class_name"],
            "risk_icon": RISK_META[risk_level]["icon"],
            "risk_summary": RISK_META[risk_level]["summary"],
            "specialist": specialist,
            "specialist_icon": SPECIALIST_ICONS.get(specialist, "fa-user-doctor"),
            "advice": result.get("advice", []),
            "advice_items": enrich_advice_items(result.get("advice", [])),
            "possible_causes": result.get("possible_causes", []),
            "when_to_seek_help": result.get("when_to_seek_help", []),
            "emergency": bool(result.get("emergency", False)),
            "symptoms": symptoms,
            "age": age,
            "gender": gender,
            "duration": DURATION_LABELS.get(duration, duration),
            "source": "fallback",
            "warning": "Server ichida xatolik bo'ldi. Xavfsiz fallback tahlil ko'rsatildi.",
        }
        result["user_notice"] = build_user_notice(result["warning"], result["source"])

    return render_template("result.html", result=result)


@app.route("/history")
def history():
    mock_history = [
        {
            "date": "2026-04-06 10:30:00",
            "symptoms": "Bosh og'rig'i, charchoq",
            "risk_level": "past",
            "specialist": "Umumiy amaliyot shifokori",
            "duration": "1-3 kun",
        }
    ]
    return render_template("history.html", history=mock_history)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
