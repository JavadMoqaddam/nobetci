import logging
from ssl import SSLError
from app.models.marznode import MarzNode
from app.models.panel import Panel
import httpx
import asyncio
import random

from app.notification.telegram import send_notification

logger = logging.getLogger(__name__)

async def get_token(panel_data: Panel) -> Panel | ValueError:
    if panel_data.token:
        return panel_data

    payload = {
        "username": f"{panel_data.username}",
        "password": f"{panel_data.password}",
    }
    for attempt in range(20):
        for scheme in ["https","http"]:
            url = f"{scheme}://{panel_data.domain}/api/admins/token"
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.post(url, data=payload, timeout=5)
                    response.raise_for_status()
                json_obj = response.json()
                panel_data.token = json_obj["access_token"]
                return panel_data
            except httpx.HTTPStatusError:
                message = f"[{response.status_code}] {response.text}"
                await send_notification(message)
                logger.error(message)
                print(message)
                continue
            except SSLError:
                continue
            except Exception as error:
                message = f"An unexpected error occurred: {error}"
                await send_notification(message)
                logger.error(message)
                print(message)
                continue
        await asyncio.sleep(random.randint(2, 5) * attempt)
    message = (
        "Failed to get token after 20 attempts. Make sure the panel is running "
        + "and the username and password are correct."
    )
    await send_notification(message)
    logger.error(message)
    raise ValueError(message)

async def get_marznodes(panel_data: Panel) -> list[MarzNode] | ValueError:
    for attempt in range(20):
        get_panel_token = await get_token(panel_data)
        if isinstance(get_panel_token, ValueError):
            raise get_panel_token
        token = get_panel_token.token
        headers = {
            "Authorization": f"Bearer {token}",
        }
        all_nodes = []
        for scheme in ["https","http"]:
            url = f"{scheme}://{panel_data.domain}/api/nodes?status=healthy"
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.get(url, headers=headers, timeout=10)

                    if response.status_code == 401:
                        panel_data.token = None
                        continue
                    
                    response.raise_for_status()
                user_inform = response.json()
                items = user_inform.get("items", []) if isinstance(user_inform, dict) else user_inform
                for node in items:
                    all_nodes.append(
                        MarzNode(
                            id=node["id"],
                            name=node["name"],
                            address=node["address"],
                            port=node.get('port', 0),
                            status=node["status"],
                            message=node.get("message", ""),
                        )
                    )
                return all_nodes
            except SSLError:
                continue
            except httpx.HTTPStatusError as e:
                logger.error(f"Error fetching nodes: {e}")
                continue
            except Exception as error:
                logger.error(f"An unexpected error occurred: {error}")
                continue
        await asyncio.sleep(random.randint(2, 5) * attempt)
    message = (
        "Failed to get nodes after 20 attempts. make sure the panel is running "
        + "and the username and password are correct."
    )
    await send_notification(message)
    logger.error(message)
    raise ValueError(message)

async def get_user(username: str, panel_data: Panel) -> dict | None:
    for attempt in range(5):
        get_panel_token = await get_token(panel_data)
        if isinstance(get_panel_token, ValueError):
            raise get_panel_token
        token = get_panel_token.token
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        for scheme in ["https", "http"]:
            url = f"{scheme}://{panel_data.domain}/api/users/{username}"
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.get(url, headers=headers, timeout=10)
                    
                    if response.status_code == 401:
                        panel_data.token = None
                        continue

                    if response.status_code == 404:
                        return None
                        
                    response.raise_for_status()
                    return response.json()
            except Exception as error:
                logger.error(f"Error fetching user {username}: {error}")
                continue
        await asyncio.sleep(1)
    return None
