from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

BASE_DIR       = Path(__file__).parent.parent.parent
TEMPLATES_DIR  = BASE_DIR / "templates"

if not TEMPLATES_DIR.exists():
    logger.error(
        f"Папка шаблонов не найдена: {TEMPLATES_DIR}. "
        "Создайте папку templates/ в корне проекта."
    )

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="", tags=["frontend"])


@router.get(
    "/",
    include_in_schema=False,   # не показывать в Swagger — это не API endpoint
)
async def index(request: Request):
    """
    Главная страница. Отдаёт templates/index.html.
    request передаётся в шаблон — Jinja2 требует его для url_for() и прочего.
    """
    return templates.TemplateResponse("index.html", {"request": request})


@router.get(
    "/{full_path:path}",
    include_in_schema=False,
)
async def spa_fallback(request: Request, full_path: str):
    """
    SPA Fallback — для Single Page Application (React/Vue/plain JS).

    Когда пользователь открывает /room/5 напрямую (например, перезагрузка страницы),
    сервер должен вернуть index.html, а JS-роутер на клиенте сам разберётся с URL.

    Исключения:
    - Запросы к /api/* обрабатываются API роутерами (они подключены раньше в main.py).
    - Запросы к /static/* и /ws/* FastAPI обработает раньше этого роута.

    Поэтому сюда доходят только "красивые" URL вида /room/5, /profile и т.д.
    """
    if full_path.startswith("api/"):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Not found"}, status_code=404)
    return templates.TemplateResponse("index.html", {"request": request})