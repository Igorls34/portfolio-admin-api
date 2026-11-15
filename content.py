"""CRUD do conteudo do portfolio + geracao do portfolio.json."""
import json
import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

import db
import schemas
from convert import cert_image_path, pdf_to_webp
from security import require_auth, require_csrf

router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])


def _row(r) -> dict:
    return dict(r) if r is not None else None


# ---------- Skills ----------

@router.get("/skills", response_model=List[schemas.SkillOut])
def list_skills():
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, icon, title, description, position FROM skills ORDER BY position, id"
        ).fetchall()
    return [_row(r) for r in rows]


@router.post("/skills", response_model=schemas.SkillOut, dependencies=[Depends(require_csrf)])
def create_skill(item: schemas.SkillIn):
    with db.connect() as conn:
        pos = conn.execute("SELECT COALESCE(MAX(position), -1) + 1 AS p FROM skills").fetchone()["p"]
        cur = conn.execute(
            "INSERT INTO skills (icon, title, description, position) VALUES (?, ?, ?, ?)",
            (item.icon.strip(), item.title.strip(), item.description.strip(), pos),
        )
        row = conn.execute("SELECT id, icon, title, description, position FROM skills WHERE id = ?",
                           (cur.lastrowid,)).fetchone()
    return _row(row)


@router.put("/skills/{skill_id}", response_model=schemas.SkillOut, dependencies=[Depends(require_csrf)])
def update_skill(skill_id: int, item: schemas.SkillIn):
    with db.connect() as conn:
        cur = conn.execute(
            "UPDATE skills SET icon = ?, title = ?, description = ? WHERE id = ?",
            (item.icon.strip(), item.title.strip(), item.description.strip(), skill_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "skill nao encontrada")
        row = conn.execute("SELECT id, icon, title, description, position FROM skills WHERE id = ?",
                           (skill_id,)).fetchone()
    return _row(row)


@router.delete("/skills/{skill_id}", dependencies=[Depends(require_csrf)])
def delete_skill(skill_id: int):
    with db.connect() as conn:
        cur = conn.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "skill nao encontrada")
    return {"ok": True}


@router.post("/skills/reorder", dependencies=[Depends(require_csrf)])
def reorder_skills(body: schemas.ReorderIn):
    with db.connect() as conn:
        for position, sid in enumerate(body.ids):
            conn.execute("UPDATE skills SET position = ? WHERE id = ?", (position, int(sid)))
    return {"ok": True}


# ---------- Projetos ----------

def _techs(conn, project_id: str) -> List[str]:
    rows = conn.execute(
        "SELECT tech FROM project_techs WHERE project_id = ? ORDER BY position, id", (project_id,)
    ).fetchall()
    return [r["tech"] for r in rows]


def _links(conn, project_id: str) -> List[dict]:
    rows = conn.execute(
        "SELECT label, href, track, position FROM project_links WHERE project_id = ? ORDER BY position, id",
        (project_id,),
    ).fetchall()
    return [_row(r) for r in rows]


def _project_out(conn, project_id: str) -> dict:
    row = conn.execute(
        "SELECT id, icon, title, description, published, position FROM projects WHERE id = ?",
        (project_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "projeto nao encontrado")
    out = _row(row)
    out["published"] = bool(out["published"])
    out["techs"] = _techs(conn, project_id)
    out["links"] = _links(conn, project_id)
    return out


@router.get("/projects", response_model=List[schemas.ProjectOut])
def list_projects():
    with db.connect() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM projects ORDER BY position, id").fetchall()]
        out = [_project_out(conn, pid) for pid in ids]
    return out


@router.post("/projects", response_model=schemas.ProjectOut, dependencies=[Depends(require_csrf)])
def create_project(item: schemas.ProjectIn):
    with db.connect() as conn:
        exists = conn.execute("SELECT 1 FROM projects WHERE id = ?", (item.id,)).fetchone()
        if exists:
            raise HTTPException(409, "ja existe projeto com este id")
        pos = conn.execute("SELECT COALESCE(MAX(position), -1) + 1 AS p FROM projects").fetchone()["p"]
        conn.execute(
            "INSERT INTO projects (id, icon, title, description, published, position) VALUES (?, ?, ?, ?, ?, ?)",
            (item.id, item.icon.strip(), item.title.strip(), item.description.strip(),
             int(item.published), pos),
        )
        _replace_children(conn, item)
        out = _project_out(conn, item.id)
    return out


@router.put("/projects/{project_id}", response_model=schemas.ProjectOut, dependencies=[Depends(require_csrf)])
def update_project(project_id: str, item: schemas.ProjectIn):
    with db.connect() as conn:
        cur = conn.execute(
            "UPDATE projects SET icon = ?, title = ?, description = ?, published = ? WHERE id = ?",
            (item.icon.strip(), item.title.strip(), item.description.strip(),
             int(item.published), project_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "projeto nao encontrado")
        conn.execute("DELETE FROM project_techs WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM project_links WHERE project_id = ?", (project_id,))
        _replace_children(conn, item)
        out = _project_out(conn, project_id)
    return out


def _replace_children(conn, item: schemas.ProjectIn):
    for position, tech in enumerate(item.techs):
        if str(tech).strip():
            conn.execute(
                "INSERT INTO project_techs (project_id, tech, position) VALUES (?, ?, ?)",
                (item.id, str(tech).strip(), position),
            )
    for position, link in enumerate(item.links):
        conn.execute(
            "INSERT INTO project_links (project_id, label, href, track, position) VALUES (?, ?, ?, ?, ?)",
            (item.id, link.label.strip(), link.href.strip(), link.track.strip(), position),
        )


@router.delete("/projects/{project_id}", dependencies=[Depends(require_csrf)])
def delete_project(project_id: str):
    with db.connect() as conn:
        cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "projeto nao encontrado")
    return {"ok": True}


@router.post("/projects/reorder", dependencies=[Depends(require_csrf)])
def reorder_projects(body: schemas.ReorderIn):
    with db.connect() as conn:
        for position, pid in enumerate(body.ids):
            conn.execute("UPDATE projects SET position = ? WHERE id = ?", (position, pid))
    return {"ok": True}


# ---------- Certificacoes ----------

def _cert_out(conn, cert_id: str) -> dict:
    row = conn.execute(
        "SELECT id, name, issuer, year, credential_id, url, position FROM certifications WHERE id = ?",
        (cert_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "certificacao nao encontrada")
    out = _row(row)
    imgs = conn.execute(
        "SELECT filename, position FROM cert_images WHERE cert_id = ? ORDER BY position, id", (cert_id,)
    ).fetchall()
    out["images"] = [_row(r) for r in imgs]
    return out


@router.get("/certifications", response_model=List[schemas.CertificationOut])
def list_certifications():
    with db.connect() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM certifications ORDER BY position, id").fetchall()]
        out = [_cert_out(conn, cid) for cid in ids]
    return out


@router.post("/certifications", response_model=schemas.CertificationOut, dependencies=[Depends(require_csrf)])
def create_certification(item: schemas.CertificationIn):
    with db.connect() as conn:
        exists = conn.execute("SELECT 1 FROM certifications WHERE id = ?", (item.id,)).fetchone()
        if exists:
            raise HTTPException(409, "ja existe certificacao com este id")
        pos = conn.execute("SELECT COALESCE(MAX(position), -1) + 1 AS p FROM certifications").fetchone()["p"]
        conn.execute(
            "INSERT INTO certifications (id, name, issuer, year, credential_id, url, position) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (item.id, item.name.strip(), item.issuer.strip(), item.year.strip(),
             item.credential_id.strip(), item.url.strip(), pos),
        )
        out = _cert_out(conn, item.id)
    return out


@router.put("/certifications/{cert_id}", response_model=schemas.CertificationOut, dependencies=[Depends(require_csrf)])
def update_certification(cert_id: str, item: schemas.CertificationIn):
    with db.connect() as conn:
        cur = conn.execute(
            "UPDATE certifications SET name = ?, issuer = ?, year = ?, credential_id = ?, url = ? WHERE id = ?",
            (item.name.strip(), item.issuer.strip(), item.year.strip(),
             item.credential_id.strip(), item.url.strip(), cert_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "certificacao nao encontrada")
        out = _cert_out(conn, cert_id)
    return out


@router.delete("/certifications/{cert_id}", dependencies=[Depends(require_csrf)])
def delete_certification(cert_id: str):
    with db.connect() as conn:
        files = [r["filename"] for r in conn.execute(
            "SELECT filename FROM cert_images WHERE cert_id = ?", (cert_id,)).fetchall()]
        cur = conn.execute("DELETE FROM certifications WHERE id = ?", (cert_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "certificacao nao encontrada")
    for filename in files:
        path = cert_image_path(filename)
        if os.path.exists(path):
            os.remove(path)
    return {"ok": True}


@router.post("/certifications/{cert_id}/image", dependencies=[Depends(require_csrf)])
async def upload_cert_image(cert_id: str, file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "envie um PDF")
    data = await file.read()
    if len(data) > 30 * 1024 * 1024:
        raise HTTPException(400, "PDF grande demais (max 30 MB)")
    with db.connect() as conn:
        if not conn.execute("SELECT 1 FROM certifications WHERE id = ?", (cert_id,)).fetchone():
            raise HTTPException(404, "certificacao nao encontrada")
    try:
        filenames = pdf_to_webp(data, cert_id)
    except Exception as err:  # noqa: BLE001
        raise HTTPException(400, f"falha ao converter PDF: {err}") from err
    with db.connect() as conn:
        old = [r["filename"] for r in conn.execute(
            "SELECT filename FROM cert_images WHERE cert_id = ?", (cert_id,)).fetchall()]
        conn.execute("DELETE FROM cert_images WHERE cert_id = ?", (cert_id,))
        for position, filename in enumerate(filenames):
            conn.execute(
                "INSERT INTO cert_images (cert_id, filename, position) VALUES (?, ?, ?)",
                (cert_id, filename, position),
            )
    for filename in old:
        if filename not in filenames:
            path = cert_image_path(filename)
            if os.path.exists(path):
                os.remove(path)
    return {"images": filenames}


@router.delete("/certifications/{cert_id}/image", dependencies=[Depends(require_csrf)])
def clear_cert_image(cert_id: str):
    with db.connect() as conn:
        if not conn.execute("SELECT 1 FROM certifications WHERE id = ?", (cert_id,)).fetchone():
            raise HTTPException(404, "certificacao nao encontrada")
        files = [r["filename"] for r in conn.execute(
            "SELECT filename FROM cert_images WHERE cert_id = ?", (cert_id,)).fetchall()]
        conn.execute("DELETE FROM cert_images WHERE cert_id = ?", (cert_id,))
    for filename in files:
        path = cert_image_path(filename)
        if os.path.exists(path):
            os.remove(path)
    return {"ok": True}


@router.post("/certifications/reorder", dependencies=[Depends(require_csrf)])
def reorder_certifications(body: schemas.ReorderIn):
    with db.connect() as conn:
        for position, cid in enumerate(body.ids):
            conn.execute("UPDATE certifications SET position = ? WHERE id = ?", (position, cid))
    return {"ok": True}


# ---------- Conteudo do site ----------

@router.get("/site", response_model=schemas.SiteIn)
def get_site():
    return schemas.SiteIn(**db.read_site_json())


@router.put("/site", response_model=schemas.SiteIn, dependencies=[Depends(require_csrf)])
def put_site(site: schemas.SiteIn):
    db.write_site_json(site.model_dump())
    return site


# ---------- Geracao do portfolio.json ----------

def build_portfolio_json() -> dict:
    with db.connect() as conn:
        certs = []
        for r in conn.execute(
            "SELECT id, name, issuer, year, credential_id, url FROM certifications ORDER BY position, id"
        ).fetchall():
            img = conn.execute(
                "SELECT filename FROM cert_images WHERE cert_id = ? ORDER BY position, id LIMIT 1",
                (r["id"],),
            ).fetchone()
            cert = {
                "id": r["id"],
                "image": f"certificados_webp/{img['filename'] if img else r['id']}.webp",
                "name": r["name"],
                "issuer": r["issuer"],
                "year": r["year"],
                "credential_id": r["credential_id"],
            }
            if r["url"]:
                cert["url"] = r["url"]
            certs.append(cert)

        skills = [_row(r) for r in conn.execute(
            "SELECT icon, title, description FROM skills ORDER BY position, id").fetchall()]

        projects = []
        for r in conn.execute(
            "SELECT id, icon, title, description FROM projects WHERE published = 1 ORDER BY position, id"
        ).fetchall():
            project = _row(r)
            project["techs"] = _techs(conn, project["id"])
            project["links"] = [
                {"label": l["label"], "href": l["href"], "track": l["track"]}
                for l in _links(conn, project["id"])
            ]
            projects.append(project)

    out = {"certifications": certs, "skills": skills, "projects": projects}
    site = db.read_site_json()
    if site:
        out["site"] = site
    return out


def build_portfolio_json_text() -> str:
    return json.dumps(build_portfolio_json(), ensure_ascii=False, indent=2) + "\n"
