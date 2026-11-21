"""Project-wide constants. REFUSAL_TEXT must stay word-for-word (see CLAUDE.md)."""

from typing import Literal

REFUSAL_TEXT = "দুঃখিত, এই প্রশ্নের উত্তর আমার কাছে থাকা সরকারি নথিতে পাইনি। সাহায্যের জন্য জাতীয় হেল্পলাইন ৩৩৩-এ কল করুন।"

RATE_LIMIT_TEXT = "কিছুক্ষণ পর আবার চেষ্টা করুন।"

Area = Literal["land", "gd", "allowance", "labour"]
AREAS: tuple[str, ...] = ("land", "gd", "allowance", "labour")

Status = Literal["answered", "partial", "refused", "clarify"]
