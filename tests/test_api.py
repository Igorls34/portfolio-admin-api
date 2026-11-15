import os
import tempfile

# Precisa acontecer ANTES de importar main/db (DB_PATH e lido no import).
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "test-password"
os.environ["SECRET_KEY"] = "test-secret"
os.environ.pop("GITHUB_TOKEN", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import db  # noqa: E402
import main  # noqa: E402
from security import CSRF_COOKIE  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    for suffix in ("", "-wal", "-shm"):
        path = db.DB_PATH + suffix
        if os.path.exists(path):
            os.remove(path)
    yield


def _login(c: TestClient) -> None:
    r = c.post("/api/auth/login", json={"username": "admin", "password": "test-password"})
    assert r.status_code == 200, r.text


def _csrf(c: TestClient) -> str:
    return c.cookies.get(CSRF_COOKIE, "")


def test_health():
    with TestClient(main.app) as c:
        r = c.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_login_recusa_senha_errada():
    with TestClient(main.app) as c:
        r = c.post("/api/auth/login", json={"username": "admin", "password": "errada"})
        assert r.status_code == 401


def test_api_exige_autenticacao():
    with TestClient(main.app) as c:
        r = c.get("/api/skills")
        assert r.status_code == 401


def test_mutacao_exige_csrf():
    with TestClient(main.app) as c:
        _login(c)
        r = c.post("/api/skills", json={"title": "x", "icon": "", "description": ""})
        assert r.status_code == 403


def test_crud_skill():
    with TestClient(main.app) as c:
        _login(c)
        t = _csrf(c)
        r = c.post("/api/skills", json={"icon": "fa-x", "title": "Teste", "description": "d"},
                   headers={"X-CSRF-Token": t})
        assert r.status_code == 200
        sid = r.json()["id"]

        r = c.get("/api/skills")
        assert any(s["title"] == "Teste" for s in r.json())

        r = c.put(f"/api/skills/{sid}", json={"icon": "fa-x", "title": "Teste2", "description": "d"},
                  headers={"X-CSRF-Token": t})
        assert r.json()["title"] == "Teste2"

        r = c.delete(f"/api/skills/{sid}", headers={"X-CSRF-Token": t})
        assert r.status_code == 200


def test_projeto_com_techs_e_links():
    with TestClient(main.app) as c:
        _login(c)
        t = _csrf(c)
        payload = {
            "id": "proj_teste", "icon": "fa-x", "title": "P", "description": "d",
            "techs": ["a", "b"],
            "links": [{"label": "L", "href": "https://x", "track": "t"}],
        }
        r = c.post("/api/projects", json=payload, headers={"X-CSRF-Token": t})
        assert r.status_code == 200, r.text

        r = c.get("/api/projects")
        p = next(x for x in r.json() if x["id"] == "proj_teste")
        assert p["techs"] == ["a", "b"]
        assert p["links"][0]["href"] == "https://x"


def test_site_put_get():
    with TestClient(main.app) as c:
        _login(c)
        t = _csrf(c)
        site = {
            "hero": {"title": "Igor", "tagline": "x"},
            "about": {"paragraphs": ["p1", "p2"]},
            "contact": {"whatsapp_number": "5524998574876"},
            "social": [{"label": "GitHub", "href": "https://github.com/Igorls34", "icon": "fa-brands fa-github", "track": "social_github"}],
        }
        r = c.put("/api/site", json=site, headers={"X-CSRF-Token": t})
        assert r.status_code == 200
        r = c.get("/api/site")
        assert r.json()["hero"]["title"] == "Igor"
        assert r.json()["contact"]["whatsapp_number"] == "5524998574876"


def test_publish_sem_configuracao_devolve_503():
    with TestClient(main.app) as c:
        _login(c)
        t = _csrf(c)
        r = c.post("/api/publish", headers={"X-CSRF-Token": t})
        assert r.status_code == 503
