import asyncio
import inspect
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from app.config import ACCEPTED, BAN_LAST_USER, DEFAULT_LIMIT, IUL, STL
from app.db.models import ExceptedIP, UserLimit
from app.models.user import User
from app.nobetnode import nodes
from app.db import excepted_ips
from app.notification.telegram import send_notification_with_reply_markup
from app.storage.base import BaseStorage
from app.db.db_base import DBBase

logger = logging.getLogger(__name__)


class CheckService:

    def __init__(self, storage: BaseStorage, specify_limit_db: DBBase, main_loop):
        self._storage = storage
        self._specify_limit_db = specify_limit_db
        self.main_loop = main_loop
        self._in_process_ips = []
        self.repeated_out_of_limits = []

    def check(self, user: User):
        raw_result = self._specify_limit_db.get(UserLimit.name == user.name)

        if inspect.isawaitable(raw_result):
            future = asyncio.run_coroutine_threadsafe(raw_result, self.main_loop)
            try:
                specify_user = future.result(timeout=10)
            except Exception as e:
                logger.error(f"Async DB fetch error: {e}")
                return
        else:
            specify_user = raw_result

        user_limit = specify_user.limit if specify_user is not None else DEFAULT_LIMIT

        if user_limit == 0 or excepted_ips.get(ExceptedIP.ip == user.ip):
            return

        self._storage.add_user(user)

        users = self._storage.get_users(user.name)

        if len(users) > user_limit and user.ip not in self._in_process_ips:
            userByEmail = self._storage.get_user(user.name)
            userLast = self._storage.get_last_user(user.name)

            if userByEmail is None:
                return

            self.repeated_out_of_limits.append(user)

            rl_len = len(list(filter(lambda x: x.name == userByEmail.name and x.ip ==
                                     userByEmail.ip, self.repeated_out_of_limits)))
            rl_last_len = len(list(filter(
                lambda x: x.name == userLast.name and x.ip == userLast.ip, self.repeated_out_of_limits)))

            logger.debug(f"rl length: {rl_len}")
            logger.debug(f"rl last length: {rl_last_len}")

            if rl_len < STL or rl_last_len < STL:
                if abs(rl_len-rl_last_len) > IUL:
                    self.repeated_out_of_limits = [
                        r for r in self.repeated_out_of_limits if r.name != userByEmail.name and r.ip != userByEmail.ip]
                    self.repeated_out_of_limits = [
                        r for r in self.repeated_out_of_limits if r.name != user.name and r.ip != user.ip]
                    self._storage.delete_user(userByEmail.name, userByEmail.ip)
                return
            self.repeated_out_of_limits = [
                r for r in self.repeated_out_of_limits if r.name != userByEmail.name and r.ip != userByEmail.ip]
            self.repeated_out_of_limits = [
                r for r in self.repeated_out_of_limits if r.name != user.name and r.ip != user.ip]

            self._in_process_ips.append(userByEmail.ip)

            ban_future = asyncio.run_coroutine_threadsafe(
                self.ban_user(userLast if BAN_LAST_USER else userByEmail),
                self.main_loop
            )
            ban_future.add_done_callback(lambda f: f.exception() and logger.error(f"Ban failed: {f.exception()}"))

            self._in_process_ips.remove(userByEmail.ip)

            self._storage.delete_user(userByEmail.name, userByEmail.ip)

            log_message = 'banned user ' + userByEmail.name+" with ip " + userByEmail.ip + \
                '\nnode: '+userByEmail.node + "\ninbound: "+userByEmail.inbound
            if ACCEPTED:
                log_message += '\naccepted: '+userByEmail.accepted
            logger.info(log_message)
            
            notif_future = asyncio.run_coroutine_threadsafe(
                send_notification_with_reply_markup(log_message, InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Unban IP", callback_data=userByEmail.ip)]])),
                self.main_loop
            )
            notif_future.add_done_callback(lambda f: f.exception() and logger.error(f"Notification failed: {f.exception()}"))

    async def ban_user(self, user: User):
        for node in nodes.keys():
            try:
                await nodes[node].BanUser(user)
            except Exception as err:
                logger.error('error: ', err)
