"""Painel admin do portfolio (FastAPI). Entrada para 'uvicorn main:app'.

Servico no homesrv: simple-vibe@portfolio-admin.service (porta 8005)."""
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import db
import security
from content import router as content_router
from publish import router as publish_router

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("portfolio-admin")

START = time.time()
REQUESTS_TOTAL = 0
ERRORS_TOTAL = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    logger.info("startup ok db=%s", db.DB_PATH)
    yield
    logger.info("shutdown ok")


app = FastAPI(title="portfolio-admin-api", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def metrics_mw(request: Request, call_next):
    global REQUESTS_TOTAL, ERRORS_TOTAL
    REQUESTS_TOTAL += 1
    t0 = time.time()
    status = 0
    try:
        resp = await call_next(request)
        status = resp.status_code
        return resp
    except Exception:
        ERRORS_TOTAL += 1
        raise
    finally:
        dt = (time.time() - t0) * 1000
        logger.info("%s %s %d %.1fms", request.method, request.url.path, status, dt)


_cors = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
if _cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


class LoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=200)


def _set_auth_cookies(response: JSONResponse, session: str, csrf: str):
    secure = security.cookie_secure()
    response.set_cookie(security.SESSION_COOKIE, session, httponly=True, samesite="strict",
                        secure=secure, path="/", max_age=security.SESSION_MAX_AGE)
    response.set_cookie(security.CSRF_COOKIE, csrf, httponly=False, samesite="strict",
                        secure=secure, path="/", max_age=security.SESSION_MAX_AGE)


@app.post("/api/auth/login")
def login(body: LoginIn, request: Request):
    ip = security.client_ip(request)
    if security.login_rate_limited(ip):
        raise HTTPException(429, "muitas tentativas; aguarde")
    with db.connect() as conn:
        row = conn.execute("SELECT username, password_hash FROM user WHERE username = ?",
                           (body.username.strip(),)).fetchone()
    if not row or not security.verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "credenciais invalidas")
    session = security.create_session(row["username"])
    csrf = security.new_csrf()
    response = JSONResponse({"ok": True, "username": row["username"]})
    _set_auth_cookies(response, session, csrf)
    return response


@app.post("/api/auth/logout")
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(security.SESSION_COOKIE, path="/")
    response.delete_cookie(security.CSRF_COOKIE, path="/")
    return response


@app.get("/api/auth/me")
def me(username: str = Depends(security.require_auth)):
    return {"authenticated": True, "username": username}


@app.get("/api/csrf")
def csrf():
    csrf = security.new_csrf()
    response = JSONResponse({"token": csrf})
    secure = security.cookie_secure()
    response.set_cookie(security.CSRF_COOKIE, csrf, httponly=False, samesite="strict",
                        secure=secure, path="/", max_age=security.SESSION_MAX_AGE)
    return response


app.include_router(content_router)
app.include_router(publish_router)


@app.get("/health")
def health():
    status = "ok"
    try:
        with db.connect() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception as err:  # noqa: BLE001
        status = f"error: {err}"
    return {
        "status": "ok" if status == "ok" else "degraded",
        "db": status,
        "uptime_sec": round(time.time() - START, 2),
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/info")
def info():
    return {
        "app": "portfolio-admin-api",
        "version": "0.1.0",
        "db_path": db.DB_PATH,
        "sqlite_wal": True,
    }


@app.get("/metrics")
def metrics():
    return {
        "requests_total": REQUESTS_TOTAL,
        "errors_total": ERRORS_TOTAL,
        "uptime_sec": round(time.time() - START, 2),
    }


# Imagens enviadas (certificados e projetos) servidas para preview no painel.
# UPLOADS_DIR = <data>/uploads/certs e PROJECTS_UPLOADS_DIR = <data>/uploads/projects,
# entao o pai (<data>/uploads) expoe os dois sob /uploads/certs e /uploads/projects.
_uploads_root = os.path.dirname(db.UPLOADS_DIR)
os.makedirs(_uploads_root, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_uploads_root), name="uploads")


# Frontend estatico (repo portfolio-admin) servido na raiz, depois das rotas /api.
_static = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(os.path.join(_static, "index.html")):
    app.mount("/", StaticFiles(directory=_static, html=True), name="static")
