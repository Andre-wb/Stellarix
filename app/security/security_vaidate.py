"""
Валидация паролей и утилиты безопасности.
Перенесено из старого проекта и улучшено.
"""
from __future__ import annotations
import re
import secrets
import string
from typing import Tuple


# ══════════════════════════════════════════════════════════════════════════════
# Валидация пароля
# ══════════════════════════════════════════════════════════════════════════════

_COMMON_PASSWORDS = frozenset([
    "password", "123456", "qwerty", "admin", "welcome", "password123",
    "12345678", "123456789", "123123", "111111", "пароль", "1234567890",
    "йцукен", "letmein", "monkey", "dragon", "baseball", "football",
    "master", "hello", "freedom", "qazwsx", "trustno1", "sunshine",
    "iloveyou", "starwars", "princess",
])

_SEQUENCES = [
    r"012|123|234|345|456|567|678|789|890|098|987|876|765|654|543|432|321|210",
    r"qwerty|asdfgh|zxcvbn|йцукен|фывапр|ячсмит",
    r"abcdef|bcdefg|cdefgh|defghi|efghij|fghijk",
]


def validate_password(password: str) -> Tuple[bool, str]:
    """
    Проверяет пароль по требованиям безопасности.
    Возвращает (ok, error_message).
    """
    if len(password) < 8:
        return False, "Пароль минимум 8 символов"
    if len(password) > 128:
        return False, "Пароль максимум 128 символов"

    checks = [
        (r"[A-ZА-Я]",                          "хотя бы одну заглавную букву"),
        (r"[a-zа-я]",                          "хотя бы одну строчную букву"),
        (r"\d",                                "хотя бы одну цифру"),
        (r'[!@#$%^&*()\-_=+\[\]{};:\'",.<>/?\\|`~]', "хотя бы один специальный символ"),
    ]
    for pattern, msg in checks:
        if not re.search(pattern, password):
            return False, f"Пароль должен содержать {msg}"

    if password.lower() in _COMMON_PASSWORDS:
        return False, "Пароль слишком простой"

    if re.search(r"(.)\1{3,}", password):
        return False, "Слишком много повторяющихся символов"

    for seq in _SEQUENCES:
        if re.search(seq, password.lower()):
            return False, "Пароль содержит простую последовательность"

    return True, ""


def validate_password_with_context(
        password: str, username: str = "", phone: str = ""
) -> Tuple[bool, str]:
    ok, msg = validate_password(password)
    if not ok:
        return ok, msg
    if username and len(username) > 2 and username.lower() in password.lower():
        return False, "Пароль не должен содержать ваш никнейм"
    return True, ""


def calculate_password_strength(password: str) -> dict:
    """Оценка стойкости пароля — для отображения в UI."""
    score = 0
    feedback = []

    if len(password) >= 12:
        score += 25
        feedback.append("✓ Длина отличная")
    elif len(password) >= 8:
        score += 15
        feedback.append("✓ Длина хорошая")
    else:
        feedback.append("✗ Слишком короткий")

    for pat, pts, desc in [
        (r"[A-ZА-Я]", 10, "Заглавные буквы"),
        (r"[a-zа-я]", 10, "Строчные буквы"),
        (r"\d",       10, "Цифры"),
        (r'[!@#$%^&*]', 15, "Специальные символы"),
    ]:
        if re.search(pat, password):
            score += pts
            feedback.append(f"✓ {desc}")
        else:
            feedback.append(f"✗ {desc}")

    for pat, penalty, reason in [
        (r"(.)\1{3,}",          20, "Много повторяющихся символов"),
        (r"123|234|456|789",    15, "Числовая последовательность"),
        (r"qwerty|asdf",        20, "Клавиатурная последовательность"),
    ]:
        if re.search(pat, password.lower()):
            score -= penalty
            feedback.append(f"⚠ {reason}")

    score = max(0, min(score, 100))

    if score >= 80:   level, color = "Очень сильный", "green"
    elif score >= 60: level, color = "Сильный",       "lightgreen"
    elif score >= 40: level, color = "Средний",       "orange"
    elif score >= 20: level, color = "Слабый",        "red"
    else:             level, color = "Очень слабый",  "darkred"

    return {
        "score": score, "strength": level, "color": color, "feedback": feedback,
        "has_upper":   bool(re.search(r"[A-ZА-Я]",  password)),
        "has_lower":   bool(re.search(r"[a-zа-я]",  password)),
        "has_digits":  bool(re.search(r"\d",         password)),
        "has_symbols": bool(re.search(r'[!@#$%^&*]', password)),
    }


def generate_secure_password(length: int = 16) -> str:
    """Генерирует стойкий пароль."""
    length = max(12, min(length, 64))
    chars = (
            [secrets.choice(string.ascii_lowercase)]
            + [secrets.choice(string.ascii_uppercase)]
            + [secrets.choice(string.digits)]
            + [secrets.choice("!@#$%^&*()-_=+")]
    )
    all_chars = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    chars += [secrets.choice(all_chars) for _ in range(length - 4)]
    secrets.SystemRandom().shuffle(chars)
    result = "".join(chars)
    ok, _ = validate_password(result)
    return result if ok else generate_secure_password(length)