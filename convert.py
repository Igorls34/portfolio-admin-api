"""Conversao de PDF em WebP (PyMuPDF + Pillow), espelhando o conversor.py do
portfolio: 150 DPI, qualidade 85, uma pagina por arquivo <base>_pagina_NNN.webp.

Os imports de fitz/Pillow sao tardios: o app so precisa deles na hora do
upload, entao CRUD/site/publish funcionam sem essas dependencias instaladas."""
import os

from db import PROJECTS_UPLOADS_DIR, UPLOADS_DIR

DPI = 150
QUALITY = 85


def pdf_to_webp(pdf_bytes: bytes, base_name: str) -> list:
    """Converte o PDF para um WebP por pagina em UPLOADS_DIR.

    Retorna a lista de nomes de arquivo gerados (ex.: ['0h2ll5ge_pagina_001.webp']).
    """
    try:
        import pymupdf as fitz  # PyMuPDF 2.x
    except ImportError:
        import fitz  # PyMuPDF 1.x
    from PIL import Image

    os.makedirs(UPLOADS_DIR, exist_ok=True)
    documento = fitz.open(stream=pdf_bytes, filetype="pdf")
    escala = DPI / 72
    matriz = fitz.Matrix(escala, escala)
    gerados = []
    try:
        for numero, pagina in enumerate(documento, start=1):
            imagem = pagina.get_pixmap(matrix=matriz, alpha=False)
            arquivo = f"{base_name}_pagina_{numero:03d}.webp"
            destino = os.path.join(UPLOADS_DIR, arquivo)
            img_pil = Image.frombytes("RGB", [imagem.width, imagem.height], imagem.samples)
            img_pil.save(destino, format="WEBP", quality=QUALITY)
            gerados.append(arquivo)
    finally:
        documento.close()
    return gerados


def cert_image_path(filename: str) -> str:
    return os.path.join(UPLOADS_DIR, filename)


def image_to_webp(data: bytes, base_name: str) -> str:
    """Converte uma imagem (png/jpg/webp) para WebP em PROJECTS_UPLOADS_DIR.

    Retorna o nome do arquivo gerado (ex.: 'meu_projeto.webp')."""
    import io

    from PIL import Image

    os.makedirs(PROJECTS_UPLOADS_DIR, exist_ok=True)
    img = Image.open(io.BytesIO(data))
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        fundo = Image.new("RGB", img.size, (255, 255, 255))
        fundo.paste(img, mask=img.split()[-1])
        img = fundo
    else:
        img = img.convert("RGB")
    filename = f"{base_name}.webp"
    destino = os.path.join(PROJECTS_UPLOADS_DIR, filename)
    img.save(destino, format="WEBP", quality=QUALITY)
    return filename


def project_image_path(filename: str) -> str:
    return os.path.join(PROJECTS_UPLOADS_DIR, filename)
