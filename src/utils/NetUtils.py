import re


def is_connection_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "apiconnectionerror" in msg
        or "connection error" in msg
        or "decodingerror" in msg
        or "decompressobj" in msg
    )


def is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg


def extract_retry_seconds(text: str, default: int = 10) -> int:
    if not text:
        return default
    match = re.search(r"retry[- ]after[: ]+(\d+)", text, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except Exception:
            return default
    match = re.search(r"retry in (\d+)\s*seconds", text, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except Exception:
            return default
    return default
