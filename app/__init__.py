import logging

import uvicorn
from app.config import DEBUG, SYNC_WITH_PANEL, PANEL_USERNAME, PANEL_PASSWORD, PANEL_ADDRESS
from app.db.db_context import DbContext
from app.db.marzneshin_db import MarzneshinDB
from app.db.models import UserLimit
from app.models.panel import Panel
from app.storage.memory import MemoryStorage


__version__ = "0.0.9"

storage = MemoryStorage()
user_limit_db = DbContext(UserLimit)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if DEBUG else logging.INFO)
handler = logging.StreamHandler()
formatter = uvicorn.logging.ColourizedFormatter(
    "{levelprefix:<8} @{name}: {message}", style="{", use_colors=True
)
handler.setFormatter(formatter)
logger.addHandler(handler)


panel_db = None
if SYNC_WITH_PANEL:
    try:
        _panel = Panel(username=PANEL_USERNAME, password=PANEL_PASSWORD, domain=PANEL_ADDRESS)
        panel_db = MarzneshinDB(_panel)
    except Exception as e:
        logger.error(f"Failed to initialize MarzneshinDB: {e}")
