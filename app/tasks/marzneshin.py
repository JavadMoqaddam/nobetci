import asyncio
from app.config import SYNC_WITH_PANEL, PANEL_ADDRESS, PANEL_CUSTOM_NODES, PANEL_PASSWORD, PANEL_USERNAME
from app.models.panel import Panel
from app.service.check_service import CheckService
from app.service.marznode_service import TASKS, MarzNodeService
from app.tasks.nodes import nodes_startup
from app.utils.panel.marzneshin_panel import get_marznodes, get_token
from app import user_limit_db, storage, panel_db
from app.db import node_db


async def start_marznode_tasks():
    await nodes_startup(node_db.get_all(True))

    if panel_db:
        paneltype = panel_db.panel
    else:
        paneltype = Panel(
            username=PANEL_USERNAME,
            password=PANEL_PASSWORD,
            domain=PANEL_ADDRESS,
        )

    if SYNC_WITH_PANEL:
        try:
            paneltype = await get_token(paneltype)
        except Exception:
            pass

    node_service = MarzNodeService(CheckService(
        storage, panel_db if (SYNC_WITH_PANEL and panel_db) else user_limit_db))

    marznodes = await get_marznodes(paneltype)

    if PANEL_CUSTOM_NODES:
        marznodes = [m for m in marznodes if m.name in PANEL_CUSTOM_NODES]

    async with asyncio.TaskGroup() as tg:
        tg.create_task(
            node_service.handle_cancel_all(TASKS, paneltype),
            name="cancel_all",
        )
        
        for marznode in marznodes:
            await node_service.create_node_task(paneltype, tg, marznode)
