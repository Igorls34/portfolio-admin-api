# portfolio-admin-api

Backend do painel admin do portfolio do IgorDev. CRUD de skills, projetos,
certificações e conteúdo do site (hero/sobre/contato/redes), upload de
certificados (PDF→WebP) e **publicação** que grava o `portfolio.json` de volta
no repo do portfolio e dispara o build (GitHub Actions → Netlify).

Faz parte do ecossistema **simple-vibe** (apps do `homesrv`, uma porta por app).

## Stack

- FastAPI + Pydantic v2 + SQLite (WAL, stdlib `sqlite3`)
- Autenticação de usuário único: senha (scrypt do stdlib), sessão assinada
  HttpOnly (itsdangerous) e CSRF por double-submit cookie
- `PyMuPDF` + `Pillow` para PDF → WebP (mesmos parâmetros do `conversor.py` do
  portfolio: 150 DPI, qualidade 85)
- `httpx` para a publicação via GitHub API

## Rodar local

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate | Linux: source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-upload.txt   # PDF -> WebP (upload de certificados)
pip install -r requirements-dev.txt      # testes
cp .env.example .env                  # ajuste ADMIN_PASSWORD e PORT=8003
uvicorn main:app --reload --host 127.0.0.1 --port 8003
```

Testar:

```bash
pytest -q
```

- `/health`, `/info`, `/metrics` (públicos)
- `/docs` (Swagger; opcional)

## Variáveis de ambiente

Ver `.env.example`. As essenciais:

| Var | Papel |
|---|---|
| `PORT` | 8003 (próxima livre no ecossistema) |
| `DB_PATH` | caminho do SQLite (padrão `./data.db`) |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | usuário único; sem senha, gera uma aleatória no primeiro boot (log) |
| `SECRET_KEY` | assinatura da sessão/CSRF; sem ela, gera e persiste `secret.key` |
| `GITHUB_TOKEN` / `GITHUB_OWNER` / `GITHUB_REPO` | publicação (PAT com `contents:write` só no repo do portfolio) |
| `NETLIFY_BUILD_HOOK` | (opcional) gatilho extra de build |

## Autenticação

`POST /api/auth/login` valida usuário/senha, define um cookie de sessão
`HttpOnly + SameSite=Strict` e um cookie CSRF (legível pelo JS). Toda mutação
exige o header `X-CSRF-Token` igual ao cookie CSRF. Login com rate limit por IP.

## Publicação (publish)

`POST /api/publish`:

1. monta o `portfolio.json` a partir do banco (formato idêntico ao atual) +
   chave `site`;
2. monta **um único commit** no repo do portfolio via Git Data API
   (`data/portfolio.json` + WebP em `certificados_webp/`, reconciliando
   inclusões e exclusões);
3. o push em `main` dispara o GitHub Actions → Netlify já existente. Se
   `NETLIFY_BUILD_HOOK` estiver definido, também o chama.

`GET /api/publish/status` mostra o histórico.

## Deploy (homesrv)

Ver `deploy/DEPLOY.md`. Resumo: código em `/home/igordev/apps/portfolio-admin`,
venv + `simple-vibe@portfolio-admin.service` (porta 8003), frontend copiado
para `static/`.
