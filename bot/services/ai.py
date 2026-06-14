"""AI service - savol generatsiya qilish (bepul, qoida-asosida).

Eski versiya OpenAI/Anthropic API larga murojaat qilardi. Endi bu modul
to'liq lokal ishlaydi — tashqi API, internet yoki API kalitlari kerak emas.

Asosiy ish bajaruvchi modul: ``bot.services.rule_based_ai``.

Ushbu fayl eski kod bilan mos (backward compatible) — `ai_service` va
`AIService` klassi nomlari saqlanib qolgan, shu sababli handlerlar va
API kodlarini o'zgartirish shart emas.
"""
from __future__ import annotations

import logging
from typing import List, Dict, Any

from bot.services.rule_based_ai import rule_based_generator

logger = logging.getLogger(__name__)


# Eski kod bilan mos bo'lish uchun bo'sh placeholder. Ilova hech qachon
# tashqi providerga ulanmaydi — lekin atribut o'qilishi mumkinligi uchun
# saqlab qo'yamiz.
SYSTEM_PROMPT = (
    "Bu modul endi qoida-asosidagi lokal generator ishlatadi. "
    "Tashqi AI providerlari (OpenAI, Anthropic) ishlatilmaydi."
)


class AIService:
    """Savol generatsiya qilish xizmati (BEPUL, qoida-asosida).

    Public API:
        - generate_questions(text, count, language, difficulty) -> List[Dict]
        - detect_language(text) -> str

    Eski kod bilan moslik uchun saqlangan. Aslida barcha ishni
    ``rule_based_generator`` bajaradi.
    """

    def __init__(self) -> None:
        self.provider = "rule_based"
        self.model = "local-rule-based-v1"
        self._delegate = rule_based_generator

    async def generate_questions(
        self,
        text: str,
        count: int = 10,
        language: str = "uz",
        difficulty: str = "mixed",
    ) -> List[Dict[str, Any]]:
        """Matndan savol yaratish.

        Args:
            text: Manba matn.
            count: Savollar soni (1-50).
            language: Savol tili (uz/ru/en/auto).
            difficulty: easy/medium/hard/mixed.

        Returns:
            Savollar ro'yxati.
        """
        return await self._delegate.generate_questions(
            text=text,
            count=count,
            language=language,
            difficulty=difficulty,
        )

    async def detect_language(self, text: str) -> str:
        """Matn tilini aniqlash (uz/ru/en)."""
        return await self._delegate.detect_language(text)

    # Quyidagi metodlar eski kod bilan mos bo'lish uchun saqlangan, lekin
    # endi ishlatilmaydi (tashqi provider yo'q).
    async def get_client(self):  # pragma: no cover
        return None

    async def get_redis(self):  # pragma: no cover
        return await self._delegate._get_redis()


# Singleton
ai_service = AIService()
