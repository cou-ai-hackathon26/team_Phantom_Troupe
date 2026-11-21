"""Project-wide constants. REFUSAL_TEXT must stay word-for-word (see CLAUDE.md)."""

from typing import Literal

REFUSAL_TEXT = "দুঃখিত, এই প্রশ্নের উত্তর আমার কাছে থাকা সরকারি নথিতে পাইনি। সাহায্যের জন্য জাতীয় হেল্পলাইন ৩৩৩-এ কল করুন।"

RATE_LIMIT_TEXT = "কিছুক্ষণ পর আবার চেষ্টা করুন।"

# "general" = every other Bangladesh law (Chronological Index, NHRC, …); added for the full DataSet.
Area = Literal["land", "gd", "allowance", "labour", "general"]
AREAS: tuple[str, ...] = ("land", "gd", "allowance", "labour", "general")

Status = Literal["answered", "partial", "refused", "clarify"]
