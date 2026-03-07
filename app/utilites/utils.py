from __future__ import annotations
import re, secrets, string


def generative_invite_code(length: int = 8) -> str:
    alpha = "".join(c for c in string.ascii_uppercase + string.digits if c not in "O0I1")
    return "".join(secrets.choice(alpha) for _ in range(length))


def sanitize(s: str, max_len: int = 4000) -> str:
    if not s:
        return ""
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", s[:max_len])
    return s.strip()