"""Qoida-asosidagi savol generatori (sun'iy intellektsiz, bepul).

Bu modul OpenAI/Anthropic kabi tashqi API larsiz, sof lokal algoritmlar
yordamida matndan test savollari yaratadi.

Strategiyalar:
1. Bo'sh joy (cloze) savollari — gap ichidagi muhim so'z yashiriladi.
2. "Qaysi bir to'g'ri" savollari — asl jumladan haqiqat va aldash quriladi.
3. Birinchi so'z savoli — jumlaning boshlanishi berilib, tugashi so'raladi.
4. Kalit so'z savoli — matndan muhim atama olinib, ta'rifi bilan bog'lanadi.
5. Raqam/fakt savoli — matndagi sonlar, sanalar, nomlar asosida.

Hech qanday internetga ulanmaydi, modellarni yuklamaydi, bepul ishlaydi.
"""
from __future__ import annotations

import re
import random
import hashlib
from collections import Counter
from typing import List, Dict, Any, Optional, Tuple

from bot.config import settings

try:
    import redis.asyncio as aioredis
    _REDIS_AVAILABLE = True
except Exception:  # pragma: no cover
    _REDIS_AVAILABLE = False


# ============== Yordamchi funksiyalar ==============

# Stop-so'zlar: matndan chiqarib tashlanadigan juda keng tarqalgan so'zlar
# (3 tilda — o'zbek, rus, ingliz). Bu savol sifatini oshiradi.
STOPWORDS = {
    # O'zbek
    "va", "yoki", "uchun", "bilan", "bu", "shu", "u", "men", "sen", "biz",
    "siz", "ular", "boshqa", "ham", "hamda", "lekin", "ammo", "chunki",
    "agar", "demak", "shuning", "uchun", "deb", "bilan", "qarab", "to'g'ri",
    "esa", "esa-da", "bo'lib", "bo'lsa", "kerak", "mumkin", "emas", "bor",
    "yo'q", "ha", "yoq", "edi", "ekan", "bo'lgan", "qiladi", "qildi",
    "qilish", "qilishga", "edi", "ekanligi", "kabi", "singari", "ya'ni",
    "ya'ni", "shu", "ana", "ana shu", "o'sha", "mana", "mana bu",
    # Rus
    "и", "или", "для", "с", "в", "на", "по", "из", "это", "эта", "этот",
    "что", "который", "как", "так", "но", "же", "бы", "ли", "ни", "не",
    "да", "нет", "он", "она", "оно", "они", "мы", "вы", "я", "ты",
    "когда", "где", "зачем", "почему", "потому", "чтобы", "если", "хотя",
    "очень", "более", "менее", "уже", "ещё", "даже", "только", "лишь",
    # Ingliz
    "the", "a", "an", "and", "or", "for", "with", "of", "in", "on", "at",
    "to", "is", "are", "was", "were", "be", "been", "being", "this", "that",
    "these", "those", "it", "its", "they", "them", "we", "us", "you", "he",
    "she", "i", "me", "my", "your", "his", "her", "as", "by", "but", "if",
    "so", "not", "no", "yes", "very", "more", "less", "already", "even",
    "only", "just", "than", "then", "also", "such",
}

# Punctuation belgilari
_PUNCT = re.compile(r"[‘’“”`\"'(){}\[\]<>|/\\!?.,;:\-_=+*&^%$#@~]")
_NUMERIC = re.compile(r"^-?\d+(?:[.,]\d+)?$")


def _normalize_word(word: str) -> str:
    """So'zni normalizatsiya qilish (kichik harf, punktuatsiya tozalash)."""
    word = word.strip().lower()
    word = _PUNCT.sub("", word)
    return word


def _is_good_keyword(word: str) -> bool:
    """So'z savol uchun yaxshi kalit so'zmi?"""
    if not word or len(word) < 3:
        return False
    if word in STOPWORDS:
        return False
    if _NUMERIC.match(word):
        # raqamlar ham foydali bo'lishi mumkin, lekin alohida ishlanadi
        return False
    # Faqat harflardan iborat yoki aralash bo'lsin
    if not re.search(r"[A-Za-zА-Яа-яЁёЀ-ӿʼ'']", word):
        return False
    return True


def _detect_language_simple(text: str) -> str:
    """Matn tilini sodda heuristic bilan aniqlash (uz/ru/en)."""
    sample = text[:2000]
    cyrillic = sum(1 for c in sample if "Ѐ" <= c <= "ӿ")
    latin = sum(1 for c in sample if c.isascii() and c.isalpha())

    if cyrillic > latin * 1.5:
        return "ru"
    if latin > cyrillic * 1.5:
        # O'zbek va inglizni ajratish — o'zbekda maxsus belgilar bor
        if any(marker in sample.lower() for marker in ["o'", "g'", "q", "x", "h"]):
            return "uz"
        return "en"
    return "uz"


# Tilga xos savol shablonlari
QUESTION_TEMPLATES = {
    "uz": {
        "cloze": "Quyidagi gapda nuqtalar o'rniga qaysi so'z qo'yiladi?\n\n«{sentence}»",
        "cloze_inline": "«{sentence}» — gapida «___» o'rniga qaysi so'z mos keladi?",
        "true_sentence": "Quyidagilardan qaysi biri matnda ASOSIY fikr sifatida uchraydi?",
        "first_word": "Matndan olingan quyidagi jumlaning boshlanishi berilgan. To'g'ri davomini tanlang.\n\n«{sentence}»",
        "definition": "«{keyword}» — matnda qanday ta'riflangan?",
        "wrong_fact": "Quyidagi gap to'g'rimi yoki noto'g'rimi?\n\n«{statement}»",
    },
    "ru": {
        "cloze": "Какое слово нужно вставить на место пропуска?\n\n«{sentence}»",
        "cloze_inline": "В предложении «{sentence}» какое слово подходит на место «___»?",
        "true_sentence": "Какое из утверждений является ОСНОВНОЙ мыслью текста?",
        "first_word": "Дано начало предложения. Выберите правильное продолжение.\n\n«{sentence}»",
        "definition": "Как в тексте описывается «{keyword}»?",
        "wrong_fact": "Верно ли следующее утверждение?\n\n«{statement}»",
    },
    "en": {
        "cloze": "Which word fits in the blank?\n\n«{sentence}»",
        "cloze_inline": "In the sentence «{sentence}», which word fits the blank «___»?",
        "true_sentence": "Which of the following is a KEY idea found in the text?",
        "first_word": "The beginning of a sentence is given. Choose the correct ending.\n\n«{sentence}»",
        "definition": "How is «{keyword}» described in the text?",
        "wrong_fact": "Is the following statement true or false?\n\n«{statement}»",
    },
}

EXPLANATION_TEMPLATES = {
    "uz": "To'g'ri javob — matndagi asl jumla/fakt. Boshqa variantlar matnda uchramaydi yoki boshqa ma'noda ishlatilgan.",
    "ru": "Правильный ответ — это оригинальное предложение/факт из текста. Остальные варианты в тексте не встречаются или использованы в другом значении.",
    "en": "The correct answer is the original sentence/fact from the text. Other options don't appear in the text or are used in a different sense.",
}

DIFFICULTY_TEMPLATES = {
    "uz": {
        "easy": "oson",
        "medium": "o'rta",
        "hard": "qiyin",
    },
    "ru": {
        "easy": "лёгкий",
        "medium": "средний",
        "hard": "сложный",
    },
    "en": {
        "easy": "easy",
        "medium": "medium",
        "hard": "hard",
    },
}


# ============== Asosiy klass ==============


class RuleBasedQuestionGenerator:
    """Qoida-asosidagi savol generatori.

    Hech qanday tashqi API chaqirmaydi. Faqat lokal NLP usullari:
    - Gaplarga ajratish (regex)
    - So'zlarni ajratish va normalizatsiya
    - So'z chastotasi (TF) — muhim so'zlarni aniqlash
    - Deterministik tasodifiy tanlash (seed = matn hash) — bir xil matndan
      har doim bir xil savollar olinadi
    """

    def __init__(self) -> None:
        self._redis: Optional["aioredis.Redis"] = None

    async def _get_redis(self) -> Optional["aioredis.Redis"]:
        if not _REDIS_AVAILABLE:
            return None
        if self._redis is None:
            try:
                self._redis = aioredis.from_url(
                    settings.redis_url,
                    password=settings.redis_password or None,
                    decode_responses=True,
                )
            except Exception:
                self._redis = None
        return self._redis

    @staticmethod
    def _cache_key(text: str, count: int, language: str, difficulty: str) -> str:
        content = f"{text[:2000]}|{count}|{language}|{difficulty}"
        return f"quiz:rule:{hashlib.sha256(content.encode()).hexdigest()[:32]}"

    # -------- Matn tahlili --------

    @staticmethod
    def split_sentences(text: str) -> List[str]:
        """Matnni gaplarga bo'lish.

        Vergul bilan ajratilgan qisqa qismlarni emas, nuqta/so'roq/undov
        bilan tugaydigan gaplarni ajratadi.
        """
        # Sahifa/jadval belgilarini tozalash
        text = re.sub(r"\[---.*?---\]", " ", text)
        text = re.sub(r"\[HEADER\].*?\[/HEADER\]", " ", text, flags=re.DOTALL)
        text = re.sub(r"\[FOOTER\].*?\[/FOOTER\]", " ", text, flags=re.DOTALL)
        text = re.sub(r"\[Jadval[^\]]*\]", " ", text)
        text = re.sub(r"\[===.*?===\]", " ", text)

        # Gaplarga bo'lish
        # nuqta, so'roq, undov, va yaponcha/arabcha oxiromatolaridan keyin
        raw_sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZА-ЯЁЎҚҒҲ«\"'])", text)
        result = []
        for s in raw_sentences:
            s = s.strip()
            # Juda qisqa yoki juda uzun gaplarni tashlab ketamiz
            if 20 <= len(s) <= 500:
                result.append(s)
        return result

    @staticmethod
    def tokenize(sentence: str) -> List[str]:
        """Gapni so'zlarga ajratish."""
        # So'zlarni ajratish (harflar, raqamlar, apostroflar)
        words = re.findall(r"[A-Za-zА-Яа-яЁёЎҚҒҲʼ''`]+|\d+", sentence)
        return words

    @staticmethod
    def keyword_score(word: str, frequencies: Counter) -> int:
        """So'zning "kalit so'z" sifatida bahosi.

        Qisqa va keng tarqalgan so'zlar past baho oladi.
        Noodatiy lekin o'rtacha chastotali so'zlar yuqori baho oladi.
        """
        if not _is_good_keyword(word):
            return 0
        freq = frequencies.get(word, 0)
        # 1 <= freq <= 5 bo'lsa eng yaxshi
        if freq == 0:
            return 0
        if freq > 8:
            return 1  # juda ko'p — ehtimol stop-word
        # Uzunlik va chastota kombinatsiyasi
        return 2 + min(len(word) // 4, 3) - abs(3 - freq) // 2

    @staticmethod
    def extract_keywords(text: str, top_n: int = 50) -> List[str]:
        """Matndan muhim kalit so'zlarni ajratib olish."""
        words = RuleBasedQuestionGenerator.tokenize(text)
        words = [_normalize_word(w) for w in words]
        words = [w for w in words if _is_good_keyword(w)]

        if not words:
            return []

        frequencies = Counter(words)

        # Bahlash
        scored = [
            (w, RuleBasedQuestionGenerator.keyword_score(w, frequencies))
            for w in set(words)
        ]
        scored = [(w, s) for w, s in scored if s > 0]
        scored.sort(key=lambda x: (-x[1], -len(x[0])))

        return [w for w, _ in scored[:top_n]]

    # -------- Savol yaratish strategiyalari --------

    @staticmethod
    def _shuffle_deterministic(items: List[Any], seed: int) -> List[Any]:
        """Deterministik tasodifiy aralashtirish (bir xil matn -> bir xil natija)."""
        rng = random.Random(seed)
        items = list(items)
        rng.shuffle(items)
        return items

    @staticmethod
    def _make_cloze_question(
        sentence: str,
        keywords: List[str],
        distractors: List[str],
        language: str,
        difficulty: str,
        qid: int,
    ) -> Optional[Dict[str, Any]]:
        """Bo'sh joy (cloze) savoli yaratish.

        Gapdagi muhim so'zni «___» bilan almashtirib, javob sifatida qaytaradi.
        """
        # Gap ichida bor bo'lgan kalit so'zlardan birini topamiz
        sentence_lower = sentence.lower()
        candidate = None
        for kw in keywords:
            if len(kw) < 4:
                continue
            if kw in sentence_lower:
                candidate = kw
                break

        if not candidate:
            return None

        # Asl so'zning aniq formasini topish (case sensitive)
        match = re.search(re.escape(candidate), sentence, re.IGNORECASE)
        if not match:
            return None

        original = match.group(0)
        cloze_sentence = sentence[: match.start()] + "___" + sentence[match.end() :]

        # Distraktorlar: boshqa kalit so'zlardan
        other_distractors = [d for d in distractors if d != candidate][:3]
        if len(other_distractors) < 3:
            return None

        options = [candidate] + other_distractors
        options = RuleBasedQuestionGenerator._shuffle_deterministic(
            options, seed=hash(candidate) & 0xFFFFFFFF
        )
        correct = options.index(candidate)

        templates = QUESTION_TEMPLATES[language]
        explanation = EXPLANATION_TEMPLATES[language]
        diff_t = DIFFICULTY_TEMPLATES[language]

        return {
            "id": qid,
            "question": templates["cloze_inline"].format(sentence=cloze_sentence),
            "options": options,
            "correct": correct,
            "explanation": f"{explanation} (To'g'ri javob: «{original}»)",
            "difficulty": difficulty if difficulty != "mixed" else diff_t["medium"],
        }

    @staticmethod
    def _make_true_sentence_question(
        true_sentence: str,
        all_sentences: List[str],
        language: str,
        difficulty: str,
        qid: int,
    ) -> Optional[Dict[str, Any]]:
        """Asosiy fikr savoli: 1 ta haqiqiy gap + 3 ta boshqa gap."""
        if len(all_sentences) < 4:
            return None

        other_sentences = [s for s in all_sentences if s != true_sentence]
        if len(other_sentences) < 3:
            return None

        # 3 ta boshqa gap — distraction
        distractors = RuleBasedQuestionGenerator._shuffle_deterministic(
            other_sentences, seed=hash(true_sentence) & 0xFFFFFFFF
        )[:3]

        # Qisqartiramiz (juda uzun bo'lsa)
        def _short(s: str, n: int = 140) -> str:
            s = s.strip()
            if len(s) <= n:
                return s
            return s[: n - 3] + "..."

        options = [_short(true_sentence)] + [_short(s) for s in distractors]
        options = RuleBasedQuestionGenerator._shuffle_deterministic(
            options, seed=hash(true_sentence) & 0xFFFFFFFF
        )
        correct = options.index(_short(true_sentence))

        templates = QUESTION_TEMPLATES[language]
        explanation = EXPLANATION_TEMPLATES[language]
        diff_t = DIFFICULTY_TEMPLATES[language]

        return {
            "id": qid,
            "question": templates["true_sentence"],
            "options": options,
            "correct": correct,
            "explanation": explanation,
            "difficulty": difficulty if difficulty != "mixed" else diff_t["hard"],
        }

    @staticmethod
    def _make_first_word_question(
        sentence: str,
        all_sentences: List[str],
        language: str,
        difficulty: str,
        qid: int,
    ) -> Optional[Dict[str, Any]]:
        """Birinchi so'z savoli: jumlaning birinchi yarmidan keyin nima keladi?"""
        words = sentence.split()
        if len(words) < 8:
            return None

        # Birinchi 30-50% qismini olamiz
        split_point = max(4, len(words) // 2)
        first_part = " ".join(words[:split_point])
        correct_continuation = " ".join(words[split_point : split_point + 8])
        if len(correct_continuation) < 10:
            return None

        # Boshqa gaplardan tasodifiy davomlar
        continuations = []
        for s in all_sentences:
            if s == sentence:
                continue
            sw = s.split()
            if len(sw) < 6:
                continue
            sp = max(4, len(sw) // 2)
            cont = " ".join(sw[sp : sp + 8])
            if len(cont) >= 10:
                continuations.append(cont)

        if len(continuations) < 3:
            return None

        distractors = RuleBasedQuestionGenerator._shuffle_deterministic(
            continuations, seed=hash(sentence) & 0xFFFFFFFF
        )[:3]

        options = [correct_continuation] + distractors
        options = RuleBasedQuestionGenerator._shuffle_deterministic(
            options, seed=hash(correct_continuation) & 0xFFFFFFFF
        )
        correct = options.index(correct_continuation)

        templates = QUESTION_TEMPLATES[language]
        explanation = EXPLANATION_TEMPLATES[language]
        diff_t = DIFFICULTY_TEMPLATES[language]

        return {
            "id": qid,
            "question": templates["first_word"].format(sentence=first_part),
            "options": options,
            "correct": correct,
            "explanation": explanation,
            "difficulty": difficulty if difficulty != "mixed" else diff_t["hard"],
        }

    @staticmethod
    def _make_keyword_question(
        keyword: str,
        sentence_with_keyword: str,
        distractors: List[str],
        language: str,
        difficulty: str,
        qid: int,
    ) -> Optional[Dict[str, Any]]:
        """Kalit so'z savoli: so'zning ma'nosi qaysi gapda ko'rsatilgan?"""
        if len(distractors) < 3:
            return None

        templates = QUESTION_TEMPLATES[language]
        explanation = EXPLANATION_TEMPLATES[language]
        diff_t = DIFFICULTY_TEMPLATES[language]

        # Savol matni
        question = templates["definition"].format(keyword=keyword)
        correct = sentence_with_keyword
        # distractors — boshqa kalit so'zlar
        options = [correct] + list(distractors[:3])
        options = RuleBasedQuestionGenerator._shuffle_deterministic(
            options, seed=hash(keyword) & 0xFFFFFFFF
        )
        correct_idx = options.index(correct)

        return {
            "id": qid,
            "question": question,
            "options": options,
            "correct": correct_idx,
            "explanation": f"{explanation} (Kalit so'z: «{keyword}»)",
            "difficulty": difficulty if difficulty != "mixed" else diff_t["easy"],
        }

    @staticmethod
    def _make_numeric_question(
        number_str: str,
        sentence: str,
        all_sentences: List[str],
        language: str,
        difficulty: str,
        qid: int,
    ) -> Optional[Dict[str, Any]]:
        """Raqam/fakt savoli.

        Gapdagi raqam o'rniga noto'g'ri raqam qo'yiladi va "to'g'rimi?" deb
        so'raladi. Bu yerda sodda varianti — matndan raqamli fakt va uning
        o'zgartirilgan versiyasi taqdim etiladi.
        """
        if not number_str or not re.search(r"\d", number_str):
            return None

        # Raqamni biroz o'zgartiramiz (noto'g'ri variant)
        try:
            n = float(number_str.replace(",", "."))
        except ValueError:
            return None

        wrong_n = n + random.Random(hash(number_str) & 0xFFFFFFFF).choice(
            [-2, -1, 1, 2, 5, 10]
        )
        if wrong_n == n:
            wrong_n = n + 1

        wrong_str = (
            str(int(wrong_n))
            if wrong_n == int(wrong_n)
            else f"{wrong_n:.1f}"
        )
        correct_str = number_str

        # Gapdagi raqamni almashtiramiz
        original_sentence = sentence
        modified_sentence = re.sub(
            re.escape(number_str), wrong_str, original_sentence, count=1
        )
        if modified_sentence == original_sentence:
            return None

        # To'g'ri javob — "Noto'g'ri" (gapda raqam boshqa)
        # variantlar: To'g'ri / Noto'g'ri / Matndan aniqlab bo'lmaydi
        if language == "uz":
            options = ["To'g'ri", "Noto'g'ri", "Matndan aniqlab bo'lmaydi"]
            explanation = (
                f"Matnda aslida «{correct_str}» deyilgan, "
                f"bu yerda «{wrong_str}» yozilgan — noto'g'ri."
            )
        elif language == "ru":
            options = ["Верно", "Неверно", "Нельзя определить из текста"]
            explanation = (
                f"В тексте указано «{correct_str}», "
                f"здесь написано «{wrong_str}» — неверно."
            )
        else:
            options = ["True", "False", "Cannot be determined from the text"]
            explanation = (
                f"The text actually says «{correct_str}», "
                f"here it says «{wrong_str}» — false."
            )

        templates = QUESTION_TEMPLATES[language]
        diff_t = DIFFICULTY_TEMPLATES[language]

        return {
            "id": qid,
            "question": templates["wrong_fact"].format(statement=modified_sentence),
            "options": options,
            "correct": 1,  # "Noto'g'ri"
            "explanation": explanation,
            "difficulty": difficulty if difficulty != "mixed" else diff_t["hard"],
        }

    # -------- Yuqori darajadagi API --------

    async def generate_questions(
        self,
        text: str,
        count: int = 10,
        language: str = "uz",
        difficulty: str = "mixed",
    ) -> List[Dict[str, Any]]:
        """Matndan savollar generatsiya qilish (BEPUL, onlaynsiz).

        Args:
            text: Manba matn (PDF/DOCX dan ajratilgan).
            count: Savollar soni (1-50).
            language: Savol tili (uz/ru/en).
            difficulty: easy/medium/hard/mixed.

        Returns:
            Savollar ro'yxati (dict).
        """
        # Limit
        count = max(1, min(count, settings.max_questions_per_test))

        # Tilni tekshirish
        if language not in ("uz", "ru", "en"):
            language = "uz"

        # Qiyinlikni tekshirish
        if difficulty not in ("easy", "medium", "hard", "mixed"):
            difficulty = "mixed"

        # Cache
        cache_key = self._cache_key(text, count, language, difficulty)
        try:
            redis = await self._get_redis()
            if redis is not None:
                cached = await redis.get(cache_key)
                if cached:
                    import json
                    return json.loads(cached)
        except Exception:
            pass

        # Tilni avtomatik aniqlash (agar 'auto' bo'lsa yoki bo'sh bo'lsa)
        detected = _detect_language_simple(text)
        if language == "auto" or not language:
            language = detected

        # Gaplarga bo'lish
        sentences = self.split_sentences(text)
        if not sentences:
            # Hech bo'lmaganda 1 ta fallback savol
            return self._fallback_questions(text, count, language, difficulty)

        # Kalit so'zlarni ajratish
        keywords = self.extract_keywords(text, top_n=max(60, count * 6))
        if not keywords:
            return self._fallback_questions(text, count, language, difficulty)

        # Detrministik seed — bir xil matn -> bir xil savollar
        seed = int(hashlib.sha256(text[:2000].encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)

        questions: List[Dict[str, Any]] = []
        used_sentences: set = set()
        qid = 1

        # Strategiyalar: har bir savol uchun tasodifiy birini tanlaymiz
        # (lekin imkon qadar har xil strategiyalardan foydalanamiz)
        strategies = [
            "cloze",
            "true_sentence",
            "first_word",
            "keyword",
            "numeric",
        ]
        strategy_cycle = strategies * (count // len(strategies) + 2)
        rng.shuffle(strategy_cycle)

        for strategy in strategy_cycle:
            if len(questions) >= count:
                break

            # Ishlatilmagan gapni tanlash
            available = [s for s in sentences if s not in used_sentences]
            if not available:
                used_sentences.clear()
                available = sentences

            sentence = rng.choice(available)

            # Qiyinlik
            diff = difficulty
            if difficulty == "mixed":
                # Aslida savol darajasini strategiya belgilaydi
                diff = "medium"

            q: Optional[Dict[str, Any]] = None

            try:
                if strategy == "cloze":
                    # Distraction sifatida boshqa kalit so'zlar
                    distractors = [k for k in keywords if k in sentence.lower()]
                    other_keywords = [k for k in keywords if k not in sentence.lower()]
                    rng.shuffle(other_keywords)
                    distractors.extend(other_keywords[:3])
                    q = self._make_cloze_question(
                        sentence=sentence,
                        keywords=keywords,
                        distractors=distractors,
                        language=language,
                        difficulty=diff,
                        qid=qid,
                    )

                elif strategy == "true_sentence":
                    q = self._make_true_sentence_question(
                        true_sentence=sentence,
                        all_sentences=sentences,
                        language=language,
                        difficulty=diff,
                        qid=qid,
                    )

                elif strategy == "first_word":
                    q = self._make_first_word_question(
                        sentence=sentence,
                        all_sentences=sentences,
                        language=language,
                        difficulty=diff,
                        qid=qid,
                    )

                elif strategy == "keyword":
                    # Kalit so'z va uni o'z ichiga olgan gap
                    chosen_kw = None
                    sentence_with_kw = None
                    for kw in keywords:
                        if kw in sentence.lower():
                            chosen_kw = kw
                            sentence_with_kw = sentence
                            break
                    if chosen_kw and sentence_with_kw:
                        # distractors — boshqa kalit so'zlar
                        other_kws = [k for k in keywords if k != chosen_kw]
                        rng.shuffle(other_kws)
                        q = self._make_keyword_question(
                            keyword=chosen_kw,
                            sentence_with_keyword=sentence_with_kw,
                            distractors=other_kws,
                            language=language,
                            difficulty=diff,
                            qid=qid,
                        )

                elif strategy == "numeric":
                    # Gapdagi raqamni topish
                    numbers = re.findall(r"\b\d+(?:[.,]\d+)?\b", sentence)
                    if numbers:
                        q = self._make_numeric_question(
                            number_str=numbers[0],
                            sentence=sentence,
                            all_sentences=sentences,
                            language=language,
                            difficulty=diff,
                            qid=qid,
                        )
            except Exception:
                q = None

            if q is not None:
                questions.append(q)
                used_sentences.add(sentence)
                qid += 1
            else:
                # Bu gap yaroqsiz bo'lib chiqdi, belgilab qo'yamiz
                used_sentences.add(sentence)

        # Agar savollar kam bo'lsa, fallback bilan to'ldiramiz
        if len(questions) < count:
            extra = await self._fallback_questions(
                text, count - len(questions), language, difficulty, start_id=qid
            )
            questions.extend(extra)

        # ID larni qayta raqamlash
        for i, q in enumerate(questions, 1):
            q["id"] = i

        # Cache ga yozish
        if questions:
            try:
                import json
                redis = await self._get_redis()
                if redis is not None:
                    await redis.setex(
                        cache_key, 86400, json.dumps(questions, ensure_ascii=False)
                    )
            except Exception:
                pass

        return questions

    async def _fallback_questions(
        self,
        text: str,
        count: int,
        language: str,
        difficulty: str,
        start_id: int = 1,
    ) -> List[Dict[str, Any]]:
        """Matndan savol yaratib bo'lmasa, eng oddiy savollar."""
        sentences = self.split_sentences(text)
        if not sentences:
            # Eng oddiy: matnni qisqartirib, 1 ta savol
            snippet = (text[:200] + "...") if len(text) > 200 else text
            return [{
                "id": start_id,
                "question": "Matn nima haqida?" if language == "uz" else
                            "О чём этот текст?" if language == "ru" else
                            "What is this text about?",
                "options": [snippet, "Boshqa mavzu", "Aniq emas", "Matnda yo'q"],
                "correct": 0,
                "explanation": "Bu matnning asosiy mazmuni.",
                "difficulty": "easy",
            }]

        # Eng muhim gaplarni olish
        scored = [(s, len(s)) for s in sentences]
        scored.sort(key=lambda x: -x[1])
        top_sentences = [s for s, _ in scored[:count]]

        results: List[Dict[str, Any]] = []
        for i, s in enumerate(top_sentences):
            short = s[:140] + ("..." if len(s) > 140 else "")
            other = [t for t in top_sentences if t != s][:3]
            if len(other) < 3:
                other.extend([
                    "Matnda bunday ma'lumot yo'q",
                    "Boshqa mavzuga oid",
                    "Aniqlab bo'lmaydi",
                ][: 3 - len(other)])

            options = [short] + [o[:140] + ("..." if len(o) > 140 else "") for o in other[:3]]
            options = self._shuffle_deterministic(options, seed=hash(s) & 0xFFFFFFFF)
            correct = options.index(short)

            if language == "uz":
                question = "Matndan olingan qaysi gap asosiy fikrni ifodalaydi?"
            elif language == "ru":
                question = "Какое из утверждений отражает основную мысль текста?"
            else:
                question = "Which sentence best expresses the main idea of the text?"

            results.append({
                "id": start_id + i,
                "question": question,
                "options": options,
                "correct": correct,
                "explanation": "Bu matndan olingan asl jumla.",
                "difficulty": "medium",
            })

        return results

    async def detect_language(self, text: str) -> str:
        """Matn tilini aniqlash."""
        return _detect_language_simple(text)


# Singleton — butun loyiha bo'ylab bitta instance
rule_based_generator = RuleBasedQuestionGenerator()
