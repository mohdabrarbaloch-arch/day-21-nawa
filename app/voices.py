"""The voice catalog.

Microsoft's neural voices are the engine. This module curates a subset that is
genuinely useful — the full list is over 300 entries and most are redundant —
and groups them by the language a person is actually working in, with Urdu
called out because it is the reason this project exists.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Voice:
    id: str
    label: str
    gender: str
    locale: str
    language: str
    accent: str
    sample_text: str

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "label": self.label,
            "gender": self.gender,
            "locale": self.locale,
            "language": self.language,
            "accent": self.accent,
            "sample_text": self.sample_text,
        }


_EN_SAMPLE = (
    "Numbers are the hard part. Rs 1,50,000 read aloud should sound like money, not like a barcode."
)
_UR_SAMPLE = "یہ آواز کا ایک نمونہ ہے۔ اعداد و شمار کو وہی کہا جاتا ہے جو بولنے میں آتا ہے۔"

VOICES: tuple[Voice, ...] = (
    # English — South Asia first, because that is where this gets used.
    Voice("en-PK-UzmaNeural", "Uzma", "Female", "en-PK", "English", "Pakistani", _EN_SAMPLE),
    Voice("en-PK-AsadNeural", "Asad", "Male", "en-PK", "English", "Pakistani", _EN_SAMPLE),
    Voice("en-IN-NeerjaNeural", "Neerja", "Female", "en-IN", "English", "Indian", _EN_SAMPLE),
    Voice("en-IN-PrabhatNeural", "Prabhat", "Male", "en-IN", "English", "Indian", _EN_SAMPLE),
    # English — US / UK / AU
    Voice("en-US-AriaNeural", "Aria", "Female", "en-US", "English", "American", _EN_SAMPLE),
    Voice("en-US-GuyNeural", "Guy", "Male", "en-US", "English", "American", _EN_SAMPLE),
    Voice("en-US-JennyNeural", "Jenny", "Female", "en-US", "English", "American", _EN_SAMPLE),
    Voice(
        "en-US-EmmaMultilingualNeural",
        "Emma",
        "Female",
        "en-US",
        "English",
        "Multilingual",
        _EN_SAMPLE,
    ),
    Voice("en-GB-SoniaNeural", "Sonia", "Female", "en-GB", "English", "British", _EN_SAMPLE),
    Voice("en-GB-RyanNeural", "Ryan", "Male", "en-GB", "English", "British", _EN_SAMPLE),
    Voice("en-AU-NatashaNeural", "Natasha", "Female", "en-AU", "English", "Australian", _EN_SAMPLE),
    # Urdu
    Voice("ur-PK-UzmaNeural", "Uzma (Urdu)", "Female", "ur-PK", "Urdu", "Pakistani", _UR_SAMPLE),
    Voice("ur-PK-AsadNeural", "Asad (Urdu)", "Male", "ur-PK", "Urdu", "Pakistani", _UR_SAMPLE),
    Voice("ur-IN-GulNeural", "Gul", "Female", "ur-IN", "Urdu", "Indian", _UR_SAMPLE),
    Voice("ur-IN-SalmanNeural", "Salman", "Male", "ur-IN", "Urdu", "Indian", _UR_SAMPLE),
    # Other languages people commonly need
    Voice(
        "ar-SA-ZariyahNeural",
        "Zariyah",
        "Female",
        "ar-SA",
        "Arabic",
        "Saudi",
        "هذا نموذج من الصوت. الأرقام تُقرأ كما تُلفظ، لا كما تُكتب.",
    ),
    Voice(
        "hi-IN-SwaraNeural",
        "Swara",
        "Female",
        "hi-IN",
        "Hindi",
        "Indian",
        "यह आवाज़ का एक नमूना है। संख्याएँ वैसे पढ़ी जाती हैं जैसे बोली जाती हैं।",
    ),
    Voice(
        "tr-TR-EmelNeural",
        "Emel",
        "Female",
        "tr-TR",
        "Turkish",
        "Turkish",
        "Bu bir ses örneğidir. Sayılar yazıldığı gibi değil, söylendiği gibi okunur.",
    ),
    Voice(
        "es-ES-ElviraNeural",
        "Elvira",
        "Female",
        "es-ES",
        "Spanish",
        "Spanish",
        "Esta es una muestra de voz. Los números se leen como se dicen, no como se escriben.",
    ),
    Voice(
        "fr-FR-DeniseNeural",
        "Denise",
        "Female",
        "fr-FR",
        "French",
        "French",
        "Ceci est un exemple de voix. Les nombres se lisent comme on les prononce.",
    ),
    Voice(
        "de-DE-KatjaNeural",
        "Katja",
        "Female",
        "de-DE",
        "German",
        "German",
        "Dies ist eine Stimmprobe. Zahlen werden so gelesen, wie man sie ausspricht.",
    ),
    Voice(
        "zh-CN-XiaoxiaoNeural",
        "Xiaoxiao",
        "Female",
        "zh-CN",
        "Chinese",
        "Mandarin",
        "这是一个语音示例。数字要按口语读法朗读，而不是按书写形式。",
    ),
)

VOICE_IDS = frozenset(v.id for v in VOICES)
DEFAULT_VOICE = "en-US-AriaNeural"


def get_voice(voice_id: str) -> Voice | None:
    return next((v for v in VOICES if v.id == voice_id), None)


def is_supported(voice_id: str) -> bool:
    return voice_id in VOICE_IDS


def languages() -> list[dict[str, str | int]]:
    """Group the catalog by language for the picker."""
    grouped: dict[str, list[dict[str, str]]] = {}
    for voice in VOICES:
        grouped.setdefault(voice.language, []).append(voice.as_dict())
    return [
        {"language": language, "count": len(items), "voices": items}
        for language, items in grouped.items()
    ]
