import time, hmac, hashlib, base64
from typing import Tuple
from config import app_cfg

def _sign(data: bytes) -> str:
    sig = hmac.new(app_cfg.secret_key.encode(), data, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")

def make_token(payload: str, ttl_seconds: int) -> str:
    exp = int(time.time()) + ttl_seconds
    raw = f"{payload}|{exp}".encode()
    b = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    sig = _sign(b.encode())
    return f"{b}.{sig}"

def verify_token(token: str) -> Tuple[bool, str]:
    try:
        b, sig = token.split(".", 1)
        if _sign(b.encode()) != sig:
            return (False, "bad-signature")
        raw = base64.urlsafe_b64decode(b + "===")
        payload, exp = raw.decode().split("|", 1)
        if int(exp) < int(time.time()):
            return (False, "expired")
        return (True, payload)
    except Exception:
        return (False, "invalid")
