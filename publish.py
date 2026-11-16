"""Publicacao: monta um unico commit no repo do portfolio (Git Data API) com o
portfolio.json e os WebP de certificados, e dispara o build (push -> Actions ->
Netlify; opcionalmente um build hook da Netlify)."""
import base64
import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException

import db
from content import build_portfolio_json_text
from convert import cert_image_path, project_image_path
from security import require_auth, require_csrf

router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])

API = "https://api.github.com"


def _repo_ref() -> tuple:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    owner = os.getenv("GITHUB_OWNER", "").strip()
    repo = os.getenv("GITHUB_REPO", "").strip()
    if not (token and owner and repo):
        raise HTTPException(503, "publicacao nao configurada: defina GITHUB_TOKEN/OWNER/REPO")
    return token, owner, repo


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "portfolio-admin",
    }


async def _request(client, method, url, headers, **kw):
    resp = await client.request(method, url, headers=headers, **kw)
    if resp.status_code >= 400:
        raise HTTPException(502, f"GitHub {method} {url} -> {resp.status_code}: {resp.text[:300]}")
    if resp.status_code == 204:
        return None
    return resp.json()


async def _commit(token, owner, repo, branch, json_text, filesets) -> str:
    base = f"{API}/repos/{owner}/{repo}"
    async with httpx.AsyncClient(timeout=60) as client:
        h = _headers(token)

        ref = await _request(client, "GET", f"{base}/git/ref/heads/{branch}", h)
        base_sha = ref["object"]["sha"]
        commit = await _request(client, "GET", f"{base}/git/commits/{base_sha}", h)
        base_tree = commit["tree"]["sha"]

        tree_entries = []

        # portfolio.json
        json_blob = await _request(client, "POST", f"{base}/git/blobs", h,
                                   json={"content": base64.b64encode(json_text.encode("utf-8")).decode(),
                                         "encoding": "base64"})
        tree_entries.append({"path": os.getenv("PORTFOLIO_JSON_PATH", "data/portfolio.json"),
                             "mode": "100644", "type": "blob", "sha": json_blob["sha"]})

        # Cada conjunto (ex.: certificados_webp, assets/img/projects): adiciona
        # os arquivos desejados e remove os que sairam do banco.
        for fs in filesets:
            diretorio = fs["dir"]
            arquivos = fs["files"]

            current = {}
            try:
                listing = await _request(client, "GET", f"{base}/contents/{diretorio}", h)
                if isinstance(listing, list):
                    for item in listing:
                        if item.get("type") == "file":
                            current[item["path"]] = item["sha"]
            except HTTPException as err:
                if err.status_code != 502 or "404" not in str(err.detail):
                    raise
                current = {}

            desired = set(arquivos.keys())
            for path, content in arquivos.items():
                blob = await _request(client, "POST", f"{base}/git/blobs", h,
                                      json={"content": base64.b64encode(content).decode(),
                                            "encoding": "base64"})
                tree_entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
            for path in current:
                if path not in desired:
                    tree_entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})

        tree = await _request(client, "POST", f"{base}/git/trees", h,
                              json={"base_tree": base_tree, "tree": tree_entries})
        new_commit = await _request(client, "POST", f"{base}/git/commits", h,
                                    json={"message": "chore: atualiza portfolio via painel admin",
                                          "tree": tree["sha"], "parents": [base_sha]})
        await _request(client, "PATCH", f"{base}/git/refs/heads/{branch}", h,
                       json={"sha": new_commit["sha"]})
        return new_commit["sha"]


def _collect_cert_files(certs_dir: str) -> dict:
    files = {}
    with db.connect() as conn:
        rows = conn.execute("SELECT filename FROM cert_images ORDER BY position, id").fetchall()
    for r in rows:
        path = cert_image_path(r["filename"])
        if os.path.exists(path):
            with open(path, "rb") as fh:
                files[f"{certs_dir}/{r['filename']}"] = fh.read()
    return files


def _collect_project_files(projects_dir: str) -> dict:
    files = {}
    with db.connect() as conn:
        rows = conn.execute("SELECT image FROM projects WHERE image != ''").fetchall()
    for r in rows:
        path = project_image_path(r["image"])
        if os.path.exists(path):
            with open(path, "rb") as fh:
                files[f"{projects_dir}/{r['image']}"] = fh.read()
    return files


async def _run_publish() -> dict:
    token, owner, repo = _repo_ref()
    branch = os.getenv("GITHUB_BRANCH", "main").strip() or "main"
    certs_dir = os.getenv("PORTFOLIO_CERTS_DIR", "certificados_webp").strip().strip("/")
    projects_dir = os.getenv("PORTFOLIO_PROJECTS_DIR", "assets/img/projects").strip().strip("/")
    filesets = [
        {"dir": certs_dir, "files": _collect_cert_files(certs_dir)},
        {"dir": projects_dir, "files": _collect_project_files(projects_dir)},
    ]
    sha = await _commit(token, owner, repo, branch, build_portfolio_json_text(), filesets)

    deploy_url = ""
    hook = os.getenv("NETLIFY_BUILD_HOOK", "").strip()
    if hook:
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                await client.post(hook)
                deploy_url = "netlify-build-hook-disparado"
            except httpx.HTTPError:
                pass
    return {"status": "ok", "commit_sha": sha, "deploy_url": deploy_url}


def _log(status, sha="", error="") -> None:
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO publish_log (status, commit_sha, error) VALUES (?, ?, ?)",
            (status, sha, error[:2000]),
        )


@router.post("/publish", dependencies=[Depends(require_csrf)])
async def publish():
    try:
        result = await _run_publish()
        _log("ok", result["commit_sha"], "")
        return result
    except HTTPException as err:
        _log("erro", "", str(err.detail))
        raise
    except Exception as err:  # noqa: BLE001
        _log("erro", "", str(err))
        raise HTTPException(500, f"falha ao publicar: {err}") from err


@router.get("/publish/status")
def publish_status():
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, at, status, commit_sha, deploy_url, error FROM publish_log ORDER BY id DESC LIMIT 10"
        ).fetchall()
    history = []
    for r in rows:
        item = dict(r)
        item["at"] = _iso(r["at"])
        history.append(item)
    return {"last": history[0] if history else None, "history": history}


def _iso(value) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        return str(value)
