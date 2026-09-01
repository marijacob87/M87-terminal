"""Ponte opcional entre o comando TODO e a PWA publicada do Planner."""

from __future__ import annotations

import os
from urllib.parse import urlparse


def planner_web_url():
    """Retorna uma URL web válida configurada para o Planner, ou string vazia."""
    url = os.environ.get("M87_PLANNER_WEB_URL", "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return url


def open_planner_web():
    """Abre a PWA no navegador somente quando uma URL privada está configurada."""
    url = planner_web_url()
    if not url:
        return False
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    return QDesktopServices.openUrl(QUrl(url))
