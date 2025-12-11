import logging
from app.config import CACHE_TTL, MARZNESHIN_SERVICES
from app.db.db_base import DBBase
from app.models.panel import Panel
from app.models.user import UserLimit
from app.utils.panel.marzneshin_panel import get_user
from cachetools import TTLCache

logger = logging.getLogger(__name__)

class MarzneshinDB(DBBase):
    def __init__(self, panel: Panel):
        self.panel = panel
        self.cache = TTLCache(maxsize=100000, ttl=CACHE_TTL)
        self.services_limit = self._parse_services(MARZNESHIN_SERVICES)

    def _parse_services(self, services_str: str) -> dict:
        limits = {}
        if not services_str:
            return limits
        try:
            for item in services_str.split(','):
                if ':' in item:
                    sid, limit = item.split(':')
                    limits[int(sid.strip())] = int(limit.strip())
        except Exception as e:
            logger.error(f"Failed to parse MARZNESHIN_SERVICES: {e}")
        return limits

    def save(self) -> None:
        pass

    def add(self, data):
        pass

    def delete(self, condition: callable):
        pass

    def update(self, condition: callable, data):
        pass

    async def get(self, condition: callable):
        username = getattr(condition.right, "value", condition.right)

        if username in self.cache:
            return UserLimit(name=self.cache[username].name, limit=self.cache[username].limit)

        self.cache[username] = UserLimit(name=username, limit=0)

        user_data = await get_user(username, self.panel)
        
        if not user_data:
            user_limit = UserLimit(name=username, limit=0)
            self.cache[username] = user_limit
            return user_limit

        service_ids = user_data.get("service_ids", [])
        if not isinstance(service_ids, list):
            service_ids = []

        limit = 0
        found_service = None

        for sid in service_ids:
            if sid in self.services_limit:
                limit = self.services_limit[sid]
                found_service = sid
                break

        user_limit = UserLimit(name=username, limit=limit)
        self.cache[username] = user_limit
        
        if limit > 0:
            logger.info(f"Synced user {username} (Services: {service_ids}) -> Matched Service: {found_service} -> Limit: {limit}")
        return UserLimit(name=user_limit.name, limit=user_limit.limit)

    def get_all(self, condition: callable):
        pass
