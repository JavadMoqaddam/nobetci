import asyncio
from contextlib import asynccontextmanager
import logging
import threading
import queue
import time
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer

from app.tasks.marzban import start_marzban_node_tasks
from app.tasks.marzneshin import start_marznode_tasks
from app.tasks.pasarguard import start_pg_node_tasks
from app.tasks.rebecca import start_rebecca_node_tasks
from app.telegram_bot import build_telegram_bot
from app.service.check_service import CheckService
from app import storage
from app.db.db_context import DbContext
from app.db.models import UserLimit
from app.db.marzneshin_db import MarzneshinDB
from app.models.panel import Panel

from . import __version__

from app.config import (DEBUG, DOCS, PANEL_TYPE, SYNC_WITH_PANEL, PANEL_USERNAME, PANEL_PASSWORD, PANEL_ADDRESS,
                        UVICORN_HOST, UVICORN_PORT, UVICORN_SSL_CERTFILE, UVICORN_SSL_KEYFILE, UVICORN_UDS)
from app.routes import api_router

from fastapi.middleware.cors import CORSMiddleware
from uvicorn import Config, Server

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log_queue = queue.Queue(maxsize=1000)
    loop = asyncio.get_running_loop()

    main_thread_db_instance = None
    if SYNC_WITH_PANEL:
        try:
            _panel = Panel(username=PANEL_USERNAME, password=PANEL_PASSWORD, domain=PANEL_ADDRESS)
            main_thread_db_instance = MarzneshinDB(_panel)
        except Exception as e:
            logger.error(f"Failed to initialize MarzneshinDB: {e}")

    def worker_thread():
        if SYNC_WITH_PANEL:
            db_instance = main_thread_db_instance
        else:
            db_instance = DbContext(UserLimit)
        
        check_service = None
        if db_instance:
            check_service = CheckService(storage, db_instance, loop)

        while True:
            if db_instance is None:
                try:
                    if SYNC_WITH_PANEL:
                        _panel = Panel(username=PANEL_USERNAME, password=PANEL_PASSWORD, domain=PANEL_ADDRESS)
                        db_instance = MarzneshinDB(_panel)
                    else:
                        db_instance = DbContext(UserLimit)
                    
                    check_service = CheckService(storage, db_instance, loop)
                    logger.info("DB Instance initialized successfully in worker.")
                except Exception as e:
                    logger.error(f"Failed to initialize DB in worker, retrying in 5s: {e}")
                    time.sleep(5)
                    continue

            try:
                log = log_queue.get()
                check_service.check(log)
            except Exception as e:
                logger.error(f"Error in log processor thread: {e}")
                
                if not SYNC_WITH_PANEL:
                    if db_instance:
                        try:
                            db_instance.close()
                        except Exception as close_err:
                            logger.error(f"Error closing DB session: {close_err}")
                    db_instance = None
                
                time.sleep(1)
            finally:
                log_queue.task_done()

    threading.Thread(target=worker_thread, daemon=True, name="LogProcessor").start()

    asyncio.create_task(build_telegram_bot())

    if PANEL_TYPE == "marzneshin":
        asyncio.create_task(start_marznode_tasks(log_queue))
    elif PANEL_TYPE == "rebecca":
        asyncio.create_task(start_rebecca_node_tasks())
    elif PANEL_TYPE == "marzban":
        asyncio.create_task(start_marzban_node_tasks())
    elif PANEL_TYPE == "pasarguard":
        asyncio.create_task(start_pg_node_tasks())

    yield

# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

app = FastAPI(
    title="NobetciAPI",
    description="Xray ip limit",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs" if DOCS else None,
    redoc_url="/redoc" if DOCS else None,
)

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
def validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    details = {}
    for error in exc.errors():
        details[error["loc"][-1]] = error.get("msg")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder({"detail": details}),
    )


async def main():
    cfg = Config(
        app=app,
        host=UVICORN_HOST,
        port=UVICORN_PORT,
        uds=(None if DEBUG else UVICORN_UDS),
        ssl_certfile=UVICORN_SSL_CERTFILE,
        ssl_keyfile=UVICORN_SSL_KEYFILE,
        workers=1,
        reload=DEBUG,
        log_level=logging.DEBUG if DEBUG else logging.INFO,
    )
    server = Server(config=cfg)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
