"""Every patient-facing sentence, in Arabic and English, in one place so the clinic can review the wording."""

MESSAGES = {
    "menu": {
        "ar": "مرحباً بك في عيادات أبها الطبية 👋\nأرسل رقم الخدمة:\n1️⃣ حجز موعد\n2️⃣ مواعيدي\n3️⃣ إلغاء موعد\n"
              "(Send EN for English)",
        "en": "Welcome to Abha Medical Clinics 👋\nReply with a number:\n1️⃣ Book an appointment\n"
              "2️⃣ My appointments\n3️⃣ Cancel an appointment\n(أرسل ع للعربية)",
    },
    "ask_symptoms": {
        "ar": "صف لنا باختصار سبب الزيارة (مثال: ألم في الركبة، طفح جلدي، فحص حمل).",
        "en": "Briefly describe the reason for your visit (e.g. knee pain, skin rash, pregnancy check).",
    },
    "emergency": {
        "ar": "⚠️ ما وصفته قد يكون حالة طارئة. اتصل بالإسعاف على 997 فوراً أو توجّه لأقرب طوارئ. "
              "لا تنتظر موعد العيادة.",
        "en": "⚠️ What you describe may be an emergency. Call 997 now or go to the nearest emergency "
              "department. Do not wait for a clinic appointment.",
    },
    "slots": {
        "ar": "الأقرب في {specialty}:\n{options}\n\nأرسل رقم الموعد، أو 0 لاختيار تخصص آخر.",
        "en": "Next available in {specialty}:\n{options}\n\nReply with a number, or 0 to choose another specialty.",
    },
    "no_slots": {
        "ar": "لا توجد مواعيد متاحة في {specialty} خلال الأيام القادمة. أرسل 0 لاختيار تخصص آخر.",
        "en": "No free slots in {specialty} in the coming days. Reply 0 to choose another specialty.",
    },
    "choose_specialty": {
        "ar": "اختر التخصص:\n{options}",
        "en": "Choose a specialty:\n{options}",
    },
    "ask_name": {"ar": "ما اسم المريض الكامل؟", "en": "What is the patient's full name?"},
    "ask_id": {
        "ar": "أرسل رقم الهوية الوطنية أو الإقامة للمريض (10 أرقام).",
        "en": "Send the patient's National ID or Iqama number (10 digits).",
    },
    "bad_id": {
        "ar": "رقم الهوية غير صحيح، تأكد منه وأعد إرساله.",
        "en": "That ID number isn't valid. Please check it and send it again.",
    },
    "confirm": {
        "ar": "تأكيد الحجز:\n👤 {name}\n🩺 {specialty} - {doctor}\n📍 {branch}\n🗓 {when}\n\nأرسل نعم للتأكيد أو لا للإلغاء.",
        "en": "Please confirm:\n👤 {name}\n🩺 {specialty} - {doctor}\n📍 {branch}\n🗓 {when}\n\nReply YES to confirm or NO to cancel.",
    },
    "booked": {
        "ar": "✅ تم الحجز. رقم الموعد {reference}.\nفضلاً احضر قبل الموعد بـ 15 دقيقة مع الهوية. سنذكّرك قبل يوم.",
        "en": "✅ Booked. Your reference is {reference}.\nPlease arrive 15 minutes early with your ID. "
              "We'll remind you the day before.",
    },
    "slot_taken": {
        "ar": "عذراً، تم حجز هذا الموعد للتو. هذه مواعيد أخرى:",
        "en": "Sorry, someone just took that slot. Here are other times:",
    },
    "aborted": {"ar": "تم إلغاء العملية.", "en": "Cancelled. Nothing was booked."},
    "none_upcoming": {"ar": "ليس لديك مواعيد قادمة.", "en": "You have no upcoming appointments."},
    "upcoming": {"ar": "مواعيدك القادمة:\n{options}", "en": "Your upcoming appointments:\n{options}"},
    "choose_cancel": {
        "ar": "أي موعد تريد إلغاءه؟\n{options}",
        "en": "Which appointment do you want to cancel?\n{options}",
    },
    "cancelled": {"ar": "تم إلغاء الموعد {reference}.", "en": "Appointment {reference} is cancelled."},
    "invalid_choice": {"ar": "لم أفهم اختيارك، أرسل رقماً من القائمة.", "en": "Please reply with a number from the list."},
    "text_only": {
        "ar": "حالياً نستقبل الرسائل النصية فقط.",
        "en": "For now I can only read text messages.",
    },
    "reminder": {
        "ar": "تذكير: موعدك غداً {when} في {branch} ({specialty}). رقم الموعد {reference}. للإلغاء أرسل 3.",
        "en": "Reminder: your appointment is tomorrow {when} at {branch} ({specialty}). "
              "Reference {reference}. To cancel, reply 3.",
    },
}


def t(key: str, lang: str, **values: str) -> str:
    return MESSAGES[key][lang].format(**values)
