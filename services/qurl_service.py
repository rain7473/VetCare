"""Publicación temporal de carnés PDF mediante qurl.sh."""
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests


def valid_pdf_url(url: str) -> bool:
    parsed = urlsplit(url)
    parts = parsed.path.strip('/').split('/')
    return (parsed.scheme == 'https' and parsed.netloc == 'qurl.sh'
            and len(parts) == 2 and parts[0].isalnum()
            and parts[1].lower().endswith('.pdf')
            and parsed.query in ('', 'raw=true') and not parsed.fragment)


def upload_pdf(path: str | Path, *, timeout: int = 45) -> str:
    source = Path(path)
    if not source.is_file() or source.stat().st_size == 0 or source.suffix.lower() != '.pdf':
        raise ValueError('No se encontró un PDF válido para publicar.')
    with source.open('rb') as stream:
        response = requests.put('https://qurl.sh/carnet-vetcare.pdf', data=stream,
            headers={'X-Format': 'json', 'X-TTL': '7d', 'X-Downloads': '100',
                     'Content-Type': 'application/pdf', 'User-Agent': 'VetCare/1.0'}, timeout=timeout)
    response.raise_for_status()
    try:
        body = response.json()
        url = body.get('url', '')
    except (ValueError, AttributeError):
        raise ValueError('El servicio devolvió una respuesta inválida.') from None
    if not isinstance(url, str) or not valid_pdf_url(url):
        raise ValueError('El servicio no devolvió un enlace de PDF válido.')
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, 'raw=true', ''))
