# Deploy do portfolio-admin (homesrv)

App `portfolio-admin` no `homesrv` (Ubuntu, LAN-first). Backend FastAPI na porta
**8003**, servindo também o frontend estático (repo `portfolio-admin`) em `/`.

## Pré-requisitos no servidor

- Python 3 + venv (`python3-venv`)
- systemd (unit genérica `simple-vibe@.service` já instalada, ou instale a partir
  de `templates/server-setup/simple-vibe@.service` do repo simple-vibe-agent)

## 1. Estrutura

```text
/home/igordev/apps/portfolio-admin/
├── main.py, db.py, security.py, ...   (este repo, portfolio-admin-api)
├── static/                             (repo portfolio-admin, arquivos do frontend)
├── venv/
├── .env                                (modo 600)
└── data.db
```

## 2. Subir o backend

```bash
ssh igordev@192.168.1.2
sudo mkdir -p /home/igordev/apps/portfolio-admin && sudo chown igordev:igordev /home/igordev/apps/portfolio-admin
cd /home/igordev/apps/portfolio-admin

git clone https://github.com/Igorls34/portfolio-admin-api .
python3 -m venv venv
./venv/bin/pip install -r requirements.txt -r requirements-upload.txt

# .env (nunca versionar)
cat > .env <<'EOF'
HOST=0.0.0.0
PORT=8003
DB_PATH=./data.db
ADMIN_USERNAME=admin
ADMIN_PASSWORD=SUA_SENHA_FORTE
GITHUB_TOKEN=ghp_...
GITHUB_OWNER=Igorls34
GITHUB_REPO=portfolio
GITHUB_BRANCH=main
CORS_ORIGINS=
EOF
chmod 600 .env
```

## 3. Subir o frontend (repo separado)

```bash
cd /home/igordev/apps/portfolio-admin
git clone https://github.com/Igorls34/portfolio-admin /tmp/portfolio-admin-front
mkdir -p static
cp -r /tmp/portfolio-admin-front/* static/
# garante que o index.html do frontend esta em static/index.html
rm -rf /tmp/portfolio-admin-front
```

## 4. Unit systemd

```bash
sudo cp /home/igordev/repos/simple-vibe/templates/server-setup/simple-vibe@.service \
  /etc/systemd/system/simple-vibe@.service
sudo systemctl daemon-reload
sudo systemctl enable --now simple-vibe@portfolio-admin.service
sudo systemctl status simple-vibe@portfolio-admin.service
```

Confira:

```bash
curl -s http://127.0.0.1:8003/health
```

## 5. Acesso

- LAN: `http://192.168.1.2:8003/`
- Remoto: via Tailscale (MagicDNS). Não há túnel ngrok (limite de 1 domínio
  free já usado) — acesso é privado de propósito.

Se acessar via Tailscale com HTTPS, defina `COOKIE_SECURE=true` no `.env`.

## 6. Atualizar (deploy)

```bash
cd /home/igordev/apps/portfolio-admin
git pull
./venv/bin/pip install -r requirements.txt -r requirements-upload.txt
# frontend:
git clone https://github.com/Igorls34/portfolio-admin /tmp/pf && rsync -a --delete /tmp/pf/ static/ && rm -rf /tmp/pf
sudo systemctl restart simple-vibe@portfolio-admin.service
```

## 7. Backup

```bash
sqlite3 /home/igordev/apps/portfolio-admin/data.db ".backup '/home/igordev/backups/portfolio-admin-$(date +%F).db'"
```

## Segredos

- `GITHUB_TOKEN`: PAT fine-grained, escopo **apenas** do repo `portfolio`, permissão
  `Contents: Read and write`. Nunca versionar.
- `SECRET_KEY`: deixe vazio na primeira subida para gerar e persistir `secret.key`
  (ou defina um valor fixo).
