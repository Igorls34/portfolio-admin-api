"""Autenticacao de usuario unico: senha (scrypt do stdlib), sessao assinada
(cookie HttpOnly) e CSRF por double-submit cookie."""
import base64
import hashlib
import hmac
import os
import secrets
import time

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from db import DATA_DIR

SESSION_COOKIE = "portfolio_admin_session"
CSRF_COOKIE = "portfolio_admin_csrf"
SESSION_MAX_AGE = 7 * 86400  # 7 dias

_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 64


def get_secret() -> str:
    env = os.getenv("SECRET_KEY", "").strip()
    if env:
        return env
    path = os.path.join(DATA_DIR, "secret.key")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    value = secrets.token_urlsafe(48)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(value)
    os.chmod(path, 0o600)
    return value


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_DKLEN)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        scheme, salt_b64, dk_b64 = hashed.split("$", 2)
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(dk_b64)
        dk = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                            n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=len(expected))
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_secret(), salt="portfolio-admin-session")


def create_session(username: str) -> str:
    return _serializer().dumps({"sub": username})


def read_session(cookie: str):
    if not cookie:
        return None
    try:
        return _serializer().loads(cookie, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def new_csrf() -> str:
    return secrets.token_urlsafe(24)


def cookie_secure() -> bool:
    return os.getenv("COOKIE_SECURE", "false").lower() in ("1", "true", "yes")


# ---- Rate limit simples do login (por IP) ----
_login_hits: dict = {}


def login_rate_limited(ip: str) -> bool:
    now = time.time()
    window = 300
    max_attempts = 10
    hits = [t for t in _login_hits.get(ip, []) if now - t < window]
    if len(hits) >= max_attempts:
        _login_hits[ip] = hits
        return True
    hits.append(now)
    _login_hits[ip] = hits
    if len(_login_hits) > 5000:
        _login_hits.clear()
    return False


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "desconhecido"


# ---- Dependencias FastAPI ----

async def require_auth(request: Request) -> str:
    data = read_session(request.cookies.get(SESSION_COOKIE))
    if not data or not data.get("sub"):
        raise HTTPException(401, "nao-autenticado")
    return data["sub"]


async def require_csrf(request: Request) -> None:
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get("x-csrf-token", "")
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise HTTPException(403, "csrf-invalido")
