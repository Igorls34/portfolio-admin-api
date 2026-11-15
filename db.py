"""Conexao SQLite (WAL) e inicializacao do banco."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv

# Carrega .env aqui (e nao so no main) para que qualquer entrypoint — uvicorn
# ou o seed.py — enxergue DB_PATH/ADMIN_PASSWORD etc. sem duplicar a leitura.
load_dotenv()

DB_PATH = os.getenv("DB_PATH", "./data.db")
DATA_DIR = os.path.dirname(os.path.abspath(DB_PATH))
UPLOADS_DIR = os.getenv(
    "UPLOADS_DIR",
    os.path.join(DATA_DIR, "uploads", "certs"),
)
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


@contextmanager
def connect():
    """Yield uma conexao e commit ao final (rollback em erro). Sempre fecha."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    with connect() as conn:
        schema = Path(SCHEMA_PATH).read_text(encoding="utf-8")
        conn.executescript(schema)
    _bootstrap_admin()


def _bootstrap_admin() -> None:
    """Cria o usuario unico na primeira subida. Sem senha no env, gera uma
    aleatoria e imprime no log (journalctl -u simple-vibe@portfolio-admin)."""
    import logging
    log = logging.getLogger("portfolio-admin")
    with connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM user").fetchone()
        if row["n"] > 0:
            return
        from security import hash_password
        username = os.getenv("ADMIN_USERNAME", "admin").strip() or "admin"
        password = os.getenv("ADMIN_PASSWORD", "").strip()
        generated = False
        if not password:
            import secrets
            password = secrets.token_urlsafe(16)
            generated = True
        conn.execute(
            "INSERT INTO user (username, password_hash) VALUES (?, ?)",
            (username, hash_password(password)),
        )
    if generated:
        log.warning("ADMIN_PASSWORD vazio: usuario '%s' criado com senha aleatoria. "
                    "Guarde-a: %s", username, password)
    else:
        log.info("usuario unico '%s' criado", username)


def read_site_json() -> dict:
    with connect() as conn:
        row = conn.execute("SELECT value FROM site WHERE key = 'site'").fetchone()
    if not row:
        return {}
    import json
    return json.loads(row["value"])


def write_site_json(site: dict) -> None:
    import json
    with connect() as conn:
        conn.execute(
            "INSERT INTO site (key, value) VALUES ('site', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(site, ensure_ascii=False),),
        )
