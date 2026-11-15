"""Migracao inicial: importa um portfolio.json existente (e os WebP de
certificados) para o banco do painel. Roda uma vez, antes do primeiro uso.

Uso:
    python seed.py <caminho/do/portfolio.json> [caminho/do/certificados_webp]

O diretorio de certificados e, por padrao, `certificados_webp/` ao lado do JSON.

IMPORTANTE: sem isto, o banco comeca vazio e a primeira publicacao apagaria o
conteudo atual do portfolio (o publish reconcilia inclusoes E exclusoes).
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

import db


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def main() -> None:
    if len(sys.argv) < 2:
        print("uso: python seed.py <portfolio.json> [certificados_webp]")
        sys.exit(1)

    json_path = sys.argv[1]
    certs_dir = sys.argv[2] if len(sys.argv) > 2 else \
        os.path.join(os.path.dirname(os.path.abspath(json_path)), "certificados_webp")

    data = json.load(open(json_path, encoding="utf-8"))

    # Indice de metadados por id e por stem da imagem (mesma logica do gerador).
    metadata = {}
    for c in data.get("certifications", []):
        cid = str(c.get("id", "")).lower()
        if cid:
            metadata[cid] = c
        stem = os.path.splitext(os.path.basename(c.get("image", "")))[0].lower()
        if stem:
            metadata.setdefault(stem, c)

    db.init_db()

    with db.connect() as conn:
        # Idempotente: limpa o conteudo (nao mexe em user/publish_log).
        conn.execute("DELETE FROM cert_images")
        conn.execute("DELETE FROM certifications")
        conn.execute("DELETE FROM project_links")
        conn.execute("DELETE FROM project_techs")
        conn.execute("DELETE FROM projects")
        conn.execute("DELETE FROM skills")

        for pos, s in enumerate(data.get("skills", [])):
            conn.execute(
                "INSERT INTO skills (icon, title, description, position) VALUES (?, ?, ?, ?)",
                (s.get("icon", ""), s.get("title", ""), s.get("description", ""), pos))

        for pos, p in enumerate(data.get("projects", [])):
            conn.execute(
                "INSERT INTO projects (id, icon, title, description, published, position) "
                "VALUES (?, ?, ?, ?, 1, ?)",
                (p["id"], p.get("icon", ""), p.get("title", ""), p.get("description", ""), pos))
            for tpos, t in enumerate(p.get("techs", [])):
                conn.execute("INSERT INTO project_techs (project_id, tech, position) VALUES (?, ?, ?)",
                             (p["id"], t, tpos))
            for lpos, l in enumerate(p.get("links", [])):
                conn.execute(
                    "INSERT INTO project_links (project_id, label, href, track, position) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (p["id"], l.get("label", ""), l.get("href", ""), l.get("track", ""), lpos))

        # Certificacoes: um registro por certificado (stem base), com as paginas
        # como cert_images — espelhando descobrirCertificacoes do gerador.
        grupos = {}
        for webp in sorted(Path(certs_dir).glob("*.webp")):
            stem = webp.stem
            base = re.sub(r"^(.*)_pagina_\d+$", r"\1", stem, flags=re.I) or stem
            grupos.setdefault(base, []).append(webp)

        cert_pos = 0
        for base, files in grupos.items():
            cid = slugify(base)
            meta = metadata.get(base.lower()) or metadata.get(cid)
            name = meta.get("name") if meta else f"Certificado {base}"
            conn.execute(
                "INSERT INTO certifications (id, name, issuer, year, credential_id, url, position) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (cid, name,
                 (meta or {}).get("issuer", ""), str((meta or {}).get("year", "")),
                 (meta or {}).get("credential_id", ""), (meta or {}).get("url", ""), cert_pos))
            for ipos, webp in enumerate(files):
                destino = os.path.join(db.UPLOADS_DIR, webp.name)
                os.makedirs(db.UPLOADS_DIR, exist_ok=True)
                shutil.copyfile(webp, destino)
                conn.execute("INSERT INTO cert_images (cert_id, filename, position) VALUES (?, ?, ?)",
                             (cid, webp.name, ipos))
            cert_pos += 1

    # Fora do bloco anterior: write_site_json abre a propria conexao e, dentro
    # de um "with connect()" aberto, o segundo writer travaria (database locked).
    db.write_site_json(data.get("site") or {})

    print("[seed] concluido:")
    print(f"  skills: {len(data.get('skills', []))}")
    print(f"  projects: {len(data.get('projects', []))}")
    print(f"  certifications: {len(grupos)}")


if __name__ == "__main__":
    main()
