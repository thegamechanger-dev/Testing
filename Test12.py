# main.py
import nest_asyncio
nest_asyncio.apply()
import signal
from telegram.ext import filters
import random
import logging
import asyncio
import os
import functools
from datetime import datetime, timezone, timedelta
import re
import time
import configparser
from cachetools import TTLCache, LRUCache
import json
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions,
    ChatMember, Bot, User as TGUser, Chat as TGChat, Message as TGMessage,
    MessageEntity, __version__ as TG_VER, CallbackQuery
)
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.error import (
    BadRequest,
    Forbidden,
    InvalidToken,
    RetryAfter,
    TimedOut,
    NetworkError,
    TelegramError,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    filters,
    ContextTypes,
    JobQueue,
)
from typing import Dict, Optional, Tuple, List, Set, Any, Coroutine, Union, Callable
import logging.handlers
import warnings
from telegram.request import HTTPXRequest
import telegram
from database_ops import (
    init_db,
    close_db_pool,
    db_pool,
    db_execute,
    db_fetchone,
    db_fetchall,
    add_user,
    add_group,
    remove_group_from_db,
    get_group_punish_action,
    set_group_punish_action_async,
    get_group_punish_duration_for_trigger,
    set_group_punish_duration_for_trigger_async,
    set_all_group_punish_durations_async,
    add_group_user_exemption,
    remove_group_user_exemption,
    is_user_exempt_in_group,
    set_feature_state,
    get_all_groups_from_db,
    get_all_users_from_db,
    get_all_groups_count,
    get_all_users_count,
    add_unmute_attempt,
    get_last_unmute_attempt_time,
    add_bad_actor,
    is_bad_actor,
    add_timed_broadcast_to_db,
    remove_timed_broadcast_from_db,
    get_all_timed_broadcasts_from_db,
    log_action_db,
    deactivate_expired_restrictions_job,
    parse_duration,
    mark_user_started_bot,
    format_duration,
)

from telegram.ext import ContextTypes
from telegram.error import Forbidden, BadRequest
from typing import Union, Optional, Any
from logging import getLogger
import patterns
from patterns import LANGUAGE_STRINGS
from database_ops import BAD_ACTOR_EXPIRY_SECONDS as db_bad_actor_expiry_seconds
from cachetools import TTLCache
from telegram import ChatPermissions
import configparser

config = configparser.ConfigParser()
config.read("config.ini")
DATABASE_NAME = config.get("Bot", "DatabaseName", fallback="bards_sentinel_async.db")
ADMIN_CACHE_REFRESH_COOLDOWN = int(config.get("Bot", "AdminCacheRefreshCooldownSeconds", fallback=60))
BROADCAST_SLEEP_INTERVAL = float(config.get("Bot", "BroadcastSleepInterval", fallback=0.3))
AUTHORIZED_USERS = [int(uid) for uid in config.get("Admin", "AuthorizedUsers", fallback="").split(",") if uid.strip()]

logger = logging.getLogger(__name__)

# Constants
CACHE_MAXSIZE = 1024
CACHE_TTL_MINUTES = 30
CACHE_TTL_SECONDS = CACHE_TTL_MINUTES * 60

# Settings
settings: Dict[str, Any] = {
    "free_users": set(),
    "channel_id": None,
    "channel_invite_link": None,
    "active_timed_broadcasts": {},
    "default_lang": "english",
    "enable_db_dump": False,
}

# Global state for bulk command cancellation
bulk_command_state = {}  # {chat_id: {"command": str, "cancelled": bool}}

# Caches
user_profile_cache = TTLCache(maxsize=CACHE_MAXSIZE, ttl=CACHE_TTL_SECONDS)
username_to_id_cache = TTLCache(maxsize=CACHE_MAXSIZE, ttl=CACHE_TTL_SECONDS)
notification_debounce_cache = TTLCache(maxsize=1024, ttl=30)
message_processing_debounce_cache = TTLCache(maxsize=1000, ttl=10)
unmute_attempt_cache = TTLCache(maxsize=1024, ttl=60)
admin_cache: Dict[int, Tuple[Set[int], float]] = {}

# Permissions
mute_permissions_obj = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
    can_change_info=False,
    can_invite_users=False,
    can_pin_messages=False,
    can_manage_topics=False,
)

# Global Configuration Variables
CONFIG_FILE_NAME = "config.ini"
LOG_FILE_PATH = "bards_sentinel.log"
LOG_LEVEL = "INFO"
MAX_LOG_SIZE_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 1
DATABASE_NAME = "bards_sentinel_async.db"
DEFAULT_PUNISH_ACTION = "mute"
DEFAULT_PUNISH_DURATION_PROFILE_SECONDS = 0
DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS = 3600
DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS = 0
BAD_ACTOR_EXPIRY_DURATION_STR: str = "30d"
BAD_ACTOR_EXPIRY_SECONDS: int = 0
UNMUTE_RATE_LIMIT_DURATION_STR: str = "3h"
UNMUTE_RATE_LIMIT_SECONDS: int = 0
BROADCAST_SLEEP_INTERVAL = 0.2
MAX_COMMAND_ARGS_SPACES = 2
CACHE_TTL_MINUTES = 30
CACHE_MAXSIZE = 1024
CACHE_TTL_SECONDS = CACHE_TTL_MINUTES * 60
BULK_COMMAND_COOLDOWN_SECONDS = 3600
ADMIN_CACHE_REFRESH_COOLDOWN_SECONDS = 60
UNMUTEALL_TARGET_BOT_MUTES_ONLY = True
GUNMUTEALL_TARGET_BOT_MUTES_ONLY = True
UNBANALL_TARGET_BOT_BANS_ONLY = True
GUNBANALL_TARGET_BOT_BANS_ONLY = True
UNMUTE_ME_RATE_LIMIT_SECONDS = 3600
MAX_TOTAL_MEMORY_MB = 512
LOG_MAX_SIZE_MB = 50
CACHE_MAX_SIZE_MB = 100
DB_MAX_SIZE_MB = 300
BOT_TOKENS: List[str] = []
TOKEN: Optional[str] = None
AUTHORIZED_USERS: List[int] = []
SUPER_ADMINS_ARE_GLOBAL_ADMINS = True

class FallbackPatterns:
    SENDER_IS_BAD_ACTOR_REASON = {"english": "Known bad actor."}
    MESSAGE_VIOLATION_REASON = "Message contains forbidden content: {message_issue_type}"
    PUNISHMENT_MESSAGE_SENDER_ENGLISH = "<b>{user_mention}</b> has been {action_taken} due to {reason_detail}."
    START_MESSAGE_PRIVATE_BASE = "Welcome!"
    ADMIN_ONLY_COMMAND_MESSAGE = "Admins only."
    SUPER_ADMIN_ONLY_COMMAND_MESSAGE = "Super Admins only."
    COMMAND_GROUP_ONLY_MESSAGE = "Group only command."
    LOGGING_SETUP_MESSAGE = "Logging setup complete with level {log_level} to {log_file_path}."
    CONFIG_NOT_FOUND_MESSAGE = "Error: config.ini not found at {config_file_name}. Creating template."
    CONFIG_TEMPLATE_CREATED_MESSAGE = "Template config.ini created at {config_file_name}. Please fill it out."
    CONFIG_TOKEN_NOT_SET_MESSAGE = "Error: Bot Token not set in config.ini at {config_file_name}."
    CONFIG_LOAD_SUCCESS_MESSAGE = "Config loaded successfully."
    NO_AUTHORIZED_USERS_WARNING = "Warning: No authorized users found in config. Some commands will be inaccessible."
    CONFIG_LOAD_ERROR_MESSAGE = "Error loading config from {config_file_name}: {e}"
    UNMUTE_ME_CMD_USAGE = "Usage: /unmuteme <group_id or group_name_part>"
    UNMUTE_ME_MULTIPLE_GROUPS_FOUND = 'Found multiple groups matching "{group_identifier}":\n{group_list}\nPlease use a more specific identifier or the ID.'
    UNMUTE_ME_GROUP_NOT_FOUND = 'Group "{group_identifier}" not found or bot is not in it.'
    UNMUTE_ME_PROFILE_ISSUE_PM = "You cannot unmute yourself because your profile still has issues: {field}. Please fix it and try again."
    UNMUTE_ME_CHANNEL_ISSUE_PM = "You need to join our verification channel to use this feature. Join here: {channel_link}"
    UNMUTE_ME_FAIL_GROUP_CMD_NO_MUTE = 'You are not muted by this bot in "{group_name}".'
    UNMUTE_ME_SUCCESS_GROUP_CMD = 'You have been unmuted in "{group_name}".'
    UNMUTE_SUCCESS_MESSAGE_GROUP = "{user_mention} has unmuted themselves."
    UNMUTE_ME_FAIL_GROUP_CMD_OTHER = 'Failed to unmute you in "{group_name}": {error}'
    UNMUTE_ME_RATE_LIMITED_PM = "You are rate limited for this command. Please wait {wait_duration}."
    UNMUTE_ME_NO_MUTES_FOUND_PM = "No active mutes by this bot found for you across any groups."
    UNMUTE_ME_COMPLETED_PM = "Attempted to unmute you from {total_count} groups. Success: {success_count}, Failed: {fail_count}, Skipped: {skipped_count}."
    UNMUTE_ME_ALL_BOT_MUTES_BUTTON = "Unmute Me From All Bot Mutes"
    LANG_BUTTON_SELECT_LANGUAGE = "🌐 Select Language"
    HELP_BUTTON_TEXT = "ℹ️ Help"
    ADD_BOT_TO_GROUP_BUTTON_TEXT = "➕ Add {bot_username} to Group"
    JOIN_VERIFICATION_CHANNEL_BUTTON_TEXT = "✅ Join Verification Channel"
    VERIFY_JOIN_BUTTON_TEXT = "🔍 Verify Channel Join"
    START_MESSAGE_ADMIN_CONFIG = "Configure me by adding me to a group and making me an admin."
    START_MESSAGE_CHANNEL_VERIFY_INFO = "This bot may require users to join a channel for verification."
    START_MESSAGE_HELP_PROMPT = "Use /help in a group for commands or click the button below for more info."
    START_MESSAGE_GROUP = "Hello! I am {bot_username}. Use /help to see commands. Make me an admin to enable full features."
    RELOAD_ADMIN_CACHE_SUCCESS = "✅ Admin cache refreshed for this group."
    RELOAD_ADMIN_CACHE_FAIL_FORBIDDEN = "❌ Failed to refresh admin cache. I might not have permission or no longer be in this group."
    RELOAD_ADMIN_CACHE_FAIL_BADREQUEST = "❌ Failed to refresh admin cache. Bad request."
    RELOAD_ADMIN_CACHE_FAIL_ERROR = "❌ Failed to refresh admin cache: {error}"
    COMMAND_COOLDOWN_MESSAGE = "⏱️ This command has a cooldown. Please wait {duration} before using it again."
    ADMIN_ONLY_COMMAND_MESSAGE_RELOAD = "You must be an admin to refresh the cache."
    GMUTE_USAGE = "Usage: /gmute <user_id/@username> [duration] [reason]"
    GBAN_USAGE = "Usage: /gban <user_id/@username> [reason]"
    USER_NOT_FOUND_MESSAGE = 'Could not find user "{identifier}".'
    INVALID_DURATION_FORMAT_MESSAGE = "Invalid duration format: {duration_str}. Use formats like 30s, 5m, 1h, 7d, or 0 for permanent."
    CANNOT_ACTION_SUPER_ADMIN = "Cannot perform this action on a Super Admin."
    GMUTE_NO_GROUPS = "No groups found in the database to perform global mute."
    GBAN_NO_GROUPS = "No groups found in the database to perform global ban."
    GMUTE_STARTED = "Initiating global mute for user {target_user_id} in {count} groups..."
    GBAN_STARTED = "Initiating global ban for user {target_user_id} in {count} groups..."
    GMUTE_DEFAULT_REASON = "Globally muted by super admin."
    GBAN_DEFAULT_REASON = "Globally banned by super admin."
    GMUTE_COMPLETED = "Global mute complete for user {target_user_id}. Success: {success_count}, Failed: {fail_count}, Total groups checked: {total_groups}."
    GBAN_COMPLETED = "Global ban complete for user {target_user_id}. Success: {success_count}, Failed: {fail_count}, Total groups checked: {total_groups}."
    BULK_UNMUTE_STARTED_STATUS = "Starting bulk {operation_type} operation in group {group_id_display} for {target_count} users (Bot mutes only: {target_bot_mutes_only})...\nProgress: 0/{target_count} (Success: 0, Failed: 0, Skipped: 0)"
    BULK_UNMUTE_PROGRESS = "Progress: {processed_count}/{total_count} (Success: {success_count}, Failed: {fail_count}, Skipped: {skipped_count})"
    BULK_UNMUTE_COMPLETE = "Bulk {operation_type} operation completed in group {group_id_display}. Success: {success_count}, Failed: {fail_count}, Skipped: {skipped_count} (Total: {total_users})."
    BULK_UNBAN_STARTED_STATUS = "Starting bulk {operation_type} operation in group {group_id_display} for {target_count} users (Bot bans only: {target_bot_mutes_only})...\nProgress: 0/{target_count} (Success: 0, Failed: 0, Skipped: 0)"
    BULK_UNBAN_PROGRESS = "Progress: {processed_count}/{total_count} (Success: {success_count}, Failed: {fail_count}, Skipped: {skipped_count})"
    BULK_UNBAN_COMPLETE = "Bulk {operation_type} operation completed in group {group_id_display}. Success: {success_count}, Failed: {fail_count}, Skipped: {skipped_count} (Total: {total_users})."
    BULK_UNMUTE_NO_TARGETS = "No users found to {operation_type} in this group based on current settings."
    BULK_UNBAN_NO_TARGETS = "No users found to {operation_type} in this group based on current settings."
    BULK_UNMUTE_NO_GROUPS_GLOBAL = "No groups found in the database to perform global {operation_type}."
    BULK_UNBAN_NO_GROUPS_GLOBAL = "No groups found in the database to perform global {operation_type}."
    BULK_UNMUTE_STARTED_GLOBAL_STATUS = "Starting global {operation_type} operation across {group_count} groups..."
    BULK_UNBAN_STARTED_GLOBAL_STATUS = "Starting global {operation_type} operation across {group_count} groups..."
    BULK_UNMUTE_ALL_TASKS_DISPATCHED_GLOBAL = "Dispatched bulk {operation_type} tasks for {group_count} groups."
    BULK_UNBAN_ALL_TASKS_DISPATCHED_GLOBAL = "Dispatched bulk {operation_type} tasks for {group_count} groups."
    BCASTSELF_MESSAGE_TEMPLATE = "Check out {bot_username}! Add me to your group:"
    BCASTSELF_USER_USAGE_ERROR_ARGS = "Usage: /bcastselfuser [interval_duration]"
    BCASTSELF_GROUP_USAGE_ERROR_ARGS = "Usage: /bcastselfgroup [interval_duration]"
    BCASTSELF_COMBINED_USAGE_ERROR_ARGS = "Usage: /bcastself [interval_duration]"
    BCASTSELF_STARTED_MESSAGE = "Starting self-promotion broadcast to all known {target_type_plural}..."
    BCASTSELF_COMPLETE_MESSAGE = "Self-promotion broadcast complete to {target_type_plural}. Sent: {sent_count}, Failed: {failed_count}."
    BCAST_SCHEDULED_USERS = "Scheduled self-promotion broadcast to users every {duration} (Job name: {job_name})."
    BCAST_SCHEDULED_GROUPS = "Scheduled self-promotion broadcast to groups every {duration} (Job name: {job_name})."
    BCAST_SCHEDULED_COMBINED = "Scheduled self-promotion broadcasts: Users (Job: {job_name_users}), Groups (Job: {job_name_groups}) every {duration}."
    JOBQUEUE_NOT_AVAILABLE_MESSAGE = "Job queue is not available."
    BCASTSELF_STARTED_MESSAGE_COMBINED = "Starting self-promotion broadcast to all known users and groups..."
    BCASTSELF_COMPLETE_MESSAGE_COMBINED = "Self-promotion broadcast complete. Users Sent: {sent_users}, Failed: {failed_users}. Groups Sent: {sent_groups}, Failed: {failed_groups}."
    DB_DUMP_CAPTION = "Database backup from {date} (File: {file_name})"
    DB_DUMP_ADMIN_NOTIFICATION = "Database size ({db_size_mb}MB) exceeds limit ({db_max_size_mb}MB). Dumped to channel {dump_channel_id}. Manual cleanup may be needed."
    PERMANENT_TEXT = "Permanent"
    NOT_APPLICABLE = "N/A"
    LANG_BUTTON_PREV = "◀️ Prev"
    LANG_BUTTON_NEXT = "▶️ Next"
    LANG_SELECT_PROMPT = "Please select your language:"
    LANG_UPDATED_USER = "Your language has been set to {language_name}."
    LANG_UPDATED_GROUP = "The language for this group has been set to {language_name}."
    LANG_MORE_COMING_SOON = "More languages coming soon!"
    NEW_USER_PROFILE_VIOLATION_REASON = "New user profile violation: {field} ({issue_type})"
    ACTION_DEBOUNCED_SENDER = "Action on sender {user_id} in chat {chat_id} debounced."
    ACTION_DEBOUNCED_MENTION = "Action on mentioned user {user_id} in chat {chat_id} debounced."
    NO_PERMS_TO_ACT_SENDER = "Bot lacks permissions to {action} user {user_id} in chat {chat_id}."
    BADREQUEST_TO_ACT_SENDER = "BadRequest acting on sender {user_id} in chat {chat_id} for {action}: {e}"
    ERROR_ACTING_SENDER = "Error acting on sender {user_id} in chat {chat_id} for {action}: {e}"
    NO_PERMS_TO_ACT_MENTION = "Bot lacks permissions to restrict user {user_id} (@{username}) in chat {chat_id}."
    BADREQUEST_TO_ACT_MENTION = "BadRequest acting on mentioned user {user_id} (@{username}) in chat {chat_id}: {e}"
    ERROR_ACTING_MENTION = "Error acting on mentioned user {user_id} (@{username}) in chat {chat_id}: {e}"
    BIO_LINK_DIALOGUES_LIST = [{"english": "Content violates rules."}]

# Command parsing patterns
COMMAND_PATTERNS: Dict[str, Dict[str, List[str]]] = {
    "initiators": {"values": ["/", "!", "."]},
    "commands": {
        "mute": ["mute", "smute", "dmute", "fmute"],
        "ban": ["ban", "fban", "dban", "sban"],
        "kick": ["kick", "skick", "dkick"],
    },
    "durations": {
        "s": ["s", "sec", "secs", "second", "seconds"],
        "m": ["m", "min", "mins", "minute", "minutes"],
        "h": ["h", "hr", "hrs", "hour", "hours"],
        "d": ["d", "day", "days"],
    },
}
COMMAND_CONFIG_REGEX_STRING: str = ""

# In-memory Caches & State
message_processing_debounce_cache = TTLCache(maxsize=1000, ttl=10)
notification_debounce_cache = TTLCache(maxsize=1024, ttl=30)
unmute_attempt_cache = TTLCache(maxsize=1024, ttl=60)
user_profile_cache: Optional[TTLCache] = None
username_to_id_cache: Optional[TTLCache] = None
admin_cache: Dict[int, Tuple[Set[int], float]] = {}
bot_instances_cache: Dict[str, Application] = {}
applications: List[Application] = []

MAINTENANCE_MODE = False
settings: Dict[str, Any] = {
    "free_users": set(),
    "channel_id": None,
    "channel_invite_link": None,
    "active_timed_broadcasts": {},
    "default_lang": "english",
    "enable_db_dump": False,
}
bot_username_cache: Optional[str] = None
specific_logger_levels: Dict[str, str] = {}
bot_start_time: float = time.time()

# Unmute permissions
unmute_permissions = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_change_info=True,
    can_invite_users=True,
    can_pin_messages=True,
    can_manage_topics=True,
)

# Language data
LANGUAGES = {
    "english": {"name": "English", "flag": "🇺🇸", "strings": {}},
    "es": {"name": "Español", "flag": "🇪🇸", "strings": {}},
    "hindi": {"name": "हिन्दी", "flag": "🇮🇳", "strings": {}},
}
LANG_CALLBACK_PREFIX = "setlang_"
LANG_PAGE_SIZE = 6

try:
    for attr_name in dir(patterns):
        if not attr_name.startswith("__"):
            attr_value = getattr(patterns, attr_name)
            if isinstance(attr_value, (str, dict, list)):
                LANGUAGES["english"]["strings"][attr_name] = attr_value
except Exception as e:
    logger.critical(f"Failed to load patterns: {e}")
    raise

logger = logging.getLogger(__name__)

REQUIRED_PATTERNS_CHECK = [
    "MESSAGE_VIOLATION_REASON",
    "PUNISHMENT_MESSAGE_SENDER_ENGLISH",
    "START_MESSAGE_PRIVATE_BASE",
    "ADMIN_ONLY_COMMAND_MESSAGE",
    "SUPER_ADMIN_ONLY_COMMAND_MESSAGE",
    "COMMAND_GROUP_ONLY_MESSAGE",
    "LOGGING_SETUP_MESSAGE",
    "CONFIG_NOT_FOUND_MESSAGE",
    "CONFIG_TEMPLATE_CREATED_MESSAGE",
    "CONFIG_TOKEN_NOT_SET_MESSAGE",
    "CONFIG_LOAD_SUCCESS_MESSAGE",
    "NO_AUTHORIZED_USERS_WARNING",
    "CONFIG_LOAD_ERROR_MESSAGE",
    "UNMUTE_ME_CMD_USAGE",
    "UNMUTE_ME_MULTIPLE_GROUPS_FOUND",
    "UNMUTE_ME_GROUP_NOT_FOUND",
    "UNMUTE_ME_PROFILE_ISSUE_PM",
    "UNMUTE_ME_CHANNEL_ISSUE_PM",
    "UNMUTE_ME_FAIL_GROUP_CMD_NO_MUTE",
    "UNMUTE_ME_SUCCESS_GROUP_CMD",
    "UNMUTE_SUCCESS_MESSAGE_GROUP",
    "UNMUTE_ME_FAIL_GROUP_CMD_OTHER",
    "UNMUTE_ME_RATE_LIMITED_PM",
    "UNMUTE_ME_NO_MUTES_FOUND_PM",
    "UNMUTE_ME_COMPLETED_PM",
    "UNMUTE_ME_ALL_BOT_MUTES_BUTTON",
    "LANG_BUTTON_SELECT_LANGUAGE",
    "HELP_BUTTON_TEXT",
    "ADD_BOT_TO_GROUP_BUTTON_TEXT",
    "JOIN_VERIFICATION_CHANNEL_BUTTON_TEXT",
    "VERIFY_JOIN_BUTTON_TEXT",
    "START_MESSAGE_ADMIN_CONFIG",
    "START_MESSAGE_CHANNEL_VERIFY_INFO",
    "START_MESSAGE_HELP_PROMPT",
    "START_MESSAGE_GROUP",
    "RELOAD_ADMIN_CACHE_SUCCESS",
    "RELOAD_ADMIN_CACHE_FAIL_FORBIDDEN",
    "RELOAD_ADMIN_CACHE_FAIL_BADREQUEST",
    "RELOAD_ADMIN_CACHE_FAIL_ERROR",
    "COMMAND_COOLDOWN_MESSAGE",
    "ADMIN_ONLY_COMMAND_MESSAGE_RELOAD",
    "GMUTE_USAGE",
    "GBAN_USAGE",
    "USER_NOT_FOUND_MESSAGE",
    "INVALID_DURATION_FORMAT_MESSAGE",
    "CANNOT_ACTION_SUPER_ADMIN",
    "GMUTE_NO_GROUPS",
    "GBAN_NO_GROUPS",
    "GMUTE_STARTED",
    "GBAN_STARTED",
    "GMUTE_DEFAULT_REASON",
    "GBAN_DEFAULT_REASON",
    "GMUTE_COMPLETED",
    "GBAN_COMPLETED",
    "BULK_UNMUTE_STARTED_STATUS",
    "BULK_UNMUTE_PROGRESS",
    "BULK_UNMUTE_COMPLETE",
    "BULK_UNBAN_STARTED_STATUS",
    "BULK_UNBAN_PROGRESS",
    "BULK_UNBAN_COMPLETE",
    "BULK_UNMUTE_NO_TARGETS",
    "BULK_UNBAN_NO_TARGETS",
    "BULK_UNMUTE_NO_GROUPS_GLOBAL",
    "BULK_UNBAN_NO_GROUPS_GLOBAL",
    "BULK_UNMUTE_STARTED_GLOBAL_STATUS",
    "BULK_UNBAN_STARTED_GLOBAL_STATUS",
    "BULK_UNMUTE_ALL_TASKS_DISPATCHED_GLOBAL",
    "BULK_UNBAN_ALL_TASKS_DISPATCHED_GLOBAL",
    "BCASTSELF_MESSAGE_TEMPLATE",
    "BCASTSELF_USER_USAGE_ERROR_ARGS",
    "BCASTSELF_GROUP_USAGE_ERROR_ARGS",
    "BCASTSELF_COMBINED_USAGE_ERROR_ARGS",
    "BCASTSELF_STARTED_MESSAGE",
    "BCASTSELF_COMPLETE_MESSAGE",
    "BCAST_SCHEDULED_USERS",
    "BCAST_SCHEDULED_GROUPS",
    "BCAST_SCHEDULED_COMBINED",
    "JOBQUEUE_NOT_AVAILABLE_MESSAGE",
    "BCASTSELF_STARTED_MESSAGE_COMBINED",
    "BCASTSELF_COMPLETE_MESSAGE_COMBINED",
    "DB_DUMP_CAPTION",
    "DB_DUMP_ADMIN_NOTIFICATION",
    "PERMANENT_TEXT",
    "NOT_APPLICABLE",
    "LANG_BUTTON_PREV",
    "LANG_BUTTON_NEXT",
    "LANG_SELECT_PROMPT",
    "LANG_UPDATED_USER",
    "LANG_UPDATED_GROUP",
    "LANG_MORE_COMING_SOON",
    "NEW_USER_PROFILE_VIOLATION_REASON",
    "ACTION_DEBOUNCED_SENDER",
    "ACTION_DEBOUNCED_MENTION",
    "NO_PERMS_TO_ACT_SENDER",
    "BADREQUEST_TO_ACT_SENDER",
    "ERROR_ACTING_SENDER",
    "NO_PERMS_TO_ACT_MENTION",
    "BADREQUEST_TO_ACT_MENTION",
    "ERROR_ACTING_MENTION",
    "SENDER_IS_BAD_ACTOR_REASON",
    "BIO_LINK_DIALOGUES_LIST",
]

try:
    for attr in REQUIRED_PATTERNS_CHECK:
        if attr in ["SENDER_IS_BAD_ACTOR_REASON", "BIO_LINK_DIALOGUES_LIST", "MESSAGE_VIOLATION_REASON"]:
            if not hasattr(patterns, attr):
                logger.error(f"Missing required attribute in patterns.py: {attr}. Setting fallback.")
                if attr == "SENDER_IS_BAD_ACTOR_REASON":
                    setattr(patterns, attr, {"english": "Known bad actor.", "hindi": "ज्ञात दुष्ट।"})
                elif attr == "BIO_LINK_DIALOGUES_LIST":
                    setattr(patterns, attr, [])
                elif attr == "MESSAGE_VIOLATION_REASON":
                    setattr(patterns, attr, "Message violation: {message_issue_type}")
        else:
            if attr not in LANGUAGE_STRINGS:
                logger.error(f"Missing required key in patterns.py LANGUAGE_STRINGS: {attr}. Setting fallback.")
                LANGUAGE_STRINGS[attr] = f"MISSING_PATTERN_{attr}"
            elif not isinstance(LANGUAGE_STRINGS[attr], str) or not LANGUAGE_STRINGS[attr]:
                logger.warning(f"Invalid or empty value for LANGUAGE_STRINGS['{attr}']. Setting fallback.")
                LANGUAGE_STRINGS[attr] = f"MISSING_PATTERN_{attr}"
except NameError as e:
    logger.critical(f"Failed to validate patterns: {e}. Ensure patterns.py is correctly imported.")
    raise
except Exception as e:
    logger.critical(f"Unexpected error validating patterns: {e}")
    raise

LOGGING_SETUP_MESSAGE_PATTERN = LANGUAGE_STRINGS.get(
    "LOGGING_SETUP_MESSAGE",
    "Logging setup complete with level {log_level} to {log_file_path}.",
)

class SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"

def setup_logging():
    log_level_enum = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level_enum,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )
    if LOG_FILE_PATH:
        try:
            file_handler = logging.handlers.RotatingFileHandler(
                LOG_FILE_PATH,
                maxBytes=MAX_LOG_SIZE_BYTES,
                backupCount=LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            logging.getLogger().addHandler(file_handler)
            logger.info(f"File logging enabled to {LOG_FILE_PATH}")
        except Exception as e:
            logger.error(f"Failed to set up file logging to {LOG_FILE_PATH}: {e}")
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    for logger_name, level_str in specific_logger_levels.items():
        level_upper = level_str.upper()
        if level_upper in valid_levels:
            logging.getLogger(logger_name).setLevel(level_upper)
            logger.debug(f"Set logger '{logger_name}' level to {level_upper}")
        else:
            logger.warning(f"Invalid log level '{level_str}' for logger '{logger_name}'")
    logger.info(LOGGING_SETUP_MESSAGE_PATTERN.format(log_level=LOG_LEVEL, log_file_path=LOG_FILE_PATH or "Console Only"))

async def load_config():
    global TOKEN, DATABASE_NAME, DEFAULT_PUNISH_ACTION, AUTHORIZED_USERS, CACHE_TTL_MINUTES, CACHE_MAXSIZE
    global DEFAULT_PUNISH_DURATION_PROFILE_SECONDS, DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS, DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS
    global LOG_FILE_PATH, LOG_LEVEL, MAX_LOG_SIZE_BYTES, LOG_BACKUP_COUNT, BROADCAST_SLEEP_INTERVAL, MAX_COMMAND_ARGS_SPACES
    global BAD_ACTOR_EXPIRY_DURATION_STR, BAD_ACTOR_EXPIRY_SECONDS, UNMUTE_RATE_LIMIT_DURATION_STR, UNMUTE_RATE_LIMIT_SECONDS
    global user_profile_cache, username_to_id_cache, CACHE_TTL_SECONDS, specific_logger_levels
    global BULK_COMMAND_COOLDOWN_SECONDS, ADMIN_CACHE_REFRESH_COOLDOWN_SECONDS
    global UNMUTEALL_TARGET_BOT_MUTES_ONLY, GUNMUTEALL_TARGET_BOT_MUTES_ONLY
    global UNBANALL_TARGET_BOT_BANS_ONLY, GUNBANALL_TARGET_BOT_BANS_ONLY
    global COMMAND_PATTERNS, COMMAND_CONFIG_REGEX_STRING
    global UNMUTE_ME_RATE_LIMIT_SECONDS
    global MAX_TOTAL_MEMORY_MB, LOG_MAX_SIZE_MB, CACHE_MAX_SIZE_MB, DB_MAX_SIZE_MB, DB_DUMP_CHANNEL_ID
    global BOT_TOKENS, SUPER_ADMINS_ARE_GLOBAL_ADMINS

    config = configparser.ConfigParser(allow_no_value=True)
    config_file = os.path.abspath(CONFIG_FILE_NAME)

    if not os.path.exists(config_file):
        logging.critical(f"config.ini not found at {config_file}. Creating a template config file.")
        config["Bot"] = {
            "Token": "YOUR_PRIMARY_BOT_TOKEN_HERE",
            "OtherBotTokens": "; Optional: YOUR_SECOND_BOT_TOKEN,YOUR_THIRD_BOT_TOKEN (comma-separated)",
            "DatabaseName": DATABASE_NAME,
            "DefaultPunishAction": DEFAULT_PUNISH_ACTION,
            "DefaultPunishDurationProfileSeconds": str(DEFAULT_PUNISH_DURATION_PROFILE_SECONDS),
            "DefaultPunishDurationMessageSeconds": str(DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS),
            "DefaultPunishDurationMentionProfileSeconds": str(DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS),
            "MinUsernameLength": str(getattr(patterns, "MIN_USERNAME_LENGTH", 5)),
            "BadActorExpiryDuration": BAD_ACTOR_EXPIRY_DURATION_STR,
            "UnmuteRateLimitDuration": UNMUTE_RATE_LIMIT_DURATION_STR,
            "BroadcastSleepInterval": str(BROADCAST_SLEEP_INTERVAL),
            "MaxCommandArgsSpaces": str(MAX_COMMAND_ARGS_SPACES),
            "BulkCommandCooldownSeconds": str(BULK_COMMAND_COOLDOWN_SECONDS),
            "AdminCacheRefreshCooldownSeconds": str(ADMIN_CACHE_REFRESH_COOLDOWN_SECONDS),
            "UnmuteallTargetBotMutesOnly": str(UNMUTEALL_TARGET_BOT_MUTES_ONLY),
            "GunmuteallTargetBotMutesOnly": str(GUNMUTEALL_TARGET_BOT_MUTES_ONLY),
            "UnbanallTargetBotBansOnly": str(UNBANALL_TARGET_BOT_BANS_ONLY),
            "GunbanallTargetBotBansOnly": str(GUNBANALL_TARGET_BOT_BANS_ONLY),
            "UnmuteMeRateLimitSeconds": str(UNMUTE_ME_RATE_LIMIT_SECONDS),
        }
        config["Admin"] = {
            "AuthorizedUsers": "",
            "SuperAdminsAreGlobalAdmins": str(SUPER_ADMINS_ARE_GLOBAL_ADMINS),
        }
        config["Cache"] = {
            "TTLMinutes": str(CACHE_TTL_MINUTES),
            "MaxSize": str(CACHE_MAXSIZE),
        }
        config["Channel"] = {"ChannelId": "", "ChannelInviteLink": ""}
        config["Logging"] = {
            "LogFilePath": LOG_FILE_PATH,
            "LogLevel": LOG_LEVEL,
            "MaxLogSizeBytes": str(MAX_LOG_SIZE_BYTES),
            "LogBackupCount": str(LOG_BACKUP_COUNT),
        }
        config["Logging.Levels"] = {"httpx": "WARNING"}
        config["CommandParsing"] = {
            "Initiator": "/, !, .",
            "CommandMute": "mute, smute, dmute, fmute",
            "CommandBan": "ban, fban, dban, sban",
            "CommandKick": "kick, skick, dkick",
            "DurationSeconds": "s, sec, secs, second, seconds",
            "DurationMinutes": "m, min, mins, minute, minutes",
            "DurationHours": "h, hr, hrs, hour, hours",
            "DurationDays": "d, day, days",
            "CommandPattern": "{initiator}{command} {duration} {reason}",
        }
        config["MemoryManagement"] = {
            "MaxTotalMemoryMB": str(MAX_TOTAL_MEMORY_MB),
            "LogMaxSizeMB": str(LOG_MAX_SIZE_MB),
            "CacheMaxSizeMB": str(CACHE_MAX_SIZE_MB),
            "DbMaxSizeMB": str(DB_MAX_SIZE_MB),
            "EnableDBDump": "False",
            "DbDumpChannelId": "; Super Admin Channel ID for DB dumps",
        }
        with open(config_file, "w", encoding="utf-8") as configfile:
            config.write(configfile)
        logging.critical(f"config.ini template created at {config_file}. Please edit it with your Bot Token. Exiting.")
        sys.exit(1)

    try:
        config.read(config_file, encoding="utf-8")
        # Bot Section
        TOKEN = config.get("Bot", "Token", fallback="")
        if not re.match(r"^\d{8,10}:[A-Za-z0-9_-]{35}$", TOKEN) or TOKEN == "YOUR_PRIMARY_BOT_TOKEN_HERE":
            logging.critical(f"Invalid or placeholder token in {config_file}. Please set a valid token. Exiting.")
            sys.exit(1)

        other_tokens_str = config.get("Bot", "OtherBotTokens", fallback="")
        BOT_TOKENS = [TOKEN]
        if other_tokens_str:
            BOT_TOKENS.extend(t.strip() for t in other_tokens_str.split(",") if t.strip() and not t.strip().startswith(";"))
            BOT_TOKENS = list(dict.fromkeys(BOT_TOKENS))  # Remove duplicates

        DATABASE_NAME = config.get("Bot", "DatabaseName", fallback=DATABASE_NAME)
        DEFAULT_PUNISH_ACTION = config.get("Bot", "DefaultPunishAction", fallback=DEFAULT_PUNISH_ACTION).lower()
        DEFAULT_PUNISH_DURATION_PROFILE_SECONDS = config.getint(
            "Bot", "DefaultPunishDurationProfileSeconds", fallback=DEFAULT_PUNISH_DURATION_PROFILE_SECONDS
        )
        DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS = config.getint(
            "Bot", "DefaultPunishDurationMessageSeconds", fallback=DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS
        )
        DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS = config.getint(
            "Bot", "DefaultPunishDurationMentionProfileSeconds", fallback=DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS
        )
        BROADCAST_SLEEP_INTERVAL = config.getfloat("Bot", "BroadcastSleepInterval", fallback=BROADCAST_SLEEP_INTERVAL)
        MAX_COMMAND_ARGS_SPACES = config.getint("Bot", "MaxCommandArgsSpaces", fallback=MAX_COMMAND_ARGS_SPACES)
        BAD_ACTOR_EXPIRY_DURATION_STR = config.get("Bot", "BadActorExpiryDuration", fallback=BAD_ACTOR_EXPIRY_DURATION_STR)
        BAD_ACTOR_EXPIRY_SECONDS = await parse_duration(BAD_ACTOR_EXPIRY_DURATION_STR) or 0
        logging.info(f"Main config loaded BAD_ACTOR_EXPIRY_SECONDS as: {BAD_ACTOR_EXPIRY_SECONDS}.")
        try:
            import database_ops
            database_ops.BAD_ACTOR_EXPIRY_SECONDS = BAD_ACTOR_EXPIRY_SECONDS
            logging.info(f"Updated BAD_ACTOR_EXPIRY_SECONDS in database_ops to {database_ops.BAD_ACTOR_EXPIRY_SECONDS}.")
        except ImportError:
            logging.warning("Could not import database_ops to set BAD_ACTOR_EXPIRY_SECONDS.")
        except Exception as e:
            logging.error(f"Error setting BAD_ACTOR_EXPIRY_SECONDS in database_ops: {e}", exc_info=True)
        UNMUTE_RATE_LIMIT_DURATION_STR = config.get("Bot", "UnmuteRateLimitDuration", fallback=UNMUTE_RATE_LIMIT_DURATION_STR)
        UNMUTE_RATE_LIMIT_SECONDS = await parse_duration(UNMUTE_RATE_LIMIT_DURATION_STR) or 0
        logging.info(f"Main config loaded UNMUTE_RATE_LIMIT_SECONDS as: {UNMUTE_RATE_LIMIT_SECONDS}.")
        UNMUTE_ME_RATE_LIMIT_SECONDS = config.getint(
            "Bot", "UnmuteMeRateLimitSeconds", fallback=UNMUTE_ME_RATE_LIMIT_SECONDS
        )
        logging.info(f"Main config loaded UNMUTE_ME_RATE_LIMIT_SECONDS as: {UNMUTE_ME_RATE_LIMIT_SECONDS}.")

        min_username_fallback = getattr(patterns, "MIN_USERNAME_LENGTH", 5)
        patterns.MIN_USERNAME_LENGTH = config.getint("Bot", "MinUsernameLength", fallback=min_username_fallback)

        BULK_COMMAND_COOLDOWN_SECONDS = config.getint(
            "Bot", "BulkCommandCooldownSeconds", fallback=BULK_COMMAND_COOLDOWN_SECONDS
        )
        ADMIN_CACHE_REFRESH_COOLDOWN_SECONDS = config.getint(
            "Bot", "AdminCacheRefreshCooldownSeconds", fallback=ADMIN_CACHE_REFRESH_COOLDOWN_SECONDS
        )
        UNMUTEALL_TARGET_BOT_MUTES_ONLY = config.getboolean(
            "Bot", "UnmuteallTargetBotMutesOnly", fallback=UNMUTEALL_TARGET_BOT_MUTES_ONLY
        )
        GUNMUTEALL_TARGET_BOT_MUTES_ONLY = config.getboolean(
            "Bot", "GunmuteallTargetBotMutesOnly", fallback=GUNMUTEALL_TARGET_BOT_MUTES_ONLY
        )
        UNBANALL_TARGET_BOT_BANS_ONLY = config.getboolean(
            "Bot", "UnbanallTargetBotBansOnly", fallback=UNBANALL_TARGET_BOT_BANS_ONLY
        )
        GUNBANALL_TARGET_BOT_BANS_ONLY = config.getboolean(
            "Bot", "GunbanallTargetBotBansOnly", fallback=GUNBANALL_TARGET_BOT_BANS_ONLY
        )

        # Admin Section
        auth_users_str = config.get("Admin", "AuthorizedUsers", fallback="")
        AUTHORIZED_USERS = [int(uid.strip()) for uid in auth_users_str.split(",") if uid.strip().isdigit()]
        SUPER_ADMINS_ARE_GLOBAL_ADMINS = config.getboolean(
            "Admin", "SuperAdminsAreGlobalAdmins", fallback=SUPER_ADMINS_ARE_GLOBAL_ADMINS
        )

        # Cache Section
        CACHE_TTL_MINUTES = config.getint("Cache", "TTLMinutes", fallback=CACHE_TTL_MINUTES)
        if CACHE_TTL_MINUTES <= 0:
            logging.warning(f"Invalid CACHE_TTL_MINUTES {CACHE_TTL_MINUTES}. Using default 30.")
            CACHE_TTL_MINUTES = 30
        CACHE_MAXSIZE = config.getint("Cache", "MaxSize", fallback=CACHE_MAXSIZE)
        CACHE_TTL_SECONDS = CACHE_TTL_MINUTES * 60
        user_profile_cache = TTLCache(maxsize=CACHE_MAXSIZE, ttl=CACHE_TTL_SECONDS)
        username_to_id_cache = TTLCache(maxsize=CACHE_MAXSIZE, ttl=CACHE_TTL_SECONDS)
        logging.info(f"Caches initialized with TTL: {CACHE_TTL_SECONDS}s, MaxSize: {CACHE_MAXSIZE}")

        # Channel Section
        settings["channel_id"] = config.get("Channel", "ChannelId", fallback=None)
        if settings["channel_id"] and isinstance(settings["channel_id"], str) and settings["channel_id"].strip().lstrip("-").isdigit():
            settings["channel_id"] = int(settings["channel_id"])
        else:
            settings["channel_id"] = None
        settings["channel_invite_link"] = config.get("Channel", "ChannelInviteLink", fallback=None)
        if settings["channel_invite_link"] and settings["channel_invite_link"].strip() == "":
            settings["channel_invite_link"] = None

        # Logging Section
        LOG_FILE_PATH = config.get("Logging", "LogFilePath", fallback=LOG_FILE_PATH)
        LOG_LEVEL = config.get("Logging", "LogLevel", fallback=LOG_LEVEL).upper()
        MAX_LOG_SIZE_BYTES = config.getint("Logging", "MaxLogSizeBytes", fallback=MAX_LOG_SIZE_BYTES)
        LOG_BACKUP_COUNT = config.getint("Logging", "LogBackupCount", fallback=LOG_BACKUP_COUNT)

        # Specific Logging Levels Section
        specific_logger_levels.clear()
        if "Logging.Levels" in config:
            for logger_name, level_str in config["Logging.Levels"].items():
                specific_logger_levels[logger_name.strip()] = level_str.strip().upper()

        # Command Parsing Section
        if "CommandParsing" in config:
            COMMAND_PATTERNS["initiators"]["values"] = [
                p.strip() for p in config.get("CommandParsing", "Initiator", fallback="/, !, .").split(",")
            ]
            COMMAND_PATTERNS["commands"]["mute"] = [
                p.strip() for p in config.get("CommandParsing", "CommandMute", fallback="mute, smute, dmute, fmute").split(",")
            ]
            COMMAND_PATTERNS["commands"]["ban"] = [
                p.strip() for p in config.get("CommandParsing", "CommandBan", fallback="ban, fban, dban, sban").split(",")
            ]
            COMMAND_PATTERNS["commands"]["kick"] = [
                p.strip() for p in config.get("CommandParsing", "CommandKick", fallback="kick, skick, dkick").split(",")
            ]
            COMMAND_PATTERNS["durations"]["s"] = [
                p.strip() for p in config.get("CommandParsing", "DurationSeconds", fallback="s, sec, secs, second, seconds").split(",")
            ]
            COMMAND_PATTERNS["durations"]["m"] = [
                p.strip() for p in config.get("CommandParsing", "DurationMinutes", fallback="m, min, mins, minute, minutes").split(",")
            ]
            COMMAND_PATTERNS["durations"]["h"] = [
                p.strip() for p in config.get("CommandParsing", "DurationHours", fallback="h, hr, hrs, hour, hours").split(",")
            ]
            COMMAND_PATTERNS["durations"]["d"] = [
                p.strip() for p in config.get("CommandParsing", "DurationDays", fallback="d, day, days").split(",")
            ]
            COMMAND_CONFIG_REGEX_STRING = config.get(
                "CommandParsing", "CommandPattern", fallback="{initiator}{command} {duration} {reason}"
            )

        # Memory Management Section
        MAX_TOTAL_MEMORY_MB = config.getint("MemoryManagement", "MaxTotalMemoryMB", fallback=MAX_TOTAL_MEMORY_MB)
        LOG_MAX_SIZE_MB = config.getint("MemoryManagement", "LogMaxSizeMB", fallback=LOG_MAX_SIZE_MB)
        CACHE_MAX_SIZE_MB = config.getint("MemoryManagement", "CacheMaxSizeMB", fallback=CACHE_MAX_SIZE_MB)
        DB_MAX_SIZE_MB = config.getint("MemoryManagement", "DbMaxSizeMB", fallback=DB_MAX_SIZE_MB)
        settings["enable_db_dump"] = config.getboolean("MemoryManagement", "EnableDBDump", fallback=False)
        DB_DUMP_CHANNEL_ID = config.get("MemoryManagement", "DbDumpChannelId", fallback=None)
        if DB_DUMP_CHANNEL_ID and isinstance(DB_DUMP_CHANNEL_ID, str) and DB_DUMP_CHANNEL_ID.strip().lstrip("-").isdigit():
            DB_DUMP_CHANNEL_ID = int(DB_DUMP_CHANNEL_ID)
        else:
            DB_DUMP_CHANNEL_ID = None
        if settings["enable_db_dump"] and DB_DUMP_CHANNEL_ID is None:
            logging.warning("DB dumping is enabled, but DbDumpChannelId is not set or invalid in config.")

        logging.info("Configuration loaded successfully.")
        if not AUTHORIZED_USERS:
            logging.warning("No authorized users configured in config.ini.")
    except configparser.MissingSectionHeaderError:
        logging.critical(f"Invalid config.ini format in {config_file}: Missing section header. Exiting.")
        sys.exit(1)
    except configparser.ParsingError as e:
        logging.critical(f"Error parsing {config_file}: {e}. Exiting.")
        sys.exit(1)
    except Exception as e:
        logging.critical(f"Unexpected error loading {config_file}: {e}. Exiting.")
        sys.exit(1)
        
async def get_feature_state(feature_name: str, default: bool = True) -> bool:
    logger = logging.getLogger(__name__)
    try:
        row = await db_fetchone("SELECT is_enabled FROM feature_control WHERE feature_name = ?", (feature_name,))
        if row is None:
            logger.debug(f"Feature state for '{feature_name}' not found in DB. Returning default: {default}")
            return default
        logger.debug(f"Retrieved feature state for '{feature_name}': {row[0]}")
        return bool(row[0])
    except Exception as e:
        logger.error(f"Error fetching feature state for '{feature_name}': {e}", exc_info=True)
        return default
        
async def cleanup_caches_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        if user_profile_cache:
            before = len(user_profile_cache)
            logger.debug(f"Profile cache size: {before}")
        if username_to_id_cache:
            before = len(username_to_id_cache)
            logger.debug(f"Username cache size: {before}")
    except Exception as e:
        logger.error(f"Error in cleanup_caches_job: {e}", exc_info=True)


from telegram.error import BadRequest
from patterns import BOT_MENTION_PATTERN  # Import from patterns.py

logger = logging.getLogger(__name__)

async def get_chat_safe(bot, chat_id_or_username):
    """
    Safely fetch chat details, skipping bot mentions and handling errors.
    
    Args:
        bot: Telegram Bot instance
        chat_id_or_username: Chat ID or username (e.g., @username)
    
    Returns:
        Chat object if successful, None otherwise
    """
    # Check if the input is a username and matches a bot pattern
    if isinstance(chat_id_or_username, str) and chat_id_or_username.startswith('@'):
        if re.match(BOT_MENTION_PATTERN, chat_id_or_username, re.IGNORECASE):
            logger.info(f"Skipping getChat for bot mention: {chat_id_or_username}")
            return None
    
    try:
        chat = await get_chat_safe(chat_id_or_username)
        return chat
    except BadRequest as e:
        if "Chat not found" in str(e):
            logger.warning(f"Chat not found for {chat_id_or_username}: {e}")
        else:
            logger.error(f"Error fetching chat {chat_id_or_username}: {e}")
        return None

async def get_cached_admins(context: ContextTypes.DEFAULT_TYPE, chat_id: int, force_refresh: bool = False) -> Set[int]:
    global admin_cache, ADMIN_CACHE_REFRESH_COOLDOWN_SECONDS
    now = time.time()
    cached_admins_set = set()

    if not force_refresh and chat_id in admin_cache:
        cached_data, last_refresh_time = admin_cache[chat_id]
        if (now - last_refresh_time) < ADMIN_CACHE_REFRESH_COOLDOWN_SECONDS:
            logger.debug(f"Admin cache hit for chat {chat_id}.")
            return cached_data

    try:
        chat_admins_list = await get_chat_administrators_mb(context.bot, chat_id)
        if chat_admins_list is not None:
            admin_ids = {admin.user.id for admin in chat_admins_list}
            admin_cache[chat_id] = (admin_ids, now)
            logger.debug(f"Admin cache updated for chat {chat_id} with {len(admin_ids)} admins.")
            return admin_ids
        else:
            logger.warning(f"get_chat_administrators_mb failed for chat {chat_id}. Bot might not be a member or lacks permissions.")
            if chat_id in admin_cache:
                stale_admins, _ = admin_cache[chat_id]
                admin_cache[chat_id] = (stale_admins, now)
                return stale_admins
            return cached_admins_set
    except Forbidden:
        logger.warning(f"Failed to get admins for chat {chat_id} (Forbidden). Removing from admin cache.")
        if chat_id in admin_cache:
            del admin_cache[chat_id]
        return cached_admins_set
    except BadRequest:
        logger.warning(f"Failed to get admins for chat {chat_id} (BadRequest). Removing from admin cache.")
        if chat_id in admin_cache:
            del admin_cache[chat_id]
        return cached_admins_set
    except Exception as e:
        logger.error(f"Unexpected error fetching admins for chat {chat_id}: {e}", exc_info=True)
        if chat_id in admin_cache:
            return admin_cache[chat_id][0]
        return cached_admins_set

async def command_cooldown_check_and_update(
    context: Optional[ContextTypes.DEFAULT_TYPE],
    chat_id: int,
    user_id: int,
    command_name: str,
    cooldown_seconds: int,
) -> bool:
    logger = logging.getLogger(__name__)
    now_dt = datetime.now(timezone.utc)
    try:
        row = await db_fetchone(
            "SELECT last_used_timestamp FROM command_cooldowns WHERE chat_id = ? AND user_id = ? AND command_name = ?",
            (chat_id, user_id, command_name),
        )
        if row and row[0]:
            try:
                last_used_dt = datetime.fromisoformat(row[0])
                if (now_dt - last_used_dt).total_seconds() < cooldown_seconds:
                    return False
            except ValueError:
                logger.error(f"Invalid timestamp format in command_cooldowns for chat {chat_id}, user {user_id}, command {command_name}")
            except Exception as e:
                logger.error(f"Error checking cooldown for chat {chat_id}, user {user_id}, command {command_name}: {e}", exc_info=True)

        await db_execute(
            """INSERT OR REPLACE INTO command_cooldowns (chat_id, user_id, command_name, last_used_timestamp)
               VALUES (?, ?, ?, ?)""",
            (chat_id, user_id, command_name, now_dt.isoformat()),
        )
        return True
    except Exception as e:
        logger.error(f"Error in command_cooldown_check_and_update: {e}", exc_info=True)
        return True

async def _is_user_group_admin_or_creator(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    check_creator_only: bool = False,
) -> bool:
    if SUPER_ADMINS_ARE_GLOBAL_ADMINS and user_id in AUTHORIZED_USERS:
        return True
    if chat_id > 0:
        return False

    admin_ids = await get_cached_admins(context, chat_id)
    if user_id in admin_ids:
        if not check_creator_only:
            return True
        try:
            member = await get_chat_member_mb(context.bot, chat_id, user_id)
            return member is not None and member.status == ChatMemberStatus.OWNER
        except Exception:
            logger.warning(f"Failed to get chat member {user_id} for creator check in chat {chat_id}.")
            return False
    return False

async def take_action(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    reasons: List[str],
    sender_trigger_type: str | None,
    problematic_mentions_list: List[Tuple[str, int, str | None]],
):
    chat = update.effective_chat
    sender = update.effective_user
    message = update.effective_message

    if not chat or not sender or not message:
        logger.error("take_action called without chat, sender, or message.")
        return

    sender_html_mention = sender.mention_html() if hasattr(sender, "mention_html") else f"@{sender.username or sender.id}"
    action_taken_on_sender_this_time = False
    actual_action_performed_on_sender: Optional[str] = None
    duration_seconds_for_sender_action: Optional[int] = None
    notified_users_in_group = set()

    try:
        if sender_trigger_type:
            is_globally_exempt = sender.id in settings.get("free_users", set())
            is_group_exempt = await is_user_exempt_in_group(chat.id, sender.id)
            if is_globally_exempt or is_group_exempt:
                logger.debug(f"Sender {sender.id} in chat {chat.id} is exempt. Skipping action.")
            else:
                debounce_key = f"punish_notification_{chat.id}_{sender.id}"
                if debounce_key in notification_debounce_cache:
                    logger.debug(await get_language_string(context, "ACTION_DEBOUNCED_SENDER", chat_id=chat.id, user_id=sender.id))
                else:
                    notification_debounce_cache[debounce_key] = True
                    group_action_on_sender = await get_group_punish_action(chat.id)
                    duration_seconds_sender = await get_group_punish_duration_for_trigger(chat.id, sender_trigger_type)
                    duration_seconds_for_sender_action = duration_seconds_sender

                    dialogue_list = await get_language_string(context, "BIO_LINK_DIALOGUES_LIST", chat_id=chat.id, user_id=sender.id)
                    if not isinstance(dialogue_list, list) or not dialogue_list:
                        dialogue_list = [await get_language_string(context, "MESSAGE_VIOLATION_REASON", chat_id=chat.id, user_id=sender.id, message_issue_type="content violation")]
                    dialogue_entry = random.choice(dialogue_list)
                    dialogue_text = dialogue_entry.get("english", str(dialogue_entry)) if isinstance(dialogue_entry, dict) else str(dialogue_entry)

                    reason_parts_display: List[str] = []
                    if sender_trigger_type == "profile":
                        reason_parts_display.append(await get_language_string(context, "NEW_USER_PROFILE_VIOLATION_REASON", chat_id=chat.id, user_id=sender.id, field="profile", issue_type=", ".join(reasons)))
                    elif sender_trigger_type == "message":
                        reason_parts_display.append(await get_language_string(context, "MESSAGE_VIOLATION_REASON", chat_id=chat.id, user_id=sender.id, message_issue_type=", ".join(reasons)))
                    elif sender_trigger_type == "mention_profile":
                        reason_parts_display.append(f"profile issue when mentioned: {', '.join(reasons)}")
                    elif sender_trigger_type == "bad_actor":
                        bad_actor_reason_pattern = await get_language_string(context, "SENDER_IS_BAD_ACTOR_REASON", chat_id=chat.id, user_id=sender.id)
                        bad_actor_reason_text = bad_actor_reason_pattern.get("english", next(iter(bad_actor_reason_pattern.values()), "known bad actor")) if isinstance(bad_actor_reason_pattern, dict) else str(bad_actor_reason_pattern)
                        reason_parts_display.append(bad_actor_reason_text)
                    else:
                        reason_parts_display.append(f"violation: {', '.join(reasons)}")
                    reason_detail_for_sender = "; ".join(reason_parts_display)

                    punishment_msg_sender_template = await get_language_string(context, "PUNISHMENT_MESSAGE_SENDER_ENGLISH", chat_id=chat.id, user_id=sender.id)

                    bot_can_act = False
                    bot_member = await get_chat_member_mb(context.bot, chat.id, context.bot.id)
                    if bot_member:
                        has_restrict_permission = getattr(bot_member, "can_restrict_members", False)
                        has_ban_permission = getattr(bot_member, "can_ban_members", False)
                        if group_action_on_sender == "ban" and has_ban_permission:
                            bot_can_act = True
                        elif group_action_on_sender == "kick" and has_ban_permission:
                            bot_can_act = True
                        elif group_action_on_sender == "mute" and has_restrict_permission:
                            bot_can_act = True

                    if not bot_can_act:
                        logger.warning(await get_language_string(context, "NO_PERMS_TO_ACT_SENDER", chat_id=chat.id, user_id=sender.id, action=group_action_on_sender))
                    else:
                        applied_at_iso = datetime.now(timezone.utc).isoformat()
                        expires_at_iso: Optional[str] = None

                        try:
                            if group_action_on_sender == "ban":
                                success = await ban_chat_member_mb(context.bot, chat.id, sender.id, revoke_messages=True)
                                if success:
                                    action_taken_on_sender_this_time = True
                                    actual_action_performed_on_sender = "ban"
                                    await db_execute(
                                        """INSERT OR REPLACE INTO bot_restrictions (user_id, chat_id, restriction_type, applied_at, expires_at, is_active, reason, applied_by_admin_id)
                                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                           ON CONFLICT(user_id, chat_id, restriction_type, is_active) WHERE is_active = 1 DO UPDATE SET
                                           applied_at = excluded.applied_at, expires_at = excluded.expires_at, reason = excluded.reason, applied_by_admin_id = excluded.applied_by_admin_id""",
                                        (sender.id, chat.id, "ban", applied_at_iso, None, 1, reason_detail_for_sender[:1000], context.bot.id),
                                    )
                                    logger.info(f"Bot banned user {sender.id} in chat {chat.id} due to {reason_detail_for_sender[:100]}.")

                            elif group_action_on_sender == "kick":
                                ban_success = await ban_chat_member_mb(context.bot, chat.id, sender.id)
                                if ban_success:
                                    await asyncio.sleep(0.5)
                                    unban_success = await unban_chat_member_mb(context.bot, chat.id, sender.id, only_if_banned=True)
                                    if unban_success:
                                        action_taken_on_sender_this_time = True
                                        actual_action_performed_on_sender = "kick"
                                        logger.info(f"Bot kicked user {sender.id} in chat {chat.id} due to {reason_detail_for_sender[:100]}.")
                                    else:
                                        logger.warning(f"Bot banned user {sender.id} in chat {chat.id} but failed to unban after kick attempt.")
                                else:
                                    logger.warning(f"Bot failed to ban user {sender.id} in chat {chat.id} during kick attempt.")

                            else:
                                until_date_sender = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds_sender) if duration_seconds_sender > 0 else None
                                if duration_seconds_sender > 0:
                                    expires_at_iso = until_date_sender.isoformat()
                                success = await restrict_chat_member_mb(context.bot, chat.id, sender.id, mute_permissions_obj, until_date=until_date_sender)
                                if success:
                                    action_taken_on_sender_this_time = True
                                    actual_action_performed_on_sender = "mute"
                                    await db_execute(
                                        """INSERT OR REPLACE INTO bot_restrictions (user_id, chat_id, restriction_type, applied_at, expires_at, is_active, reason, applied_by_admin_id)
                                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                           ON CONFLICT(user_id, chat_id, restriction_type, is_active) WHERE is_active = 1 DO UPDATE SET
                                           applied_at = excluded.applied_at, expires_at = excluded.expires_at, reason = excluded.reason, applied_by_admin_id = excluded.applied_by_admin_id""",
                                        (sender.id, chat.id, "mute", applied_at_iso, expires_at_iso, 1, reason_detail_for_sender[:1000], context.bot.id),
                                    )
                                    logger.info(f"Bot muted user {sender.id} in chat {chat.id} for {duration_seconds_sender}s due to {reason_detail_for_sender[:100]}.")

                            if action_taken_on_sender_this_time and actual_action_performed_on_sender:
                                await log_action_db(
                                    context,
                                    actual_action_performed_on_sender.capitalize(),
                                    sender.id,
                                    chat.id,
                                    reason_detail_for_sender,
                                    duration_seconds_for_sender_action,
                                    context.bot.id,
                                )

                                punishment_msg_sender_display = await get_language_string(
                                    context,
                                    "PUNISHMENT_MESSAGE_SENDER_ENGLISH",
                                    chat_id=chat.id,
                                    user_id=sender.id,
                                    user_mention=sender_html_mention,
                                    action_taken=actual_action_performed_on_sender.capitalize(),
                                    reason_detail=reason_detail_for_sender,
                                    dialogue=dialogue_text,
                                )

                                if actual_action_performed_on_sender == "mute" and duration_seconds_for_sender_action and duration_seconds_for_sender_action > 0:
                                    punishment_msg_sender_display += await get_language_string(
                                        context,
                                        "PUNISHMENT_DURATION_APPEND",
                                        chat_id=chat.id,
                                        user_id=sender.id,
                                        duration=format_duration(duration_seconds_for_sender_action),
                                    )

                                reply_markup = None
                                if actual_action_performed_on_sender == "mute" and duration_seconds_for_sender_action and duration_seconds_for_sender_action > 0:
                                    unmute_me_button_text = await get_language_string(context, "UNMUTE_ME_BUTTON_TEXT", chat_id=chat.id, user_id=sender.id)
                                    bot_username = await get_bot_username(context) or "your_bot"
                                    start_payload = f"unmuteme_{chat.id}"
                                    button_url = f"https://t.me/{bot_username}?start={start_payload}"
                                    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(unmute_me_button_text, url=button_url)]])

                                await send_message_safe(
                                    context,
                                    chat.id,
                                    punishment_msg_sender_display,
                                    parse_mode=ParseMode.HTML,
                                    reply_to_message_id=message.message_id if message else None,
                                    reply_markup=reply_markup,
                                )
                                notified_users_in_group.add(sender.id)
                        except Forbidden:
                            logger.error(await get_language_string(context, "NO_PERMS_TO_ACT_SENDER", chat_id=chat.id, user_id=sender.id, action=group_action_on_sender))
                        except BadRequest as e:
                            logger.error(await get_language_string(context, "BADREQUEST_TO_ACT_SENDER", chat_id=chat.id, user_id=sender.id, action=group_action_on_sender, e=e))
                        except Exception as e:
                            logger.error(await get_language_string(context, "ERROR_ACTING_SENDER", chat_id=chat.id, user_id=sender.id, action=group_action_on_sender, e=e), exc_info=True)

        if problematic_mentions_list:
            mention_action_on_user = "mute"
            duration_seconds_mention = await get_group_punish_duration_for_trigger(chat.id, "mention_profile")

            bot_can_restrict = False
            try:
                bot_member = await get_chat_member_mb(context.bot, chat.id, context.bot.id)
                if bot_member:
                    bot_can_restrict = getattr(bot_member, "can_restrict_members", False)
            except Exception:
                logger.error(f"Failed to get bot member status in {chat.id} for mention actions.")
                bot_can_restrict = False

            if not bot_can_restrict:
                logger.warning(await get_language_string(context, "NO_PERMS_TO_ACT_MENTION", chat_id=chat.id, user_id=None, username="[any]"))
            else:
                muted_mentioned_display_list: List[str] = []

                for p_uname, p_uid, p_issue_type in problematic_mentions_list:
                    if p_uid == sender.id and action_taken_on_sender_this_time:
                        logger.debug(f"Skipping action on mentioned user {p_uid} in chat {chat.id} as they are the sender and already actioned.")
                        continue

                    is_globally_exempt_mention = p_uid in settings.get("free_users", set())
                    is_group_exempt_mention = await is_user_exempt_in_group(chat.id, p_uid)
                    if is_globally_exempt_mention or is_group_exempt_mention:
                        logger.debug(f"Mentioned user {p_uid} in chat {chat.id} is exempt. Skipping action.")
                        continue

                    mention_debounce_key = f"punish_notification_{chat.id}_{p_uid}_mention"
                    if mention_debounce_key in notification_debounce_cache:
                        logger.debug(await get_language_string(context, "ACTION_DEBOUNCED_MENTION", chat_id=chat.id, user_id=p_uid))
                        continue
                    notification_debounce_cache[mention_debounce_key] = True

                    applied_at_iso_mention = datetime.now(timezone.utc).isoformat()
                    expires_at_iso_mention: Optional[str] = None
                    until_date_mention = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds_mention) if duration_seconds_mention > 0 else None
                    if duration_seconds_mention > 0:
                        expires_at_iso_mention = until_date_mention.isoformat()

                    try:
                        success = await restrict_chat_member_mb(context.bot, chat.id, p_uid, mute_permissions_obj, until_date=until_date_mention)
                        if success:
                            mention_reason = f"Profile issue ({p_issue_type or 'unknown'}) when mentioned by {sender.id}"
                            await db_execute(
                                """INSERT OR REPLACE INTO bot_restrictions (user_id, chat_id, restriction_type, applied_at, expires_at, is_active, reason, applied_by_admin_id)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                   ON CONFLICT(user_id, chat_id, restriction_type, is_active) WHERE is_active = 1 DO UPDATE SET
                                   applied_at = excluded.applied_at, expires_at = excluded.expires_at, reason = excluded.reason, applied_by_admin_id = excluded.applied_by_admin_id""",
                                (p_uid, chat.id, "mute", applied_at_iso_mention, expires_at_iso_mention, 1, mention_reason[:1000], context.bot.id),
                            )
                            await log_action_db(context, "Mute (Mentioned)", p_uid, chat.id, mention_reason, duration_seconds_mention, context.bot.id)
                            mentioned_user_mention = f"@{p_uname}" if p_uname else f"User ID {p_uid}"
                            muted_mentioned_display_list.append(mentioned_user_mention)
                            logger.info(f"Bot muted mentioned user {p_uid} in chat {chat.id} for {duration_seconds_mention}s due to profile issue.")
                    except Forbidden:
                        logger.warning(await get_language_string(context, "NO_PERMS_TO_ACT_MENTION", chat_id=chat.id, user_id=p_uid, username=p_uname))
                    except BadRequest as e:
                        if "user not found" in str(e).lower() or "member not found" in str(e).lower():
                            logger.debug(f"Mentioned user @{p_uname} ({p_uid}) not in group {chat.id}. Cannot mute.")
                        else:
                            logger.warning(await get_language_string(context, "BADREQUEST_TO_ACT_MENTION", chat_id=chat.id, user_id=p_uid, username=p_uname, e=e))
                    except Exception as e:
                        logger.error(await get_language_string(context, "ERROR_ACTING_MENTION", chat_id=chat.id, user_id=p_uid, username=p_uname, e=e), exc_info=True)

                if muted_mentioned_display_list and sender.id not in notified_users_in_group:
                    muted_list_str = ", ".join(muted_mentioned_display_list)
                    mention_punishment_msg = await get_language_string(context, "PUNISHMENT_MESSAGE_MENTIONED", chat_id=chat.id, user_list=muted_list_str, duration=format_duration(duration_seconds_mention))
                    await send_message_safe(context, chat.id, mention_punishment_msg, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Unexpected error in take_action: {e}", exc_info=True)

async def get_bot_username(context: Optional[ContextTypes.DEFAULT_TYPE]) -> str | None:
    global bot_username_cache
    if bot_username_cache:
        return bot_username_cache
    try:
        bot = context.bot if context else None
        if not bot:
            logger.error("No bot instance available to fetch username.")
            return None
        bot_chat = await get_chat_mb(bot, bot.id)
        if bot_chat and bot_chat.username:
            bot_username_cache = bot_chat.username
            return bot_username_cache
        logger.error("Failed to fetch primary bot username.")
        return None
    except Exception as e:
        logger.error(f"Error getting primary bot username: {e}", exc_info=True)
        return None

async def log_action_db(
    context: ContextTypes.DEFAULT_TYPE,
    action_type: str,
    target_user_id: int,
    chat_id: int,
    reason: str,
    duration_seconds: Optional[int] = None,
    sender_user_id: Optional[int] = None,
):
    logger = logging.getLogger(__name__)
    try:
        timestamp_iso = datetime.now(timezone.utc).isoformat()
        await db_execute(
            """INSERT INTO observed_admin_actions (chat_id, sender_user_id, command_text, timestamp, detected_action_type, target_user_id, duration_seconds, parsed_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (chat_id, sender_user_id, f"Bot Action: {action_type}", timestamp_iso, action_type.lower(), target_user_id, duration_seconds, reason[:1000]),
        )
        logger.debug(f"Logged bot action '{action_type}' for user {target_user_id} in chat {chat_id}.")
    except Exception as e:
        logger.error(f"DB error logging action: {e}", exc_info=True)
        
def feature_controlled(feature_name: str):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            global MAINTENANCE_MODE
            if MAINTENANCE_MODE and feature_name not in {"start", "status"}:
                user = update.effective_user
                chat = update.effective_chat
                if user and chat and not await _is_super_admin(user.id):
                    await send_message_safe(
                        context,
                        chat.id,
                        await get_language_string(context, "MAINTENANCE_MODE_ACTIVE", chat_id=chat.id, user_id=user.id),
                    )
                    return
            try:
                is_enabled = await get_feature_state(feature_name, default=True)
                if not is_enabled:
                    user = update.effective_user
                    chat = update.effective_chat
                    if user and chat:
                        await send_message_safe(context, chat.id, f"Feature '{feature_name}' is disabled.")
                    return
                return await func(update, context, *args, **kwargs)
            except Exception as e:
                logger.error(f"Error in feature_controlled decorator for {feature_name}: {e}", exc_info=True)
                return
        return wrapper
    return decorator

async def _is_super_admin(user_id: int) -> bool:
    return user_id in AUTHORIZED_USERS

async def send_message_safe(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, **kwargs) -> Optional[TGMessage]:
    if not text:
        logger.warning(f"Attempted to send empty message to {chat_id}.")
        return None
    if context.bot is None:
        logger.error(f"Bot instance is None in send_message_safe for chat {chat_id}")
        return None
    try:
        return await send_message_safe_mb(context.bot, chat_id, text, **kwargs)
    except Exception as e:
        logger.error(f"send_message_safe failed for {chat_id}: {e}", exc_info=True)
        return None

async def send_message_safe_mb(initial_bot_instance: Any, chat_id: int, text: str, **kwargs) -> Optional[TGMessage]:
    if not text:
        logger.warning(f"Attempted to send empty message to {chat_id} via _mb.")
        return None
    def action_factory(bot_obj):
        return bot_obj.send_message(chat_id=chat_id, text=text, **kwargs)
    action_name = f"send_message({chat_id})"
    try:
        sent_message = await _execute_bot_action_mb(initial_bot_instance, action_factory, action_name)
        return sent_message
    except Forbidden as e:
        logger.warning(f"Bot forbidden to send to group {chat_id}: {e}")
        if chat_id < 0:
            asyncio.create_task(remove_group_from_db(chat_id))
        return None
    except BadRequest as e:
        logger.warning(f"Bad request sending to {chat_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to send message to {chat_id} via _mb: {e}", exc_info=True)
        return None

async def _execute_bot_action_mb(
    initial_bot_instance: Bot,
    action_coroutine_factory: Callable[[Bot], Any],
    action_name: str,
    max_retries_per_bot: int = 3,
    max_bot_fallbacks: Optional[int] = None,
    initial_bot_id_override: Optional[int] = None,
) -> Any:
    if not isinstance(initial_bot_instance, Bot):
        logger.error(f"Invalid bot instance for '{action_name}': {type(initial_bot_instance).__name__}")
        raise ValueError(f"Expected Bot instance, got {type(initial_bot_instance).__name__}")
    current_bot_obj = initial_bot_instance
    max_bot_fallbacks = max_bot_fallbacks or 1
    last_exception = None
    try:
        for bot_attempt in range(max_bot_fallbacks):
            logger.debug(f"Executing '{action_name}' with bot {current_bot_obj.id} (Attempt {bot_attempt + 1})")
            for retry_num in range(max_retries_per_bot):
                try:
                    result = await action_coroutine_factory(current_bot_obj)
                    logger.debug(f"Action '{action_name}' succeeded with bot {current_bot_obj.id}")
                    return result
                except RetryAfter as e_ra:
                    last_exception = e_ra
                    logger.warning(f"Bot {current_bot_obj.id} faced RetryAfter for '{action_name}' (wait {e_ra.retry_after}s).")
                    if retry_num < max_retries_per_bot - 1:
                        await asyncio.sleep(e_ra.retry_after + 0.1)
                except (TimedOut, NetworkError) as e_net:
                    last_exception = e_net
                    logger.warning(f"Bot {current_bot_obj.id} faced {type(e_net).__name__} for '{action_name}'.")
                    if retry_num < max_retries_per_bot - 1:
                        await asyncio.sleep(1 + retry_num * 2)
                except Forbidden as e_f:
                    logger.warning(f"Bot {current_bot_obj.id} faced Forbidden for '{action_name}': {e_f}")
                    raise
                except BadRequest as e_br:
                    logger.warning(f"Bot {current_bot_obj.id} faced BadRequest for '{action_name}': {e_br}")
                    raise
                except Exception as e:
                    last_exception = e
                    logger.error(f"Unexpected error for '{action_name}': {e}", exc_info=True)
                    break
            break
        if last_exception:
            logger.error(f"Action '{action_name}' failed: {type(last_exception).__name__}: {last_exception}")
            raise last_exception
        raise Exception(f"Action '{action_name}' failed after all retries")
    except Exception as e:
        logger.error(f"Error in _execute_bot_action_mb for '{action_name}': {e}", exc_info=True)
        raise

# Replace in main.py
async def get_language_string(
    context,
    key: str,
    chat_id: Optional[int] = None,
    user_id: Optional[int] = None,
    lang_code: Optional[str] = None,
    **format_kwargs
) -> str:
    logger = logging.getLogger(__name__)
    default_fallback = "⚠️ Missing string: {}"
    supported_langs = ["english", "hindi"]  # Match patterns.py languages

    # Determine language
    lang = lang_code or "english"
    if lang_code and lang_code not in supported_langs:
        logger.warning(f"Invalid language code '{lang_code}' for key '{key}'. Using English.")
        lang = "english"
    
    if not lang_code:
        try:
            if chat_id:
                row = await db_fetchone("SELECT language_code FROM groups WHERE group_id = ?", (chat_id,))
                lang = row["language_code"] if row and row["language_code"] else "english"
            elif user_id:
                row = await db_fetchone("SELECT language_code FROM users WHERE user_id = ?", (user_id,))
                lang = row["language_code"] if row and row["language_code"] else "english"
        except Exception as e:
            logger.error(f"Failed to fetch language for key '{key}': {e}")
            lang = "english"

    # Get template from patterns.py
    from patterns import LANGUAGE_STRINGS
    template = LANGUAGE_STRINGS.get(key)
    if isinstance(template, dict):
        template = template.get(lang, template.get("english", default_fallback.format(key)))
    elif isinstance(template, str):
        pass
    else:
        logger.warning(f"Invalid format for '{key}' in LANGUAGE_STRINGS. Using fallback.")
        template = default_fallback.format(key)

    # Format the string
    try:
        return template.format(**format_kwargs)
    except KeyError as e:
        logger.error(f"Missing format key {e} for '{key}' in lang '{lang}'. Kwargs: {format_kwargs}")
        return template
    except Exception as e:
        logger.error(f"Error formatting '{key}' in lang '{lang}': {e}")
        return template
        
async def _execute_broadcast(
    context: ContextTypes.DEFAULT_TYPE,
    message_text: str,
    target_type: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    job_name_for_log: str = "ManualBroadcast",
    target_id: Optional[int] = None,
) -> Tuple[int, int]:
    """Helper to execute broadcast messages to target users or groups."""
    sent_count = 0
    failed_count = 0
    target_list: List[int] = []

    if target_type == "all_users":
        # Get all users who have started the bot
        target_list = await get_all_users_from_db(started_only=True)
        logger.info(f"Broadcasting '{job_name_for_log}' to {len(target_list)} users...")
    elif target_type == "all_groups":
        # Get all groups the bot is in (from DB)
        target_list = await get_all_groups_from_db()
        logger.info(f"Broadcasting '{job_name_for_log}' to {len(target_list)} groups...")
    elif target_type == "specific_group" and target_id:
        target_list = [target_id]
        logger.info(f"Broadcasting '{job_name_for_log}' to specific group {target_id}...")
    elif target_type == "specific_user" and target_id:
        target_list = [target_id]
        logger.info(f"Broadcasting '{job_name_for_log}' to specific user {target_id}...")
    else:
        logger.warning(f"Unknown broadcast target type '{target_type}' or missing target_id.")
        return 0, 0

    for target in target_list:
        try:
            # Use send_message_safe (which will use the multi-bot version later)
            message_sent = await send_message_safe(
                context,
                target,
                message_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            if message_sent:
                sent_count += 1
            else:
                failed_count += 1  # send_message_safe returns None on failure
        except Exception as e:
            logger.warning(f"Failed to send broadcast message to {target} ({target_type}): {e}")
            failed_count += 1
        await asyncio.sleep(BROADCAST_SLEEP_INTERVAL)  # Delay between messages

    logger.info(f"Broadcast '{job_name_for_log}' completed. Sent: {sent_count}, Failed: {failed_count}.")
    return sent_count, failed_count


# Placeholder for timed_broadcast_job_callback - used by JobQueue (Part 8)
# This callback needs to execute the broadcast logic.
async def timed_broadcast_job_callback(context: ContextTypes.DEFAULT_TYPE):
    """Callback function executed by the JobQueue for timed broadcasts."""
    job = context.job
    if not job or not job.data:
        logger.error("Timed broadcast job called with no job or data.")
        return

    job_data = job.data
    job_name = job.name  # Use job name for logging

    target_type = job_data.get("target_type")
    message_text = job_data.get("message_text")
    markup_json = job_data.get("markup_json")
    target_id = job_data.get("target_id")  # For specific targets

    if not target_type or not message_text:
        logger.error(f"Timed broadcast job '{job_name}' missing target_type or message_text.")
        return

    reply_markup = None
    if markup_json:
        try:
            markup_dict = json.loads(markup_json)
            # Manually reconstruct InlineKeyboardMarkup from dict structure
            # The structure expected is a list of lists of dicts
            # Example: [[{'text': 'Button Text', 'url': '...'}]]
            inline_keyboard = []
            for row in markup_dict.get("inline_keyboard", []):
                button_row = []
                for button_data in row:
                    # Check for 'text' key
                    text = button_data.get("text")
                    if not text:
                        continue  # Skip buttons without text

                    # Handle different button types - simplified for url/callback_data
                    if "url" in button_data:
                        button_row.append(InlineKeyboardButton(text, url=button_data["url"]))
                    elif "callback_data" in button_data:
                        button_row.append(InlineKeyboardButton(text, callback_data=button_data["callback_data"]))
                    # Add other types like login_url, switch_inline_query etc if needed
                if button_row:
                    inline_keyboard.append(button_row)

            if inline_keyboard:
                reply_markup = InlineKeyboardMarkup(inline_keyboard)
            else:
                logger.warning(f"Timed broadcast job '{job_name}' had markup_json but could not reconstruct keyboard.")

        except json.JSONDecodeError:
            logger.error(f"Timed broadcast job '{job_name}' failed to decode markup_json.")
        except Exception as e:
            logger.error(f"Timed broadcast job '{job_name}' error reconstructing markup: {e}")

    logger.info(f"Executing timed broadcast job '{job_name}' to {target_type}...")
    sent, failed = await _execute_broadcast(
        context,
        message_text,
        target_type,
        reply_markup=reply_markup,
        job_name_for_log=job_name,
        target_id=target_id,
    )
    logger.info(f"Timed broadcast job '{job_name}' completed. Sent: {sent}, Failed: {failed}.")

    # Update next_run_time in DB? The JobQueue handles scheduling, DB only stores config.
    # The initial loading in main() sets the 'first' run time. JobQueue manages subsequent runs.
    # If the bot restarts, main() loads the job from DB with its interval and next_run_time (if stored)
    # It seems the current implementation just stores the config, and JobQueue handles the loop.
    # If next_run_time was updated in DB, upon restart, JobQueue would schedule 'first' based on that.
    # The current code stores 'next_run_time' in DB but doesn't update it in the job callback.
    # Let's assume storing it initially and relying on JobQueue's internal state is the intent.


# Handlers for various commands and updates
# Need to define these or ensure they are included in chunks

# Example: New Chat Members Handler - defined in Part 2's logic block, but here's its placement conceptually
# async def new_chat_members_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): ...

# Example: Handle Observed Admin Message Handler - defined in Part 2's logic block, uses parse_admin_command (Part 7)
# async def handle_observed_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE): ...

# Example: Deactivate Expired Restrictions Job - defined in Part 2's logic block
# async def deactivate_expired_restrictions_job(context: ContextTypes.DEFAULT_TYPE): ...

# --- Unmute Me Command and Button Handlers ---


@feature_controlled("unmuteme")
async def unmute_me_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /unmuteme [group_id_or_name] command."""
    user = update.effective_user
    chat = update.effective_chat  # Chat where command was used (can be PM or group)
    command_name = "unmuteme"

    if not user:
        return

    # Rate limit check (per user, global for this command, not per chat)
    # Using user.id as chat_id for global commands context
    cooldown_chat_id_context = user.id

    # Check cooldown using a generic command name for all /unmuteme attempts to avoid bypass
    # command_cooldown_check_and_update now takes context
    if not await command_cooldown_check_and_update(
            context,
            cooldown_chat_id_context,
            user.id,
            "unmuteme_cmd_global",
            UNMUTE_ME_RATE_LIMIT_SECONDS,
    ):
        # command_cooldown_check_and_update now sends the message internally if in a chat.
        # For PM, send explicitly here if the check function didn't send one.
        if chat.type == TGChat.PRIVATE:
            remaining_cooldown = (
                UNMUTE_ME_RATE_LIMIT_SECONDS  # Simplified, actual remaining time harder
            )
            await send_message_safe(
                context,
                user.id,
                await get_language_string(
                    context,
                    "UNMUTE_ME_RATE_LIMITED_PM",
                    user_id=user.id,
                    wait_duration=format_duration(remaining_cooldown),
                ),
            )  # Needs precise duration from cooldown func

        return  # On cooldown

    if not context.args:
        # Need to send usage info
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(context, "UNMUTE_ME_CMD_USAGE", user_id=user.id),
        )
        return

    group_identifier = " ".join(context.args)
    target_chat_id: Optional[int] = None
    target_chat_title: Optional[str] = None

    # Attempt to resolve group identifier
    if group_identifier.lstrip("-").isdigit():
        target_chat_id = int(group_identifier)
        # Use get_chat_mb to get chat info with fallback
        group_chat = await get_chat_mb(context.bot, target_chat_id)  # Use _mb version
        if group_chat:
            target_chat_title = group_chat.title or f"Group ID {target_chat_id}"
        else:
            target_chat_title = f"Group ID {target_chat_id}"  # Fallback if API fails
            logger.warning(f"Could not fetch chat info for ID {target_chat_id} via _mb.")

    else:  # Try to find group by name (limited search in bot's DB)
        group_rows = await db_fetchall(
            "SELECT group_id, group_name FROM groups WHERE group_name LIKE ?",
            (f"%{group_identifier}%", ),
        )
        if len(group_rows) == 1:
            target_chat_id = group_rows[0]["group_id"]
            target_chat_title = group_rows[0]["group_name"]
        elif len(group_rows) > 1:
            possible_groups = "\n".join(
                [f"- {row['group_name']} (ID: <code>{row['group_id']}</code>)" for row in group_rows[:5]])
            await send_message_safe(
                context,
                chat.id if chat else user.id,
                await get_language_string(
                    context,
                    "UNMUTE_ME_MULTIPLE_GROUPS_FOUND",
                    user_id=user.id,
                    group_list=possible_groups,
                ),
                parse_mode=ParseMode.HTML,
            )
            return
        else:
            await send_message_safe(
                context,
                chat.id if chat else user.id,
                await get_language_string(
                    context,
                    "UNMUTE_ME_GROUP_NOT_FOUND",
                    user_id=user.id,
                    group_identifier=group_identifier,
                ),
            )
            return

    if not target_chat_id:  # Should be caught by above logic
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(
                context,
                "UNMUTE_ME_GROUP_NOT_FOUND",
                user_id=user.id,
                group_identifier=group_identifier,
            ),
        )
        return

    # Ensure bot is actually in the target group and has permissions (optional but good practice)
    # Get bot's own member status in the target chat
    try:
        bot_member_in_target_chat = await get_chat_member_mb(context.bot, target_chat_id, context.bot.id)  # Use _mb
        if not bot_member_in_target_chat or bot_member_in_target_chat.status not in [
                ChatMemberStatus.MEMBER,
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.OWNER,
        ]:
            await send_message_safe(
                context,
                chat.id if chat else user.id,
                await get_language_string(
                    context,
                    "UNMUTE_ME_BOT_NOT_IN_GROUP",
                    user_id=user.id,
                    group_name=target_chat_title,
                ),
            )  # Need pattern
            return
        if bot_member_in_target_chat.status != ChatMemberStatus.OWNER and not getattr(
                bot_member_in_target_chat, "can_restrict_members", False):
            await send_message_safe(
                context,
                chat.id if chat else user.id,
                await get_language_string(
                    context,
                    "UNMUTE_ME_BOT_NO_PERMS",
                    user_id=user.id,
                    group_name=target_chat_title,
                ),
            )  # Need pattern
            return
    except Exception as e:
        logger.error(f"Error checking bot status in target group {target_chat_id} for /unmuteme: {e}")
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(
                context,
                "UNMUTE_ME_BOT_CHECK_FAIL",
                user_id=user.id,
                group_name=target_chat_title,
            ),
        )  # Need pattern
        return

    # Check profile issues first (uses user_has_links_cached which uses get_chat_mb)
    has_profile_issue, problematic_field, _ = await user_has_links_cached(context, user.id)
    if has_profile_issue:
        # Send the message to the user in PM, even if command was in group
        await send_message_safe(
            context,
            user.id,
            await get_language_string(
                context,
                "UNMUTE_ME_PROFILE_ISSUE_PM",
                user_id=user.id,
                field=problematic_field or "unknown",
            ),
        )
        # If in a group, send a short confirmation there too
        if chat.type != TGChat.PRIVATE:
            await send_message_safe(
                context,
                chat.id,
                await get_language_string(
                    context,
                    "UNMUTE_ME_PROFILE_ISSUE_GROUP_SHORT",
                    chat_id=chat.id,
                    user_id=user.id,
                ),
            )  # Need pattern
        return

    # Check channel subscription if required (uses is_user_subscribed which uses get_chat_mb/get_chat_member_mb)
    if settings.get("channel_id"):
        # Pass target_chat_id for potential guidance link context
        is_subbed = await is_user_subscribed(context, user.id, chat_id_for_pm_guidance=target_chat_id)
        if not is_subbed:
            channel_link = (settings.get("channel_invite_link") or f"Channel ID: {settings.get('channel_id')}")
            # Send the message to the user in PM
            await send_message_safe(
                context,
                user.id,
                await get_language_string(
                    context,
                    "UNMUTE_ME_CHANNEL_ISSUE_PM",
                    user_id=user.id,
                    channel_link=channel_link,
                ),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            # If in a group, send a short confirmation there too
            if chat.type != TGChat.PRIVATE:
                await send_message_safe(
                    context,
                    chat.id,
                    await get_language_string(
                        context,
                        "UNMUTE_ME_CHANNEL_ISSUE_GROUP_SHORT",
                        chat_id=chat.id,
                        user_id=user.id,
                    ),
                )  # Need pattern
            return

    # Check if user is muted by this bot in that specific group
    restriction = await db_fetchone(
        "SELECT id FROM bot_restrictions WHERE user_id = ? AND chat_id = ? AND restriction_type = 'mute' AND is_active = 1 AND applied_by_admin_id = ?",
        (
            user.id,
            target_chat_id,
            context.bot.id,
        ),  # Crucially check if muted *by this bot instance*
    )

    if not restriction:
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(
                context,
                "UNMUTE_ME_FAIL_GROUP_CMD_NO_MUTE",
                user_id=user.id,
                group_name=target_chat_title,
            ),
        )
        return

    try:
        # Use restrict_chat_member_mb to unmute
        # unmute_permissions object is defined globally
        success = await restrict_chat_member_mb(context.bot, target_chat_id, user.id,
                                                permissions=unmute_permissions)  # Use _mb version
        if success:
            await db_execute(
                "UPDATE bot_restrictions SET is_active = 0 WHERE id = ?",
                (restriction["id"], ),
            )
            # Send success message to user in PM
            await send_message_safe(
                context,
                user.id,
                await get_language_string(
                    context,
                    "UNMUTE_ME_SUCCESS_GROUP_CMD",
                    user_id=user.id,
                    group_name=target_chat_title,
                ),
            )
            logger.info(
                f"User {user.id} successfully unmuted themselves in group {target_chat_id} via /unmuteme command.")
            # Try to notify in group as well (use the chat where the command was issued if group, otherwise PM)
            group_notification_chat_id = (chat.id if chat.type != TGChat.PRIVATE else target_chat_id
                                          )  # Notify in the target group if command was PM
            await send_message_safe(
                context,
                group_notification_chat_id,
                await get_language_string(
                    context,
                    "UNMUTE_SUCCESS_MESSAGE_GROUP",
                    chat_id=target_chat_id,
                    user_mention=user.mention_html(),
                ),
                parse_mode=ParseMode.HTML,
            )
        else:
            # restrict_chat_member_mb failed after retries/fallbacks
            logger.error(
                f"Failed to unmute user {user.id} in group {target_chat_id} via _mb call during /unmuteme command.")
            await send_message_safe(
                context,
                chat.id if chat else user.id,
                await get_language_string(
                    context,
                    "UNMUTE_ME_FAIL_GROUP_CMD_OTHER",
                    user_id=user.id,
                    group_name=target_chat_title,
                    error="API call failed.",
                ),
            )

    except Exception as e:  # Catch any unexpected errors not handled by _mb wrappers
        logger.error(
            f"Unexpected error during /unmuteme for user {user.id} in group {target_chat_id}: {e}",
            exc_info=True,
        )
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(
                context,
                "UNMUTE_ME_FAIL_GROUP_CMD_OTHER",
                user_id=user.id,
                group_name=target_chat_title,
                error=str(e),
            ),
        )


async def handle_unmute_me_button_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles 'Unmute Me From All Bot Mutes' button from /start."""
    query = update.callback_query
    user = query.from_user
    command_name = "unmuteme_button_all"

    if not user or not query:
        return
    await query.answer(await get_language_string(context, "PROCESSING_REQUEST_SHORT",
                                                 user_id=user.id))  # Acknowledge button press - Need pattern

    # Rate limit check (per user, global context)
    cooldown_chat_id_context = user.id  # Use user.id as chat_id for global context

    # command_cooldown_check_and_update now takes context
    if not await command_cooldown_check_and_update(
            context,
            cooldown_chat_id_context,
            user.id,
            command_name,
            UNMUTE_ME_RATE_LIMIT_SECONDS,
    ):
        # The cooldown check function does not send message for callback queries.
        # Send rate limited message as an edit or new message in PM.
        remaining_cooldown = UNMUTE_ME_RATE_LIMIT_SECONDS  # Simplified
        message_text = await get_language_string(
            context,
            "UNMUTE_ME_RATE_LIMITED_PM",
            user_id=user.id,
            wait_duration=format_duration(remaining_cooldown),
        )  # Needs precise duration

        # Use edit_message_text_mb
        await edit_message_text_mb(
            context.bot,
            text=message_text,
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            reply_markup=query.message.reply_markup if query.message else None,
        )
        return

    # Check profile issues (uses user_has_links_cached which uses get_chat_mb)
    has_profile_issue, problematic_field, _ = await user_has_links_cached(context, user.id)
    if has_profile_issue:
        message_text = await get_language_string(
            context,
            "UNMUTE_ME_PROFILE_ISSUE_PM",
            user_id=user.id,
            field=problematic_field or "unknown",
        )
        await edit_message_text_mb(
            context.bot,
            text=message_text,
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            reply_markup=query.message.reply_markup if query.message else None,
        )  # Keep buttons for retry
        return

    # Check channel subscription (uses is_user_subscribed which uses get_chat_mb/get_chat_member_mb)
    if settings.get("channel_id"):
        # Pass user.id for PM guidance context
        is_subbed = await is_user_subscribed(context, user.id, chat_id_for_pm_guidance=user.id)
        if not is_subbed:
            channel_link = (settings.get("channel_invite_link") or f"Channel ID: {settings.get('channel_id')}")
            message_text = await get_language_string(
                context,
                "UNMUTE_ME_CHANNEL_ISSUE_PM",
                user_id=user.id,
                channel_link=channel_link,
            )
            await edit_message_text_mb(
                context.bot,
                text=message_text,
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=query.message.reply_markup if query.message else None,
            )  # Keep buttons for retry
            return

    # Find all active mutes by this bot for this user
    muted_in_chats = await db_fetchall(
        "SELECT id, chat_id FROM bot_restrictions WHERE user_id = ? AND restriction_type = 'mute' AND is_active = 1 AND applied_by_admin_id = ?",
        (user.id, context.bot.id),  # Crucially check if muted *by this bot instance*
    )

    if not muted_in_chats:
        message_text = await get_language_string(context, "UNMUTE_ME_NO_MUTES_FOUND_PM", user_id=user.id)
        await edit_message_text_mb(
            context.bot,
            text=message_text,
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            reply_markup=None,
        )  # Remove buttons
        return

    unmuted_in_count = 0
    failed_count = 0
    skipped_count = 0  # Not really skipped here, but helps match bulk op logic
    total_to_process = len(muted_in_chats)

    status_update_text = await get_language_string(
        context,
        "BULK_UNMUTE_STARTED_STATUS",  # Re-use pattern
        user_id=user.id,  # Lang context
        operation_type="unmute",
        group_id_display="various groups",  # Placeholder for global op
        target_count=total_to_process,
        target_bot_mutes_only=True,
    )  # Always true for this button

    # Use edit_message_text_mb for status update
    await edit_message_text_mb(
        context.bot,
        text=status_update_text,
        chat_id=query.message.chat_id,
        message_id=query.message.message_id,
        reply_markup=None,
    )  # Remove initial buttons

    logger.info(f"User {user.id} attempting global unmute from {total_to_process} groups via button.")

    for i, restriction_info in enumerate(muted_in_chats):
        chat_id_to_unmute = restriction_info["chat_id"]
        restriction_id = restriction_info["id"]

        # Need to check if bot still has permissions in this specific group *before* attempting API call
        try:
            bot_member_in_target_chat = await get_chat_member_mb(context.bot, chat_id_to_unmute,
                                                                 context.bot.id)  # Use _mb
            if (not bot_member_in_target_chat or bot_member_in_target_chat.status != ChatMemberStatus.ADMINISTRATOR or
                    not getattr(bot_member_in_target_chat, "can_restrict_members", False)):
                logger.warning(
                    f"Bot {context.bot.id} lacks restrict perms in {chat_id_to_unmute} for global unmute button.")
                failed_count += 1
                continue  # Skip this group if no perms
        except Exception:
            logger.warning(f"Could not check bot perms in {chat_id_to_unmute} for global unmute button.")
            failed_count += 1
            continue  # Skip on error

        try:
            # Use restrict_chat_member_mb to unmute
            # unmute_permissions object is defined globally
            success = await restrict_chat_member_mb(context.bot,
                                                    chat_id_to_unmute,
                                                    user.id,
                                                    permissions=unmute_permissions)  # Use _mb version
            if success:
                await db_execute(
                    "UPDATE bot_restrictions SET is_active = 0 WHERE id = ?",
                    (restriction_id, ),
                )
                unmuted_in_count += 1
                logger.info(f"User {user.id} unmuted in group {chat_id_to_unmute} via global unmute me button.")
                # Optionally send a confirmation to the group (can be spammy)
                # await send_message_safe(context, chat_id_to_unmute, f"{user.mention_html()} has been unmuted via self-service.", parse_mode=ParseMode.HTML)
            else:
                # restrict_chat_member_mb failed after retries/fallbacks
                logger.warning(
                    f"Failed to unmute user {user.id} in group {chat_id_to_unmute} via global unmute me (_mb failed).")
                failed_count += 1
        except (Exception) as e:  # Catch any unexpected errors not handled by _mb wrappers
            logger.warning(
                f"Unexpected error unmuting user {user.id} in group {chat_id_to_unmute} via global unmute me: {e}")
            failed_count += 1
        await asyncio.sleep(BROADCAST_SLEEP_INTERVAL)  # Rate limit API calls slightly

        # Update status message periodically using edit_message_text_mb
        if (i + 1) % 5 == 0 or (i + 1) == total_to_process:  # Update every 5 or on last
            progress_text = await get_language_string(
                context,
                "BULK_UNMUTE_PROGRESS",  # Re-use pattern
                user_id=user.id,  # Lang context
                processed_count=(i + 1),
                total_count=total_to_process,
                success_count=unmuted_in_count,
                fail_count=failed_count,
                skipped_count=skipped_count,
            )  # Skipped is 0 here

            await edit_message_text_mb(
                context.bot,
                text=status_update_text.split("\n")[0] + "\n" + progress_text,  # Keep the "Starting..." line
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
            )

    final_message = await get_language_string(
        context,
        "UNMUTE_ME_COMPLETED_PM",
        user_id=user.id,
        success_count=unmuted_in_count,
        fail_count=failed_count,
        total_count=total_to_process,
    )
    # Final status message using edit_message_text_mb
    await edit_message_text_mb(
        context.bot,
        text=final_message,
        chat_id=query.message.chat_id,
        message_id=query.message.message_id,
        reply_markup=None,
    )  # Remove buttons

    logger.info(
        f"Global unmute button for user {user.id} completed. Unmuted: {unmuted_in_count}, Failed: {failed_count}.")


# --- Language Command ---
# LANG_CALLBACK_PREFIX = "setlang_" # Defined in Part 1
# LANG_PAGE_SIZE = 6 # Defined in Part 1


@feature_controlled("lang")
async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /lang command to set language for the user or group."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    is_group_admin = False
    if chat.type != TGChat.PRIVATE:
        # Use _is_user_group_admin_or_creator which uses get_cached_admins (uses _mb)
        is_group_admin = await _is_user_group_admin_or_creator(context, chat.id, user.id)
        if not is_group_admin:
            await send_message_safe(
                context,
                chat.id,
                await get_language_string(
                    context,
                    "ADMIN_ONLY_COMMAND_MESSAGE",
                    chat_id=chat.id,
                    user_id=user.id,
                ),
            )
            return

    # Store context for pagination (target chat ID)
    # User data is per user, this is appropriate for PM or initiated-by-user command
    context.user_data["lang_target_chat_id"] = (chat.id)  # Store if it's for group or PM (user.id)

    await send_language_selection_page(update, context, page=0)


async def send_language_selection_page(
    update_or_query: Union[Update, CallbackQuery],
    context: ContextTypes.DEFAULT_TYPE,
    page: int,
):
    """Sends a paginated list of languages for selection."""
    # Determine source of the update (command or callback query)
    if isinstance(update_or_query, Update):
        effective_chat = update_or_query.effective_chat
        effective_user = update_or_query.effective_user
        message_to_edit = None  # No message to edit on first command
    elif isinstance(update_or_query, CallbackQuery):
        query = update_or_query
        effective_chat = query.message.chat if query.message else None
        effective_user = query.from_user
        message_to_edit = query.message
        await query.answer()  # Answer the callback query
    else:
        logger.error("send_language_selection_page called with invalid type.")
        return

    if not effective_chat or not effective_user:
        return  # Defensive check

    target_chat_id = context.user_data.get("lang_target_chat_id")
    if target_chat_id is None:  # Should not happen if lang_command set it
        logger.warning("lang_target_chat_id not found in user_data for language selection.")
        if effective_chat:  # Send error message if possible
            await send_message_safe(
                context,
                effective_chat.id,
                "Error: Could not determine chat for language setting. Please try /lang again.",
            )
        return

    lang_items = list(LANGUAGES.items())  # List of (code, info) tuples
    total_languages = len(lang_items)
    total_pages = (total_languages + LANG_PAGE_SIZE - 1) // LANG_PAGE_SIZE
    page = max(0, min(page, total_pages - 1))  # Clamp page number

    start_index = page * LANG_PAGE_SIZE
    end_index = start_index + LANG_PAGE_SIZE
    current_page_langs = lang_items[start_index:end_index]

    keyboard = []
    for lang_code, lang_info in current_page_langs:
        button_text = f"{lang_info.get('flag', '')} {lang_info.get('name', lang_code)}"  # Use .get for safety
        keyboard.append(
            [InlineKeyboardButton(
                button_text,
                callback_data=f"{LANG_CALLBACK_PREFIX}select_{lang_code}",
            )])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(
                await get_language_string(context, "LANG_BUTTON_PREV", user_id=effective_user.id),
                callback_data=f"{LANG_CALLBACK_PREFIX}page_{page-1}",
            ))
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(
                await get_language_string(context, "LANG_BUTTON_NEXT", user_id=effective_user.id),
                callback_data=f"{LANG_CALLBACK_PREFIX}page_{page+1}",
            ))
    if nav_buttons:
        keyboard.append(nav_buttons)

    # Add a placeholder button if needed
    # keyboard.append([InlineKeyboardButton(await get_language_string(context, 'LANG_MORE_COMING_SOON', user_id=effective_user.id), callback_data="noop_ignore")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    prompt_text = await get_language_string(context, "LANG_SELECT_PROMPT", user_id=effective_user.id)

    if message_to_edit:  # Editing existing message for pagination
        try:
            await edit_message_text_mb(
                context.bot,
                text=prompt_text,
                chat_id=message_to_edit.chat.id,
                message_id=message_to_edit.message_id,
                reply_markup=reply_markup,
            )  # Use _mb
        except BadRequest as e:  # Message not modified is common on page navigation
            if "Message is not modified" not in str(e):
                logger.error(f"Error editing language selection message via _mb: {e}")
        except Exception as e:
            logger.error(f"Unexpected error editing language selection message via _mb: {e}")

    else:  # Sending new message for /lang command
        await send_message_safe(context, target_chat_id, prompt_text,
                                reply_markup=reply_markup)  # Use send_message_safe (uses _mb)


# main.py (Add this new function)

# Make sure the following are imported or defined above this point:
# telegram.CallbackQuery, telegram.InlineKeyboardMarkup, telegram.InlineKeyboardButton
# telegram.constants.ParseMode, telegram.error.BadRequest, telegram.ChatPermissions
# TTLCache (used for debounce), datetime, timezone, timedelta, asyncio
# is_user_exempt_in_group, user_has_links_cached, is_user_subscribed, get_bot_username
# restrict_chat_member_mb, edit_message_text_mb, send_message_safe (which wraps _mb)
# db_fetchone, db_execute
# unmute_permissions (global ChatPermissions object)
# notification_debounce_cache (global TTLCache)

# Pattern for the callback data (e.g., "pmunmute_attempt_12345")
PM_UNMUTE_CALLBACK_PATTERN = r"^pmunmute_attempt_(-?\d+)$"


async def pm_unmute_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles callback queries for users attempting to unmute themselves from a specific group in PM."""
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat if query.message else None  # The user's private chat

    if not user or not query or not chat or chat.type != TGChat.PRIVATE:
        logger.warning(
            f"pm_unmute_callback_handler received invalid query from user {user.id if user else 'N/A'} in chat {chat.id if chat else 'N/A'}."
        )
        # Answer the query even if invalid
        await query.answer(await get_language_string(context, "INVALID_REQUEST_SHORT", user_id=user.id))  # Need pattern
        # Attempt to edit the message to show error if possible
        if query.message:
            try:
                await edit_message_text_mb(
                    context.bot,
                    text=await get_language_string(context, "INVALID_REQUEST_ERROR", user_id=user.id),
                    chat_id=chat.id,
                    message_id=query.message.message_id,
                    reply_markup=None,
                )
            except Exception:
                pass  # Ignore edit errors
        return

    # Acknowledge the button press immediately
    await query.answer(await get_language_string(context, "PROCESSING_REQUEST_SHORT", user_id=user.id))  # Need pattern

    logger.info(f"User {user.id} attempting PM unmute via callback: {query.data}")

    # Extract group_id from callback data using the defined pattern
    match = re.match(PM_UNMUTE_CALLBACK_PATTERN, query.data)
    if not match:
        logger.warning(f"Invalid callback data format for PM unmute: {query.data}")
        # Edit message to show error
        if query.message:
            try:
                await edit_message_text_mb(
                    context.bot,
                    text=await get_language_string(context, "INVALID_CALLBACK_DATA", user_id=user.id),
                    chat_id=chat.id,
                    message_id=query.message.message_id,
                    reply_markup=None,
                )  # Need pattern
            except Exception:
                pass
        return

    try:
        target_group_id = int(match.group(1))
    except ValueError:
        logger.error(f"Could not parse group_id from callback data: {query.data}")
        if query.message:
            try:
                await edit_message_text_mb(
                    context.bot,
                    text=await get_language_string(context, "INVALID_CALLBACK_DATA", user_id=user.id),
                    chat_id=chat.id,
                    message_id=query.message.message_id,
                    reply_markup=None,
                )
            except Exception:
                pass
        return

    # Debounce consecutive attempts for the same user/group
    debounce_key = f"pm_unmute_attempt_{user.id}_{target_group_id}"
    if (debounce_key in notification_debounce_cache):  # Re-using notification_debounce_cache
        logger.debug(f"PM unmute attempt for user {user.id} in group {target_group_id} debounced.")
        # Edit message to show rate limit
        remaining_cooldown = notification_debounce_cache.ttl - (
            time.time() - notification_debounce_cache.get_last_access(debounce_key))  # Approximate remaining time
        await edit_message_text_mb(
            context.bot,
            text=await get_language_string(
                context,
                "UNMUTE_ME_RATE_LIMITED_PM",
                user_id=user.id,
                wait_duration=format_duration(remaining_cooldown),
            ),
            chat_id=chat.id,
            message_id=query.message.message_id,
            reply_markup=query.message.reply_markup,
        )  # Keep buttons for retry
        return
    notification_debounce_cache[debounce_key] = (
        True  # Add to cache with its default TTL (30s)
    )

    # Check profile issues first (uses user_has_links_cached which uses get_chat_mb)
    has_profile_issue, problematic_field, _ = await user_has_links_cached(context,
                                                                          user.id)  # Use context from the query
    if has_profile_issue:
        message_text = await get_language_string(
            context,
            "UNMUTE_ME_PROFILE_ISSUE_PM",
            user_id=user.id,
            field=problematic_field or "unknown",
        )  # Use user's language context
        await edit_message_text_mb(
            context.bot,
            text=message_text,
            chat_id=chat.id,
            message_id=query.message.message_id,
            reply_markup=query.message.reply_markup,
        )  # Keep buttons for retry
        logger.info(f"PM unmute attempt failed for user {user.id} in group {target_group_id}: profile issue.")
        return

    # Check channel subscription if required (uses is_user_subscribed which uses get_chat_mb/get_chat_member_mb)
    if settings.get("channel_id"):
        # Pass user.id for PM guidance context
        is_subbed = await is_user_subscribed(context, user.id,
                                             chat_id_for_pm_guidance=user.id)  # Use user's PM chat for guidance
        if not is_subbed:
            channel_link = (settings.get("channel_invite_link") or f"Channel ID: {settings.get('channel_id')}")
            message_text = await get_language_string(
                context,
                "UNMUTE_ME_CHANNEL_ISSUE_PM",
                user_id=user.id,
                channel_link=channel_link,
            )  # Use user's language context
            await edit_message_text_mb(
                context.bot,
                text=message_text,
                chat_id=chat.id,
                message_id=query.message.message_id,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=query.message.reply_markup,
            )  # Keep buttons for retry
            logger.info(f"PM unmute attempt failed for user {user.id} in group {target_group_id}: channel not joined.")
            return

    # Check if user is currently muted by this bot instance in the target group according to the DB
    restriction = await db_fetchone(
        "SELECT id FROM bot_restrictions WHERE user_id = ? AND chat_id = ? AND restriction_type = 'mute' AND is_active = 1 AND applied_by_admin_id = ?",
        (
            user.id,
            target_group_id,
            context.bot.id,
        ),  # Crucially check if muted *by this bot instance*
    )

    if not restriction:
        # User is not muted by this bot in this group, or restriction expired/inactive
        group_title = f"Group ID {target_group_id}"  # Fallback title
        try:
            group_chat_info = await get_chat_mb(context.bot, target_group_id)  # Use _mb to get group title
            if group_chat_info and group_chat_info.title:
                group_title = group_chat_info.title
        except Exception:
            logger.debug(f"Could not fetch group info for ID {target_group_id} for PM unmute message.")

        message_text = await get_language_string(
            context,
            "UNMUTE_ME_FAIL_GROUP_CMD_NO_MUTE",
            user_id=user.id,
            group_name=group_title,
        )  # Re-use pattern, use user's lang context
        await edit_message_text_mb(
            context.bot,
            text=message_text,
            chat_id=chat.id,
            message_id=query.message.message_id,
            reply_markup=None,
        )  # Remove buttons
        logger.info(f"PM unmute attempt for user {user.id} in group {target_group_id}: not muted by this bot.")
        return

    # If all checks pass, attempt to unmute via API
    try:
        # Ensure bot is still in the group and has permissions
        bot_can_restrict = False
        try:
            bot_member_in_target_chat = await get_chat_member_mb(context.bot, target_group_id,
                                                                 context.bot.id)  # Use _mb
            if (bot_member_in_target_chat and bot_member_in_target_chat.status == ChatMemberStatus.ADMINISTRATOR and
                    getattr(bot_member_in_target_chat, "can_restrict_members", False)):
                bot_can_restrict = True
            elif (bot_member_in_target_chat and bot_member_in_target_chat.status == ChatMemberStatus.OWNER):
                bot_can_restrict = True  # Owner always has permissions
            else:
                logger.warning(
                    f"Bot {context.bot.id} lacks restrict perms or not admin/owner in {target_group_id} for PM unmute button."
                )
                # Edit message to show lack of bot perms
                group_title = f"Group ID {target_group_id}"  # Fallback title
                try:
                    group_chat_info = await get_chat_mb(context.bot, target_group_id)  # Use _mb
                    if group_chat_info and group_chat_info.title:
                        group_title = group_chat_info.title
                except Exception:
                    pass
                await edit_message_text_mb(
                    context.bot,
                    text=await get_language_string(
                        context,
                        "UNMUTE_ME_BOT_NO_PERMS",
                        user_id=user.id,
                        group_name=group_title,
                    ),  # Need pattern
                    chat_id=chat.id,
                    message_id=query.message.message_id,
                    reply_markup=None,
                )
                logger.info(
                    f"PM unmute attempt failed for user {user.id} in group {target_group_id}: bot lacks permissions.")
                return

        except Exception as e:
            logger.error(f"Error checking bot status in target group {target_group_id} for PM unmute: {e}")
            await edit_message_text_mb(
                context.bot,
                text=await get_language_string(
                    context,
                    "UNMUTE_ME_BOT_CHECK_FAIL",
                    user_id=user.id,
                    group_name=f"Group ID {target_group_id}",
                ),  # Need pattern
                chat_id=chat.id,
                message_id=query.message.message_id,
                reply_markup=None,
            )
            return

        # Use restrict_chat_member_mb to unmute
        # unmute_permissions object is defined globally (Part 1)
        success = await restrict_chat_member_mb(context.bot, target_group_id, user.id,
                                                permissions=unmute_permissions)  # Use _mb version

        group_title = f"Group ID {target_group_id}"  # Fallback title
        try:
            group_chat_info = await get_chat_mb(context.bot, target_group_id)  # Use _mb to get group title
            if group_chat_info and group_chat_info.title:
                group_title = group_chat_info.title
        except Exception:
            logger.debug(f"Could not fetch group info for ID {target_group_id} for PM unmute message.")

        if success:
            # Mark the restriction as inactive in the DB
            await db_execute(
                "UPDATE bot_restrictions SET is_active = 0 WHERE id = ?",
                (restriction["id"], ),
            )

            # Edit the message to show success
            message_text = await get_language_string(
                context,
                "UNMUTE_ME_SUCCESS_GROUP_CMD",
                user_id=user.id,
                group_name=group_title,
            )  # Re-use pattern, use user's lang context
            await edit_message_text_mb(
                context.bot,
                text=message_text,
                chat_id=chat.id,
                message_id=query.message.message_id,
                reply_markup=None,
            )  # Remove buttons

            logger.info(f"User {user.id} successfully unmuted themselves in group {target_group_id} via PM callback.")

            # Optional: Send a notification in the target group that the user unmuted themselves
            # This can be spammy in large groups. Make it optional?
            # For now, let's send it. Use send_message_safe with the target group ID.
            group_notification_text = await get_language_string(
                context,
                "UNMUTE_SUCCESS_MESSAGE_GROUP",
                chat_id=target_group_id,
                user_mention=user.mention_html(),
            )  # Use group's language context, re-use pattern
            await send_message_safe(
                context,
                target_group_id,
                group_notification_text,
                parse_mode=ParseMode.HTML,
            )

        else:
            # restrict_chat_member_mb failed after retries/fallbacks
            logger.error(f"Failed to unmute user {user.id} in group {target_group_id} via PM callback (_mb failed).")
            message_text = await get_language_string(
                context,
                "UNMUTE_ME_FAIL_GROUP_CMD_OTHER",
                user_id=user.id,
                group_name=group_title,
                error="API call failed.",
            )  # Re-use pattern, use user's lang context
            await edit_message_text_mb(
                context.bot,
                text=message_text,
                chat_id=chat.id,
                message_id=query.message.message_id,
                reply_markup=None,
            )  # Remove buttons

    except Exception as e:  # Catch any unexpected errors not handled by _mb wrappers
        logger.error(
            f"Unexpected error during PM unmute callback for user {user.id} in group {target_group_id}: {e}",
            exc_info=True,
        )
        group_title = f"Group ID {target_group_id}"  # Fallback title
        try:
            group_chat_info = await get_chat_mb(context.bot, target_group_id)  # Use _mb
            if group_chat_info and group_chat_info.title:
                group_title = group_chat_info.title
        except Exception:
            pass
        message_text = await get_language_string(
            context,
            "UNMUTE_ME_FAIL_GROUP_CMD_OTHER",
            user_id=user.id,
            group_name=group_title,
            error=str(e),
        )  # Re-use pattern, use user's lang context
        await edit_message_text_mb(
            context.bot,
            text=message_text,
            chat_id=chat.id,
            message_id=query.message.message_id,
            reply_markup=None,
        )  # Remove buttons

async def check_bot_permissions(bot: Bot, chat_id: int) -> bool:
    try:
        bot_member = await get_chat_member_mb(bot, chat_id, bot.id)
        return bot_member and bot_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception:
        return False

async def new_chat_members_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle new members joining a chat."""
    chat_id = update.effective_chat.id
    for member in update.message.new_chat_members:
        user_id = member.id
        if cache.get(f"processed_{chat_id}_{user_id}"):
            continue
        cache.set(f"processed_{chat_id}_{user_id}", True, ttl=3600)
        try:
            profile = await rate_limited_api_call(context.bot.get_chat_member, chat_id, user_id)
            if profile.user.bio and check_for_links_enhanced(profile.user.bio):
                await rate_limited_api_call(
                    context.bot.restrict_chat_member,
                    chat_id,
                    user_id,
                    permissions=mute_permissions_obj,
                )
                await db_execute(
                    """INSERT OR REPLACE INTO bot_restrictions (user_id, chat_id, restriction_type, applied_at, is_active, reason, applied_by_admin_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (user_id, chat_id, "mute", datetime.now(timezone.utc).isoformat(), 1, "Spammy bio", 0),
                )
                await send_message_safe(
                    context,
                    chat_id,
                    await get_language_string(context, "AUTO_MUTE", user_id=0, target_user_id=user_id),
                )
        except telegram.error.TelegramError as e:
            logger.warning(f"Failed to process new member {user_id} in chat {chat_id}: {e}")

async def set_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = (query.message.chat if query.message else None)  # Chat where the message with buttons is

    if not user or not query or not chat:
        return

    await query.answer()  # Answer the callback query

    data_parts = query.data.split(
        "_")  # {LANG_CALLBACK_PREFIX}_select_{lang_code} or {LANG_CALLBACK_PREFIX}_page_{page_num}

    # Ensure valid callback data structure
    if len(data_parts) < 2 or data_parts[0] != LANG_CALLBACK_PREFIX.rstrip("_"):
        logger.warning(f"Received invalid language callback data: {query.data}")
        await edit_message_text_mb(
            context.bot,
            text="Invalid language selection data.",
            chat_id=chat.id,
            message_id=query.message.message_id,
            reply_markup=None,
        )
        return

    action = data_parts[1]

    target_chat_id_for_setting = context.user_data.get("lang_target_chat_id")
    if target_chat_id_for_setting is None:
        logger.warning(f"lang_target_chat_id not found in user_data for callback {query.data}")
        await edit_message_text_mb(
            context.bot,
            text="Error: Context lost for language setting. Please try /lang again.",
            chat_id=chat.id,
            message_id=query.message.message_id,
            reply_markup=None,
        )  # Use _mb
        return

    # Check admin status if setting for a group (message chat ID)
    if target_chat_id_for_setting != user.id:  # If setting for a group (not PM)
        # Use _is_user_group_admin_or_creator which uses get_cached_admins (_mb)
        is_group_admin = await _is_user_group_admin_or_creator(context, target_chat_id_for_setting, user.id)
        if not is_group_admin and not await _is_super_admin(user.id):  # Super admins can set lang anywhere
            # Edit message to show error, do not proceed
            await edit_message_text_mb(
                context.bot,
                text=await get_language_string(
                    context,
                    "ADMIN_ONLY_COMMAND_MESSAGE",
                    chat_id=target_chat_id_for_setting,
                    user_id=user.id,
                ),
                chat_id=chat.id,
                message_id=query.message.message_id,
                reply_markup=None,
            )  # Use _mb
            return

    if action == "select":
        if len(data_parts) < 3:
            logger.warning(f"Received language select callback with no lang code: {query.data}")
            await edit_message_text_mb(
                context.bot,
                text="Invalid language code.",
                chat_id=chat.id,
                message_id=query.message.message_id,
                reply_markup=None,
            )
            return

        lang_code = data_parts[2]
        if lang_code not in LANGUAGES:
            logger.warning(f"Received language select callback with unknown lang code: {lang_code}")
            await edit_message_text_mb(
                context.bot,
                text="Invalid language selected.",
                chat_id=chat.id,
                message_id=query.message.message_id,
                reply_markup=None,
            )  # Use _mb
            return

        lang_name = LANGUAGES[lang_code]["name"]

        try:
            if target_chat_id_for_setting == user.id:  # Setting for user (PM)
                await db_execute(
                    "UPDATE users SET language_code = ? WHERE user_id = ?",
                    (lang_code, user.id),
                )
                # Update in-memory user_data cache if it exists for this user
                if context.user_data:
                    context.user_data.setdefault(user.id, {})["language_code"] = lang_code
                msg = await get_language_string(
                    context,
                    "LANG_UPDATED_USER",
                    user_id=user.id,
                    language_name=lang_name,
                )
            else:  # Setting for group (message chat ID)
                await db_execute(
                    "UPDATE groups SET language_code = ? WHERE group_id = ?",
                    (target_chat_id_for_setting, lang_code),
                )
                # Update in-memory chat_data cache if it exists for this chat
                if context.application.chat_data.get(target_chat_id_for_setting):
                    context.application.chat_data.setdefault(target_chat_id_for_setting,
                                                             {})["language_code"] = lang_code
                else:  # Initialize if not exist (less likely for an active chat)
                    context.application.chat_data[target_chat_id_for_setting] = {"language_code": lang_code}

                msg = await get_language_string(
                    context,
                    "LANG_UPDATED_GROUP",
                    chat_id=target_chat_id_for_setting,
                    user_id=user.id,
                    language_name=lang_name,
                )

            # Edit the message to show confirmation, remove buttons
            await edit_message_text_mb(
                context.bot,
                text=msg,
                chat_id=chat.id,
                message_id=query.message.message_id,
                reply_markup=None,
            )  # Use _mb

            logger.info(
                f"Language for {'user ' + str(user.id) if target_chat_id_for_setting == user.id else 'group ' + str(target_chat_id_for_setting)} set to {lang_code} by user {user.id}."
            )

        except Exception as e:
            logger.error(
                f"DB error setting language for {target_chat_id_for_setting} to {lang_code} by user {user.id}: {e}",
                exc_info=True,
            )
            # Edit message to show error
            await edit_message_text_mb(
                context.bot,
                text=f"Error setting language: {e}",
                chat_id=chat.id,
                message_id=query.message.message_id,
                reply_markup=None,
            )  # Use _mb

    elif action == "page":
        if len(data_parts) < 3 or not data_parts[2].isdigit():
            logger.warning(f"Received language page callback with invalid page num: {query.data}")
            await edit_message_text_mb(
                context.bot,
                text="Invalid page number.",
                chat_id=chat.id,
                message_id=query.message.message_id,
                reply_markup=None,
            )
            return

        page_num = int(data_parts[2])
        # Send the next page, editing the current message
        await send_language_selection_page(query, context, page_num)  # Pass query object to continue pagination flow

    # Ignore "noop_ignore" or other unknown actions


# --- Reload Command ---


@feature_controlled("reload")  # Also aliased to /r
async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /reload or /r command to refresh admin cache for the current group."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return
    if chat.type not in [TGChat.GROUP, TGChat.SUPERGROUP]:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "COMMAND_GROUP_ONLY_MESSAGE",
                chat_id=chat.id,
                user_id=user.id,
                command_name="reload",
            ),
        )
        return

    is_super_admin = user.id in AUTHORIZED_USERS

    # Rate limit check for non-super admins
    if not is_super_admin:
        # command_cooldown_check_and_update now takes context
        if not await command_cooldown_check_and_update(context, chat.id, user.id, "reload",
                                                       ADMIN_CACHE_REFRESH_COOLDOWN_SECONDS):
            # command_cooldown_check_and_update will send the cooldown message internally if in a chat.
            return  # On cooldown

    # Check if user is admin (after rate limit, so non-admins don't bypass rate limit just to be told they're not admin)
    # Use force_refresh=False first to utilize cache if possible before the actual refresh for the check
    # Then, if they are admin (or super admin), we do the force_refresh.
    # _is_user_group_admin_or_creator checks super admin status first, then uses cached admins (which uses _mb)
    is_chat_admin_or_super = await _is_user_group_admin_or_creator(context, chat.id, user.id)

    if not is_chat_admin_or_super:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "ADMIN_ONLY_COMMAND_MESSAGE_RELOAD",
                chat_id=chat.id,
                user_id=user.id,
            ),
        )  # Specific message
        return

    try:
        # Force refresh admin cache for this chat using the _mb version internally
        refreshed_admin_ids = await get_cached_admins(context, chat.id, force_refresh=True)
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "RELOAD_ADMIN_CACHE_SUCCESS", chat_id=chat.id, user_id=user.id),
        )
        logger.info(
            f"Admin cache for chat {chat.id} refreshed by user {user.id}. Found {len(refreshed_admin_ids)} admins.")
    except Forbidden:
        # get_cached_admins handles the Forbidden case by returning empty set and removing from cache.
        # We only need to send the user notification here.
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "RELOAD_ADMIN_CACHE_FAIL_FORBIDDEN",
                chat_id=chat.id,
                user_id=user.id,
            ),
        )
        logger.warning(
            f"Failed to refresh admin cache for chat {chat.id} (Forbidden). Bot might have lost admin rights.")
    except BadRequest:
        # get_cached_admins handles the BadRequest case similarly.
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "RELOAD_ADMIN_CACHE_FAIL_BADREQUEST",
                chat_id=chat.id,
                user_id=user.id,
            ),
        )
        logger.warning(f"Failed to refresh admin cache for chat {chat.id} (BadRequest). Bot might not be in the group.")
    except Exception as e:
        # get_cached_admins might re-raise other exceptions.
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "RELOAD_ADMIN_CACHE_FAIL_ERROR",
                chat_id=chat.id,
                user_id=user.id,
                error=str(e),
            ),
        )
        logger.error(
            f"Error refreshing admin cache for chat {chat.id} by user {user.id}: {e}",
            exc_info=True,
        )


# main.py - Part 4 of 20

# --- Multi-Bot Support Framework (Initial Fallback Implementation) ---
# This is a conceptual start. True load balancing or complex coordination is much harder.
# We will modify core API calling functions to try with fallback bot instances.

# Store multiple application instances if multiple tokens are provided
# This should ideally be managed by the main() function.
# applications: List[Application] = [] # This will be populated in main() - Defined in Part 1 logic block
# bot_instances_cache: Dict[str, Application] = {} # Defined in Part 1 logic block

# DB_DUMP_CHANNEL_ID: Optional[int] = None # Loaded from config in MemoryManagement section - Defined in Part 1 logic block

# Multi-bot related helpers and wrappers - definitions start here


async def _get_next_bot_instance(current_bot_id: int) -> Optional[Application]:
    """
    Gets the next available bot application instance for fallback, cycling through BOT_TOKENS.
    Attempts to avoid re-using the initial bot that just failed.
    """
    global BOT_TOKENS, bot_instances_cache
    if len(BOT_TOKENS) <= 1:
        # logger.debug("No fallback bots configured.")
        return None  # No fallback instances

    try:
        current_token = None
        # Find the token corresponding to the current_bot_id from the cache
        for token, app_instance in bot_instances_cache.items():
            if app_instance.bot.id == current_bot_id:
                current_token = token
                break

        if current_token is None:
            logger.error(f"Fallback: Could not find token for current bot ID {current_bot_id} in cache. Cannot cycle.")
            return None  # Cannot determine current bot's token to find the next

        if current_token not in BOT_TOKENS:
            logger.error(f"Fallback: Current bot token for ID {current_bot_id} not in configured BOT_TOKENS list.")
            # Fallback might be tricky, try the first token if it's different
            if (BOT_TOKENS and BOT_TOKENS[0] in bot_instances_cache and
                    bot_instances_cache[BOT_TOKENS[0]].bot.id != current_bot_id):
                logger.info(f"Fallback: Trying primary bot {BOT_TOKENS[0]} as current token was not in list.")
                return bot_instances_cache[BOT_TOKENS[0]]
            return None  # Cannot fallback

        current_token_index = BOT_TOKENS.index(current_token)

        # Find the next unique token in the list, cycling if necessary
        next_token_index = current_token_index
        for _ in range(len(BOT_TOKENS) - 1):  # Try up to N-1 other tokens
            next_token_index = (next_token_index + 1) % len(BOT_TOKENS)
            next_token = BOT_TOKENS[next_token_index]

            # Ensure the next token is different from the current one AND is in the instance cache
            if next_token != current_token and next_token in bot_instances_cache:
                # Also ensure the bot ID is different, just in case (highly unlikely same ID for different tokens)
                if bot_instances_cache[next_token].bot.id != current_bot_id:
                    # logger.debug(f"Fallback: Cycling to next bot instance with token ...{next_token[-6:]}")
                    return bot_instances_cache[next_token]
                else:
                    logger.warning(
                        f"Fallback: Next token ...{next_token[-6:]} has same bot ID {current_bot_id}? Skipping.")

        logger.warning(
            f"Fallback: No other unique, usable bot instance found after cycling through {len(BOT_TOKENS)} tokens.")
        return None  # No suitable next bot instance found

    except (ValueError):  # current_token not in BOT_TOKENS list - Should be caught above now
        logger.error(
            f"Fallback: Logic error - Current bot token for ID {current_bot_id} not in BOT_TOKENS list unexpectedly.")
        return None
    except Exception as e:
        logger.error(f"Error getting next bot instance: {e}", exc_info=True)
        return None


async def _execute_bot_action_mb(
    initial_bot_instance: Any,  # Application or Bot object that initiated the attempt
    action_coroutine_factory: Callable,  # A function that takes a bot object and returns a coroutine
    action_name: str,
    max_retries_per_bot: int = 1,  # How many times to retry with the same bot
    max_bot_fallbacks: Optional[int] = None,  # Max number of different bot instances to try
    initial_bot_id_override: Optional[int] = None,  # To enforce starting with a specific bot ID
) -> Any:
    """
    Executes a generic bot action with multi-bot fallback for network errors, timeouts, and RetryAfter.
    Handles Forbidden and BadRequest by typically not retrying with other bots for that specific error.

    Args:
        initial_bot_instance: The first bot instance (Application or Bot object) to try.
                              This bot instance's ID is used to determine where to start cycling from.
        action_coroutine_factory: A function that, when called with a bot object, returns the awaitable coroutine for the action.
                                  Example: `lambda bot_obj: bot_obj.get_chat(chat_id=some_id)`
        action_name: A descriptive name for the action (e.g., "get_chat", "restrict_member").
        max_retries_per_bot: How many times to retry with the *same* bot if a RetryAfter is encountered.
                             Default is 1 (no retry with the same bot, immediately try fallback on RetryAfter).
        max_bot_fallbacks: Total number of different bot instances to try. Defaults to total number of BOT_TOKENS.
        initial_bot_id_override: If provided, this bot ID is considered the "primary" for this call's tracking,
                                 though `initial_bot_instance` is the one actually used for the first attempt.

    Returns:
        The result of the successful action.

    Raises:
        ValueError: If the bot instance is invalid.
        Forbidden: If a Forbidden error is encountered.
        BadRequest: If a BadRequest error is encountered.
        Exception: If the action fails after all retries and fallbacks.
    """
    # Validate initial bot instance
    if not initial_bot_instance:
        logger.error(f"Initial bot instance is None for '{action_name}'")
        raise ValueError("Initial bot instance cannot be None")

    # Extract Bot object
    current_bot_obj = (
        initial_bot_instance.bot
        if hasattr(initial_bot_instance, "bot")
        else initial_bot_instance
    )

    # Validate that current_bot_obj is a Bot instance
    if not isinstance(current_bot_obj, Bot) or not hasattr(current_bot_obj, "get_chat"):
        logger.error(f"Invalid bot object for '{action_name}': {type(current_bot_obj).__name__}")
        raise ValueError(f"Expected Bot instance, got {type(current_bot_obj).__name__}")

    initial_bot_id = (
        initial_bot_id_override if initial_bot_id_override is not None else current_bot_obj.id
    )

    tried_bot_ids = {current_bot_obj.id}  # Track tried bot IDs

    # Determine total number of bots to try
    total_available_bots = len(BOT_TOKENS) if BOT_TOKENS else 1
    if max_bot_fallbacks is None:
        max_bot_fallbacks = total_available_bots
    else:
        max_bot_fallbacks = min(max_bot_fallbacks, total_available_bots)

    last_exception: Optional[Exception] = None

    for bot_attempt_count in range(max_bot_fallbacks):
        logger.debug(
            f"Executing '{action_name}' with bot {current_bot_obj.id} "
            f"(Bot attempt {bot_attempt_count + 1}/{max_bot_fallbacks})"
        )

        for retry_num in range(max_retries_per_bot):
            try:
                action_coro = action_coroutine_factory(current_bot_obj)
                result = await action_coro
                logger.debug(f"Action '{action_name}' succeeded with bot {current_bot_obj.id}")
                return result
            except RetryAfter as e_ra:
                last_exception = e_ra
                logger.warning(
                    f"Bot {current_bot_obj.id} faced RetryAfter for '{action_name}' "
                    f"(wait {e_ra.retry_after}s). Retry {retry_num + 1}/{max_retries_per_bot}."
                )
                if retry_num < max_retries_per_bot - 1:
                    await asyncio.sleep(e_ra.retry_after + 0.1)
                else:
                    logger.warning(
                        f"Bot {current_bot_obj.id} max retries for RetryAfter on '{action_name}' exhausted."
                    )
                    break
            except (TimedOut, NetworkError) as e_net:
                last_exception = e_net
                logger.warning(
                    f"Bot {current_bot_obj.id} faced {type(e_net).__name__} for '{action_name}'. "
                    f"Retry {retry_num + 1}/{max_retries_per_bot}."
                )
                if retry_num < max_retries_per_bot - 1:
                    await asyncio.sleep(1 + retry_num * 2)
                else:
                    logger.warning(
                        f"Bot {current_bot_obj.id} max retries for {type(e_net).__name__} on '{action_name}' exhausted."
                    )
                    break
            except Forbidden as e_f:
                logger.warning(
                    f"Bot {current_bot_obj.id} faced Forbidden for '{action_name}': {e_f}. "
                    f"This is usually final for this bot and request."
                )
                last_exception = e_f
                raise
            except BadRequest as e_br:
                logger.warning(
                    f"Bot {current_bot_obj.id} faced BadRequest for '{action_name}': {e_br}. "
                    f"This is often final for this request."
                )
                last_exception = e_br
                raise
            except Exception as e_unexp:
                logger.error(
                    f"Bot {current_bot_obj.id} faced unexpected error during '{action_name}' "
                    f"(Attempt {bot_attempt_count + 1}, Retry {retry_num + 1}): {e_unexp}",
                    exc_info=True,
                )
                last_exception = e_unexp
                break

        # Try fallback bot if attempts remain
        if bot_attempt_count < max_bot_fallbacks - 1:
            next_bot_app = await _get_next_bot_instance(current_bot_obj.id)
            if next_bot_app and next_bot_app.bot.id not in tried_bot_ids:
                logger.info(f"Switching to fallback bot {next_bot_app.bot.id} for '{action_name}'.")
                current_bot_obj = next_bot_app.bot
                tried_bot_ids.add(current_bot_obj.id)
                await asyncio.sleep(0.1)
            else:
                logger.warning(
                    f"No more unique, usable fallback bots available for '{action_name}'. "
                    f"Total unique bots tried: {len(tried_bot_ids)}."
                )
                break
        else:
            logger.warning(f"All {max_bot_fallbacks} bot fallbacks used for '{action_name}'.")
            break

    if last_exception:
        logger.error(
            f"Action '{action_name}' failed after all attempts and fallbacks with final error: "
            f"{type(last_exception).__name__}: {last_exception}"
        )
        raise last_exception
    else:
        logger.error(f"Action '{action_name}' failed after all attempts and fallbacks with no specific error recorded.")
        raise Exception(f"Action '{action_name}' failed after all retries and fallbacks.")

# --- Wrappers for common API calls using _execute_bot_action_mb ---
from telegram.error import Forbidden, BadRequest
from typing import Union, Optional, Any
import asyncio
from logging import getLogger

logger = getLogger(__name__)

async def get_user_mb(context_or_bot: Any, user_id: Union[int, str], **kwargs) -> Optional[Union[TGUser, TGChat]]:
    """
    Fetches user or chat info using a user ID or username, with multi-bot support.
    Args:
        context_or_bot: ContextTypes.DEFAULT_TYPE or Bot instance.
        user_id: Integer user ID or string username (with or without @).
        **kwargs: Additional arguments for bot.get_chat.
    Returns:
        TGChat object if found, else None.
    """
    # Extract bot instance
    bot_instance = context_or_bot.bot if hasattr(context_or_bot, "bot") else context_or_bot
    if not isinstance(bot_instance, Bot):
        logger.error(f"Invalid bot_instance type in get_user_mb: Expected Bot, got {type(bot_instance).__name__}")
        return None

    # Normalize chat_id (user_id or username)
    chat_id = user_id
    if isinstance(user_id, str):
        chat_id = user_id if user_id.startswith("@") else "@" + user_id

    def action_factory(bot_obj):
        return bot_obj.get_chat(chat_id=chat_id, **kwargs)

    try:
        await asyncio.sleep(0.05)  # Rate limiting
        result = await _execute_bot_action_mb(bot_instance, action_factory, f"get_user({user_id})")
        logger.debug(f"Fetched profile for user {user_id}: {result}")
        return result
    except Forbidden:
        logger.warning(f"Failed to fetch user {user_id}: Bot forbidden")
        return None
    except BadRequest:
        logger.warning(f"Failed to fetch user {user_id}: Invalid user or chat")
        return None
    except Exception as e:
        logger.error(f"get_user_mb: Unhandled exception for user_id {user_id}: {e}", exc_info=True)
        return None

import inspect
import traceback

async def get_chat_mb(context_or_bot: Any, chat_id: Union[int, str], **kwargs) -> Optional[TGChat]:
    """Gets chat information with multi-bot fallback."""
    # Extract bot instance
    bot_instance = context_or_bot.bot if hasattr(context_or_bot, "bot") else context_or_bot

    # Validate bot_instance
    if not isinstance(bot_instance, Bot):
        # Get caller information
        caller_frame = inspect.currentframe().f_back
        caller_name = caller_frame.f_code.co_name
        caller_file = caller_frame.f_code.co_filename
        caller_line = caller_frame.f_lineno
        stack_trace = "".join(traceback.format_stack(limit=5)[:-1])  # Last frame is this function
        logger.error(
            f"Invalid bot_instance type in get_chat_mb: Expected Bot, got {type(bot_instance).__name__} "
            f"for chat_id {chat_id}. Called from {caller_name} in {caller_file}:{caller_line}\n"
            f"Stack trace:\n{stack_trace}"
        )
        return None

    # Validate chat_id
    if not (isinstance(chat_id, int) or (isinstance(chat_id, str) and chat_id.startswith("@"))):
        logger.warning(f"Invalid chat_id format: {chat_id}")
        return None

    # Define action factory
    def action_factory(bot_obj): return bot_obj.get_chat(chat_id=chat_id, **kwargs)

    try:
        await asyncio.sleep(0.05)  # Prevent hitting Telegram rate limits
        result = await _execute_bot_action_mb(bot_instance, action_factory, f"get_chat({chat_id})")
        return result
    except (Forbidden, BadRequest):
        logger.warning(f"Failed to fetch chat {chat_id}: Forbidden or invalid chat")
        return None
    except Exception as e:
        logger.error(f"get_chat_mb: Unhandled exception for chat_id {chat_id}: {e}", exc_info=True)
        return None

from telegram import ChatMember
from telegram.ext import ContextTypes

from telegram import Bot, ChatMember
from telegram.ext import ContextTypes
from typing import Optional

async def get_chat_member_mb(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, **kwargs) -> Optional[ChatMember]:
    """Gets chat member information with retry logic."""
    if not isinstance(context.bot, Bot):
        logger.error(f"Invalid context.bot type: {type(context.bot)} for chat {chat_id}, user {user_id}. Expected Bot.")
        return None

    def action_factory(bot_obj: Bot):
        return bot_obj.get_chat_member(chat_id=chat_id, user_id=user_id, **kwargs)
    
    try:
        result = await _execute_bot_action_mb(context.bot, action_factory, f"get_chat_member({chat_id},{user_id})")
        return result
    except (Forbidden, BadRequest):
        logger.debug(f"Permission or bad request error for get_chat_member({chat_id},{user_id})")
        return None
    except Exception as e:
        logger.error(f"get_chat_member_mb: Unhandled exception for chat {chat_id}, user {user_id}: {e}", exc_info=True)
        return None

async def get_chat_administrators_mb(context_or_bot: Any, chat_id: int, **kwargs) -> Optional[List[ChatMember]]:
    """Gets chat administrators with multi-bot fallback."""
    bot_instance = context_or_bot.bot if hasattr(context_or_bot, "bot") else context_or_bot
    if not isinstance(bot_instance, Bot):
        caller_frame = inspect.currentframe().f_back
        caller_name = caller_frame.f_code.co_name
        caller_file = caller_frame.f_code.co_filename
        caller_line = caller_frame.f_lineno
        stack_trace = "".join(traceback.format_stack(limit=5)[:-1])
        logger.error(
            f"Invalid bot_instance type in get_chat_administrators_mb: Expected Bot, got {type(bot_instance).__name__} "
            f"for chat_id {chat_id}. Called from {caller_name} in {caller_file}:{caller_line}\n"
            f"Stack trace:\n{stack_trace}"
        )
        return None

    def action_factory(bot_obj): return bot_obj.get_chat_administrators(chat_id=chat_id, **kwargs)
    try:
        result = await _execute_bot_action_mb(bot_instance, action_factory, f"get_chat_administrators({chat_id})")
        return result
    except (Forbidden, BadRequest):
        logger.warning(f"Failed to fetch administrators for chat {chat_id}: Forbidden or invalid request")
        return None
    except Exception as e:
        logger.error(f"get_chat_administrators_mb: Unhandled exception for chat_id {chat_id}: {e}", exc_info=True)
        return None

async def restrict_chat_member_mb(
    context_or_bot: Any,
    chat_id: int,
    user_id: int,
    permissions: ChatPermissions,
    until_date: Optional[datetime] = None,
    **kwargs,
) -> bool:
    """Restricts a chat member with multi-bot fallback."""
    bot_instance = (context_or_bot.bot if hasattr(context_or_bot, "bot") else context_or_bot)

    def action_factory(bot_obj): return bot_obj.restrict_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        permissions=permissions,
        until_date=until_date,
        **kwargs,
    )
    try:
        await _execute_bot_action_mb(bot_instance, action_factory, f"restrict_chat_member({chat_id},{user_id})")
        return True  # Action was successful
    except (Forbidden, BadRequest):
        # Catch expected API errors and return False
        return False
    except Exception as e:
        logger.error(f"restrict_chat_member_mb: Unhandled exception for chat {chat_id}, user {user_id}: {e}")
        return False


async def ban_chat_member_mb(
    context_or_bot: Any,
    chat_id: int,
    user_id: int,
    until_date: Optional[datetime] = None,
    revoke_messages: Optional[bool] = None,
    **kwargs,
) -> bool:
    """Bans a chat member with multi-bot fallback."""
    bot_instance = (context_or_bot.bot if hasattr(context_or_bot, "bot") else context_or_bot)

    def action_factory(bot_obj): return bot_obj.ban_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        until_date=until_date,
        revoke_messages=revoke_messages,
        **kwargs,
    )
    try:
        await _execute_bot_action_mb(bot_instance, action_factory, f"ban_chat_member({chat_id},{user_id})")
        return True  # Action was successful
    except (Forbidden, BadRequest):
        # Catch expected API errors and return False
        return False
    except Exception as e:
        logger.error(f"ban_chat_member_mb: Unhandled exception for chat {chat_id}, user {user_id}: {e}")
        return False


async def unban_chat_member_mb(
    context_or_bot: Any,
    chat_id: int,
    user_id: int,
    only_if_banned: Optional[bool] = None,
    **kwargs,
) -> bool:
    """Unbans a chat member with multi-bot fallback."""
    bot_instance = (context_or_bot.bot if hasattr(context_or_bot, "bot") else context_or_bot)
    def action_factory(bot_obj): return bot_obj.unban_chat_member(
        chat_id=chat_id, user_id=user_id, only_if_banned=only_if_banned, **kwargs)
    try:
        await _execute_bot_action_mb(bot_instance, action_factory, f"unban_chat_member({chat_id},{user_id})")
        return True  # Action was successful
    except (Forbidden, BadRequest):
        # Catch expected API errors and return False
        return False
    except Exception as e:
        logger.error(f"unban_chat_member_mb: Unhandled exception for chat {chat_id}, user {user_id}: {e}")
        return False


async def delete_message_mb(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, **kwargs) -> bool:
    """Deletes a message with retry logic."""
    def action_factory(bot_obj: Bot):
        return bot_obj.delete_message(chat_id=chat_id, message_id=message_id, **kwargs)
    
    try:
        await _execute_bot_action_mb(context.bot, action_factory, f"delete_message({chat_id},{message_id})")
        return True
    except (Forbidden, BadRequest):
        return False
    except Exception as e:
        logger.error(f"delete_message_mb: Unhandled exception for chat {chat_id}, msg {message_id}: {e}", exc_info=True)
        return False

async def edit_message_text_mb(
    context_or_bot: Any,
    text: str,
    chat_id: Optional[int] = None,
    message_id: Optional[int] = None,
    inline_message_id: Optional[str] = None,
    **kwargs,
) -> bool:
    """Edits a message with multi-bot fallback."""
    bot_instance = (context_or_bot.bot if hasattr(context_or_bot, "bot") else context_or_bot)

    def action_factory(bot_obj): return bot_obj.edit_message_text(
        text=text,
        chat_id=chat_id,
        message_id=message_id,
        inline_message_id=inline_message_id,
        **kwargs,
    )
    try:
        await _execute_bot_action_mb(
            bot_instance,
            action_factory,
            f"edit_message_text(chat={chat_id},msg={message_id},inline={inline_message_id})",
        )
        return True  # Action was successful
    except BadRequest as e:
        # Catch BadRequest. "Message is not modified" is common and should be treated as success.
        if "Message is not modified" in str(e):
            # logger.debug(f"edit_message_text_mb: Message {message_id} in {chat_id} not modified.")
            return True  # Treat as success
        logger.warning(f"edit_message_text_mb: BadRequest: {e} for chat {chat_id}, msg {message_id}")
        return False
    except Forbidden:
        # Catch Forbidden and return False
        return False
    except Exception as e:
        logger.error(f"edit_message_text_mb: Unhandled exception for chat {chat_id}, msg {message_id}: {e}")
        return False


# The main send_message_safe function is now a wrapper that uses send_message_safe_mb


async def send_message_safe(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    **kwargs,
) -> Optional[TGMessage]:
    """
    Safely sends a message using the multi-bot fallback mechanism.
    Wrapper around send_message_safe_mb using context.bot.
    """
    if not text:
        logger.warning(f"Attempted to send empty message to {chat_id}.")
        return None

    if context.bot is None:
        logger.error(f"Bot instance is None in send_message_safe for chat {chat_id}")
        return None

    try:
        return await send_message_safe_mb(
            context.bot,
            chat_id,
            text,
            **kwargs,
        )
    except Exception as e:
        logger.error(f"send_message_safe failed for {chat_id}: {e}", exc_info=True)
        return None

async def send_message_safe_mb(
    initial_bot_instance: Any,
    chat_id: int,
    text: str,
    **kwargs,
) -> Optional[TGMessage]:
    """
    Sends a message with multi-bot fallback. Uses _execute_bot_action_mb for bot cycling.
    """
    if not text:
        logger.warning(f"Attempted to send empty message to {chat_id} via _mb.")
        return None

    if initial_bot_instance is None:
        logger.error(f"Initial bot instance is None in send_message_safe_mb for chat {chat_id}")
        return None

    def action_factory(bot_obj): 
        return bot_obj.send_message(chat_id=chat_id, text=text, **kwargs)
    action_name = f"send_message({chat_id})"

    try:
        sent_message = await _execute_bot_action_mb(
            initial_bot_instance,
            action_factory,
            action_name,
        )
        return sent_message
    except Forbidden as e:
        logger.warning(f"Bot {initial_bot_instance.bot.id if hasattr(initial_bot_instance, 'bot') else 'unknown'} "
                      f"forbidden to send to group {chat_id}: {e}")
        if chat_id < 0:
            asyncio.create_task(remove_group_from_db(chat_id))
        return None
    except BadRequest as e:
        logger.warning(f"Bad request sending to {chat_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to send message to {chat_id} via _mb: {e}", exc_info=True)
        return None

async def _execute_bot_action_mb(
    initial_bot_instance: Any,
    action_factory: Callable,
    action_name: str,
    max_retries_per_bot: int = 1,
    max_bot_fallbacks: int = 1,
) -> Any:
    """
    Stub for multi-bot action execution. Attempts the action with the initial bot.
    To be extended for multiple bots when BOT_TOKENS is available.
    """
    if initial_bot_instance is None:
        logger.error(f"Null bot instance in _execute_bot_action_mb for {action_name}")
        raise ValueError("Bot instance is None")

    attempt = 0
    while attempt < max_retries_per_bot:
        try:
            result = await action_factory(initial_bot_instance)
            logger.debug(f"Action {action_name} succeeded with bot {initial_bot_instance.bot.id}")
            return result
        except RetryAfter as e:
            logger.warning(f"Rate limit for {action_name}. Waiting {e.retry_after}s.")
            await asyncio.sleep(e.retry_after)
            attempt += 1
        except TelegramError as e:
            logger.error(f"Telegram error for {action_name}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error for {action_name}: {e}", exc_info=True)
            raise
    logger.error(f"Max retries ({max_retries_per_bot}) reached for {action_name}")
    raise TelegramError(f"Failed to execute {action_name} after {max_retries_per_bot} attempts")

# Helper functions that use the new _mb wrappers
# These were conceptually in Part 7, implementing them here.


from typing import Tuple, Optional
from telegram.ext import ContextTypes
from telegram import User as TGUser, Chat as TGChat
from logging import getLogger

logger = getLogger(__name__)

from datetime import datetime, timedelta
from typing import Dict, Tuple

user_profile_cache: Dict[int, Tuple[bool, Optional[str], Optional[str], datetime]] = {}

async def user_has_links_cached(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> Tuple[bool, Optional[str], Optional[str]]:
    """Checks if a user's profile fields contain prohibited content, using cache."""
    # Check cache (expire after 1 hour)
    if user_id in user_profile_cache:
        has_issue, field, issue_type, timestamp = user_profile_cache[user_id]
        if datetime.now() - timestamp < timedelta(hours=1):
            logger.debug(f"Cache hit for user {user_id}")
            return has_issue, field, issue_type

    try:
        user = await get_user_mb(context, user_id)
        if not user:
            logger.warning(f"Could not fetch user {user_id}: User not found or forbidden")
            user_profile_cache[user_id] = (False, "api_fetch_failed", "user_not_found", datetime.now())
            return False, "api_fetch_failed", "user_not_found"

        fields = [
            ("first_name", user.first_name or ""),
            ("last_name", user.last_name or ""),
            ("bio", getattr(user, "bio", "") or ""),
            ("username", user.username or ""),
        ]

        for field_name, field_value in fields:
            if field_value:
                issue_found, issue_type = await check_for_links_enhanced(context, field_value, field_name)
                if issue_found:
                    user_profile_cache[user_id] = (True, field_name, issue_type, datetime.now())
                    return True, field_name, issue_type

        user_profile_cache[user_id] = (False, None, None, datetime.now())
        return False, None, None
    except Exception as e:
        logger.error(f"Error checking profile for user {user_id}: {e}", exc_info=True)
        user_profile_cache[user_id] = (False, "api_unknown_error", str(e), datetime.now())
        return False, "api_unknown_error", str(e)
        
import re
from typing import Tuple, Optional
from telegram.ext import ContextTypes
from telegram import User as TGUser, Chat as TGChat
from logging import getLogger

logger = getLogger(__name__)

async def is_real_telegram_user_cached(context: ContextTypes.DEFAULT_TYPE, username: str) -> Tuple[Optional[int], bool]:
    """
    Checks if a given username corresponds to a real Telegram user (or bot) using cache.
    Returns (user_id, is_bot).
    Uses get_user_mb for resolving username.
    """
    global username_to_id_cache
    if username_to_id_cache is None:
        logger.error("username_to_id_cache not initialized.")
        return None, False

    # Normalize username and check cache
    key = username.lower().lstrip("@")  # Cache key is username without @, lower case
    if key in username_to_id_cache:
        logger.debug(f"Username cache hit for '{key}'")
        resolved_id, is_bot_flag = username_to_id_cache.get(key)
        return resolved_id, is_bot_flag

    # Cache miss, resolve username via API
    resolved_user_id: Optional[int] = None
    is_bot_flag = False

    # Basic validation for username format
    processed_username = username if username.startswith("@") else "@" + username
    min_len = getattr(patterns, "MIN_USERNAME_LENGTH", 5)  # Get min length from patterns or default

    # Regex check for valid username format (excluding the @)
    if not re.match(rf"^@[a-zA-Z0-9_]{{{min_len},32}}$", processed_username):
        logger.debug(f"Invalid username format: '{username}'")
        # Cache invalid formats to avoid repeated API calls
        username_to_id_cache[key] = (None, False)
        return None, False

    try:
        # Use get_user_mb to resolve the username
        user = await get_user_mb(context, processed_username)  # Pass context, not context.bot

        if user and isinstance(user, TGUser):
            resolved_user_id = user.id
            is_bot_flag = user.is_bot
            logger.debug(f"Resolved username '{processed_username}' to user ID {resolved_user_id}, is_bot={is_bot_flag}")
        elif user and isinstance(user, TGChat) and user.type in [TGChat.PRIVATE, TGChat.BOT]:
            resolved_user_id = user.id
            is_bot_flag = user.type == TGChat.BOT or getattr(user, "is_bot", False)
            logger.debug(f"Resolved username '{processed_username}' to chat ID {resolved_user_id}, is_bot={is_bot_flag}")
        else:
            logger.debug(f"get_user_mb failed to resolve username '{processed_username}'. User not found or invalid.")
            # resolved_user_id remains None, is_bot_flag remains False

    except Exception as e:
        logger.error(f"Unexpected error resolving username '{processed_username}' via get_user_mb: {e}", exc_info=True)
        # resolved_user_id remains None, is_bot_flag remains False

    # Cache the result
    username_to_id_cache[key] = (resolved_user_id, is_bot_flag)
    logger.debug(f"Username cache updated for '{key}': ID={resolved_user_id}, is_bot={is_bot_flag}")

    return resolved_user_id, is_bot_flag

# main.py - Part 5 of 20


async def is_user_subscribed(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id_for_pm_guidance: Optional[int] = None,
) -> bool:
    """
    Checks if a user is subscribed to the configured channel if required.
    Returns True if no channel is set, or if the user is subscribed.
    Uses get_chat_mb and get_chat_member_mb for API calls.
    """
    channel_id = settings.get("channel_id")
    if not channel_id:
        # logger.debug("No verification channel configured.")
        return True  # No channel required

    subbed = False
    channel_chat_obj: Optional[TGChat] = None
    channel_link = settings.get("channel_invite_link")

    try:
        # Use get_chat_mb to get channel info with fallback
        channel_chat_obj = await get_chat_mb(context.bot, channel_id)  # Use _mb version

        if not channel_chat_obj or channel_chat_obj.type != TGChat.CHANNEL:
            # If get_chat_mb failed or the ID doesn't point to a channel
            logger.error(f"Configured channel ID {channel_id} is invalid or not a channel after get_chat_mb.")
            settings["channel_id"] = None  # Disable the feature if channel is invalid
            settings["channel_invite_link"] = None
            return True  # Assume requirement is met if channel is invalid

        # Ensure we have an invite link if possible
        if not channel_link and channel_chat_obj.invite_link:
            settings["channel_invite_link"] = channel_chat_obj.invite_link
            channel_link = settings["channel_invite_link"]
            logger.info(f"Fetched invite link for channel {channel_id}.")
        elif not channel_link:
            # If no link and cannot fetch one, use the ID
            channel_link = f"Channel ID: {channel_id}"

        # Use get_chat_member_mb to check user's status in the channel
        member = await get_chat_member_mb(context.bot, channel_id, user_id)  # Use _mb version

        if member:  # If get_chat_member_mb returned a member object
            subbed = member.status in [
                ChatMemberStatus.MEMBER,
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.OWNER,
            ]

    except (Exception) as e:  # Catch any unexpected errors from _mb calls (Forbidden/BadRequest handled internally)
        logger.error(
            f"Unexpected error checking subscription for user {user_id} in channel {channel_id}: {e}",
            exc_info=True,
        )
        subbed = False  # Assume not subscribed on error

    # If user is not subscribed and chat_id_for_pm_guidance is provided, send a PM
    if not subbed and chat_id_for_pm_guidance is not None:
        # Use send_message_safe which now uses the multi-bot version
        # Send the guidance message to the user's PM chat (user_id)
        # Use the language string for channel issue guidance in PM
        guidance_message = await get_language_string(
            context,
            "UNMUTE_ME_CHANNEL_ISSUE_PM",  # This pattern is used for the "Unmute Me" button case
            user_id=user_id,
            channel_link=channel_link,
        )
        # Add a specific pattern for general subscription requirement if needed, or reuse
        # Let's reuse for simplicity now, it mentions fixing channel issue.

        # Pass the chat_id_for_pm_guidance to send_message_safe as the target chat ID
        # This is typically the user's PM chat if guidance is needed from a command/button in PM
        # Or the group chat if the check happened there and guidance is needed there.
        # The variable name `chat_id_for_pm_guidance` is confusing if it's used for group chat.
        # Let's rename it to `notification_chat_id`.
        notification_chat_id = chat_id_for_pm_guidance
        # However, the requirement was to send PM guidance... so the target should be user_id.
        # Let's stick to sending to user_id for guidance.
        await send_message_safe(
            context,
            user_id,
            guidance_message,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

        # If the original interaction was in a group, send a short message there too
        if context and context.effective_chat and context.effective_chat.id != user_id:
            await send_message_safe(
                context,
                context.effective_chat.id,
                await get_language_string(
                    context,
                    "UNMUTE_ME_CHANNEL_ISSUE_GROUP_SHORT",  # Need a shorter group pattern
                    chat_id=context.effective_chat.id,
                    user_id=user_id,
                ),
            )

    return subbed


from telegram import Update, MessageEntity
from telegram.constants import ChatType

logger = logging.getLogger(__name__)

message_processing_debounce_cache = {}  # Assuming global cache

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Main message handler for processing messages."""
    if not await get_feature_state("message_processing", default=True):
        logger.debug("Message processing feature is disabled.")
        return

    chat = update.effective_chat
    user = update.effective_user
    message = update.message

    if not chat or not user or not message:
        logger.warning("handle_message received update without chat, user, or message.")
        return

    if user.is_bot:
        logger.debug(f"Ignoring message from bot user {user.id} in chat {chat.id}.")
        return

    if chat.type == ChatType.PRIVATE:
        logger.debug(f"Ignoring non-command text message from user {user.id} in PM.")
        return

    if MAINTENANCE_MODE and not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "MAINTENANCE_MODE_ACTIVE",
                chat_id=chat.id,
                user_id=user.id,
            ),
            parse_mode="HTML",
        )
        return

    if await _is_super_admin(user.id) or user.id in settings["free_users"] or await is_user_exempt_in_group(chat.id, user.id):
        logger.debug(f"User {user.id} is exempt in chat {chat.id}. Skipping message processing.")
        return

    # Add user to database
    await add_user(user.id, user.username, user.first_name, user.last_name or "")

    message_debounce_key = f"msg_proc_{chat.id}_{message.message_id}"
    if message_debounce_key in message_processing_debounce_cache:
        logger.debug(f"Message {message.message_id} in chat {chat.id} processing debounced.")
        return
    message_processing_debounce_cache[message_debounce_key] = True

    message_text = message.text or message.caption or ""
    reasons_for_action: List[str] = []
    problematic_mentions: List[Tuple[str, int, str]] = []
    sender_trigger_type: Optional[str] = None

    # Check bad actor
    if await is_bad_actor(user.id):
        sender_trigger_type = "bad_actor"
        reasons_for_action.append(
            await get_language_string(
                context,
                "SENDER_IS_BAD_ACTOR_REASON",
                chat_id=chat.id,
                user_id=user.id,
            )
        )

    # Check message content
    message_has_issue, message_issue_type = await check_for_links_enhanced(context, message_text, "message_text")
    should_delete_message = False
    if message_has_issue:
        should_delete_message = True
        if sender_trigger_type is None:
            sender_trigger_type = "message"
        reasons_for_action.append(
            await get_language_string(
                context,
                "MESSAGE_VIOLATION_REASON",
                chat_id=chat.id,
                user_id=user.id,
                message_issue_type=message_issue_type or "unknown",
            )
        )

    # Check mentions
    if message.entities:
        for entity in message.entities:
            if entity.type in [MessageEntity.MENTION, MessageEntity.TEXT_MENTION]:
                mentioned_user_id = None
                mentioned_username = None
                if entity.type == MessageEntity.MENTION:
                    mention_text = message_text[entity.offset : entity.offset + entity.length]
                    mentioned_username = mention_text.lstrip("@")
                    mentioned_user_id, is_bot = await is_real_telegram_user_cached(context, mentioned_username)
                elif entity.type == MessageEntity.TEXT_MENTION and entity.user:
                    mentioned_user_id = entity.user.id
                    mentioned_username = entity.user.username

                if mentioned_user_id and not is_bot:
                    if mentioned_user_id in settings["free_users"] or await is_user_exempt_in_group(chat.id, mentioned_user_id):
                        continue
                    has_issue, field, issue_type = await user_has_links_cached(context, mentioned_user_id)
                    if has_issue:
                        problematic_mentions.append((mentioned_username or str(mentioned_user_id), mentioned_user_id, issue_type))

    # Check sender profile
    if sender_trigger_type is None or sender_trigger_type == "message":
        has_issue, field, issue_type = await user_has_links_cached(context, user.id)
        if has_issue:
            if sender_trigger_type is None:
                sender_trigger_type = "profile"
            reasons_for_action.append(
                await get_language_string(
                    context,
                    "NEW_USER_PROFILE_VIOLATION_REASON",
                    chat_id=chat.id,
                    user_id=user.id,
                    field=field or "unknown",
                    issue_type=issue_type or "unknown",
                )
            )

    # Take action if needed
    if reasons_for_action or problematic_mentions:
        await take_action(update, context, reasons_for_action, sender_trigger_type, problematic_mentions)

    # Delete message if necessary
    if should_delete_message and message.message_id:
        logger.info(f"Deleting message {message.message_id} from user {user.id} in chat {chat.id} due to content violation.")
        delete_success = await delete_message_mb(context, chat.id, message.message_id)
        if not delete_success:
            logger.warning(f"Could not delete message {message.message_id} from {user.id} in chat {chat.id}.")  
            
async def parse_admin_command(text: str, context: Optional[ContextTypes.DEFAULT_TYPE] = None) -> Dict[str, Any]:
    """Parses an admin command string based on configured patterns."""
    parsed_data = {
        "raw_text": text,
        "action_type": None,
        "command_used": None,
        "target_identifier": None,
        "target_user_id": None,
        "duration_seconds": None,
        "reason": None,
    }

    if not text or not text.strip():
        logger.debug("Empty command text provided.")
        return parsed_data

    text_lower = text.lower().strip()
    found_initiator = None
    command_start_index = -1

    for initiator in COMMAND_PATTERNS.get("initiators", {}).get("values", []):
        if text_lower.startswith(initiator.lower()):
            found_initiator = initiator
            command_start_index = len(initiator)
            break

    if not found_initiator:
        logger.debug(f"No valid initiator found in command: {text}")
        return parsed_data

    remaining_text = text[command_start_index:].strip()
    if not remaining_text:
        logger.debug("No command content after initiator.")
        return parsed_data

    command_parts = remaining_text.split(maxsplit=1)
    potential_cmd_text = command_parts[0]
    args_text = command_parts[1] if len(command_parts) > 1 else ""

    action_type = None
    command_used_exact = None

    potential_cmd_text_lower = potential_cmd_text.lower()
    for cmd_type, cmd_list in COMMAND_PATTERNS.get("commands", {}).items():
        if potential_cmd_text_lower in [c.lower() for c in cmd_list]:
            action_type = cmd_type
            command_used_exact = potential_cmd_text
            break

    if not action_type:
        logger.debug(f"No valid command found: {potential_cmd_text}")
        return parsed_data

    parsed_data["action_type"] = action_type
    parsed_data["command_used"] = command_used_exact

    args_parts = args_text.split(maxsplit=MAX_COMMAND_ARGS_SPACES) if args_text else []

    if args_parts:
        first_arg = args_parts[0]
        parsed_duration_seconds = await parse_duration(first_arg)  # Assume async for consistency
        if parsed_duration_seconds is not None:
            parsed_data["duration_seconds"] = parsed_duration_seconds
            parsed_data["reason"] = " ".join(args_parts[1:]).strip() if len(args_parts) > 1 else None
        else:
            potential_target = first_arg
            is_mention = potential_target.startswith("@")
            is_id = potential_target.lstrip("-").isdigit()

            if is_mention or (is_id and len(potential_target) > 5):
                parsed_data["target_identifier"] = potential_target
                if context and is_mention:
                    resolved_id, _ = await is_real_telegram_user_cached(context, potential_target.lstrip("@"))
                    if resolved_id:
                        parsed_data["target_user_id"] = resolved_id
                elif is_id:
                    try:
                        parsed_data["target_user_id"] = int(potential_target)
                    except ValueError:
                        logger.warning(f"Invalid user ID format: {potential_target}")
                        pass

                if len(args_parts) > 1:
                    second_arg = args_parts[1]
                    parsed_duration_seconds = await parse_duration(second_arg)
                    if parsed_duration_seconds is not None:
                        parsed_data["duration_seconds"] = parsed_duration_seconds
                        parsed_data["reason"] = " ".join(args_parts[2:]).strip() if len(args_parts) > 2 else None
                    else:
                        parsed_data["reason"] = " ".join(args_parts[1:]).strip()
            else:
                parsed_data["reason"] = " ".join(args_parts).strip()

    if parsed_data["reason"] == "":
        parsed_data["reason"] = None

    logger.debug(f"parse_admin_command result for '{text}': {parsed_data}")
    return parsed_data

async def parse_duration(duration_str: str) -> int:
    logger = logging.getLogger(__name__)
    try:
        if not duration_str or duration_str.lower() in ("permanent", "none", ""):
            return 0
        total_seconds = 0
        current_number = ""
        for char in duration_str.lower():
            if char.isdigit():
                current_number += char
            elif char in "smhd":
                if not current_number:
                    continue
                num = int(current_number)
                if char == "s":
                    total_seconds += num
                elif char == "m":
                    total_seconds += num * 60
                elif char == "h":
                    total_seconds += num * 3600
                elif char == "d":
                    total_seconds += num * 86400
                current_number = ""
        if current_number:
            total_seconds += int(current_number)
        return total_seconds
    except Exception as e:
        logger.error(f"Error parsing duration '{duration_str}': {e}", exc_info=True)
        return 0

async def set_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle language selection callback queries."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    user_id = update.effective_user.id
    data = query.data.split("_")
    if len(data) != 3 or data[0] != "setlang":
        return

    action, selected_lang, callback_user_id = data
    if str(user_id) != callback_user_id:
        await query.message.reply_text("This button is not for you!")
        return

    if action == "cancel":
        await query.message.delete()
        return

    # Update language in database
    with sqlite3.connect("bot.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO user_settings (user_id, language) VALUES (?, ?)",
            (user_id, selected_lang),
        )
        conn.commit()

    await query.message.edit_text(f"Language set to: {selected_lang}")   
# main.py - Part 6 of 20

# --- Global Ban/Mute Commands ---


@feature_controlled("gmute")
async def gmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Globally mutes a user in all groups the bot is an admin in."""
    user = update.effective_user
    chat = update.effective_chat  # Command issuer's chat
    command_name = "gmute"

    if not user or not await _is_super_admin(user.id):
        # Use send_message_safe (which uses the multi-bot version)
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(context, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", user_id=user.id),
        )
        return

    # Parse command arguments using the refined parser (although gmute/gban are simple)
    # This parser isn't strictly necessary for fixed args like gmute/gban, but good practice
    # args from context is simpler here.
    if not context.args:
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(context, "GMUTE_USAGE", user_id=user.id),
        )
        return

    # Expected arguments: target_identifier [duration] [reason...]
    target_identifier = context.args[0]
    duration_str = (context.args[1] if len(context.args) > 1 else "0")  # Default to permanent mute
    reason = (" ".join(context.args[2:])
              if len(context.args) > 2 else await get_language_string(context, "GMUTE_DEFAULT_REASON", user_id=user.id))

    # Resolve target identifier to user ID using cached helper (uses is_real_telegram_user_cached which uses get_chat_mb)
    target_user_id: Optional[int] = None
    if target_identifier.startswith("@"):
        resolved_id, is_bot = await is_real_telegram_user_cached(context,
                                                                 target_identifier)  # Use cached helper (uses _mb)
        if resolved_id and not is_bot:  # Don't gmute bots
            target_user_id = resolved_id
            logger.debug(f"Resolved username '{target_identifier}' to user ID {target_user_id}.")
        elif resolved_id and is_bot:
            await send_message_safe(
                context,
                chat.id if chat else user.id,
                await get_language_string(context, "CANNOT_ACTION_BOT", user_id=user.id),
            )  # Need pattern
            return

    elif target_identifier.isdigit():
        target_user_id = int(target_identifier)
        # Optional: Verify if this ID is a real user/bot using get_chat_mb if needed, but not strictly necessary for API call.
        # is_real check is more for usernames.
        try:
            target_chat_info = await get_chat_mb(context.bot, target_user_id)  # Use _mb
            if target_chat_info and target_chat_info.type == TGChat.BOT:
                await send_message_safe(
                    context,
                    chat.id if chat else user.id,
                    await get_language_string(context, "CANNOT_ACTION_BOT", user_id=user.id),
                )
                return
        except Exception:
            logger.debug(f"Could not verify if ID {target_user_id} is a bot via get_chat_mb.")

    if not target_user_id:
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(
                context,
                "USER_NOT_FOUND_MESSAGE",
                user_id=user.id,
                identifier=target_identifier,
            ),
        )
        return

    duration_seconds = parse_duration(duration_str)  # Use parse_duration (Part 2)
    if duration_seconds is None:
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(
                context,
                "INVALID_DURATION_FORMAT_MESSAGE",
                user_id=user.id,
                duration_str=duration_str,
            ),
        )
        return

    # Prevent Super Admins from gmute/gban each other or self.
    if target_user_id in AUTHORIZED_USERS:
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(context, "CANNOT_ACTION_SUPER_ADMIN", user_id=user.id),
        )
        return

    # Do not allow muting the bot itself
    if target_user_id == context.bot.id:
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(context, "CANNOT_ACTION_BOT_SELF", user_id=user.id),
        )  # Need pattern
        return

    # Get all groups from DB
    all_groups = await get_all_groups_from_db()  # Uses db_fetchall (Part 2)
    if not all_groups:
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(context, "GMUTE_NO_GROUPS", user_id=user.id),
        )
        return

    # Send initial status message (using send_message_safe which uses _mb)
    status_message = await send_message_safe(
        context,
        chat.id if chat else user.id,
        await get_language_string(
            context,
            "GMUTE_STARTED",
            user_id=user.id,
            target_user_id=target_user_id,
            count=len(all_groups),
        ),
    )
    original_msg_id = status_message.message_id if status_message else None
    original_chat_id_for_update = (chat.id if chat else user.id)  # Use the chat where command was issued or user's PM

    success_count = 0
    fail_count = 0

    applied_at_iso = datetime.now(timezone.utc).isoformat()
    expires_at_iso: Optional[str] = None
    if duration_seconds > 0:
        expires_at_iso = (datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)).isoformat()

    # mute_permissions_obj is defined globally now (Part 1)
    mute_perms_obj = ChatPermissions(  # Ensure correct mute permissions are used
        can_send_messages=False,
        can_send_audios=False,
        can_send_documents=False,
        can_send_photos=False,
        can_send_videos=False,
        can_send_video_notes=False,
        can_send_voice_notes=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
        can_change_info=False,
        can_invite_users=False,
        can_pin_messages=False,
        can_manage_topics=False,
    )

    # Iterate through groups and attempt to mute
    # For GMUTE, we perform the action directly in the command handler's async scope.
    # For very large numbers of groups, a background task might be better, but direct iteration is common.
    # The plan did mention a background task helper (_perform_bulk_unrestrict_operation_task) - that's for UNMUTEALL/GUNMUTEALL.
    # Let's stick to direct iteration for GMUTE/GBAN as per initial logic, but use _mb wrappers.

    for i, group_id in enumerate(all_groups):
        if SHUTTING_DOWN:
            logger.warning("GMUTE operation interrupted due to shutdown.")
            break
        try:
            # Check if bot has restrict permissions in this group using get_chat_member_mb
            bot_member = await get_chat_member_mb(context.bot, group_id, context.bot.id)  # Use _mb version
            if bot_member and getattr(bot_member, "can_restrict_members", False):
                # Use restrict_chat_member_mb to mute
                success = await restrict_chat_member_mb(
                    context.bot,  # Pass the primary bot
                    chat_id=group_id,
                    user_id=target_user_id,
                    permissions=mute_perms_obj,  # Use the defined mute permissions object
                    until_date=((datetime.now(timezone.utc) +
                                 timedelta(seconds=duration_seconds)) if duration_seconds > 0 else None),
                )
                if success:
                    # Log to bot_restrictions for this group and user
                    await db_execute(
                        """INSERT OR REPLACE INTO bot_restrictions (user_id, chat_id, restriction_type, applied_at, expires_at, is_active, reason, applied_by_admin_id)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(user_id, chat_id, restriction_type, is_active) WHERE is_active = 1 DO UPDATE SET
                           applied_at = excluded.applied_at, expires_at = excluded.expires_at, reason = excluded.reason, applied_by_admin_id = excluded.applied_by_admin_id""",
                        (
                            target_user_id,
                            group_id,
                            "mute",
                            applied_at_iso,
                            expires_at_iso,
                            1,
                            reason[:1000],
                            user.id,
                        ),  # reason limited, applied_by super admin
                    )
                    success_count += 1
                    logger.debug(f"Gmuted user {target_user_id} in group {group_id}.")
                else:
                    fail_count += 1  # API call failed after _mb retries/fallbacks
                    logger.warning(f"Failed to gmute {target_user_id} in group {group_id} via restrict_chat_member_mb.")

            else:
                # Bot lacks permissions in this group
                fail_count += 1
                logger.warning(f"Bot lacks restrict permissions in group {group_id} to gmute user {target_user_id}.")
        except (Exception) as e:  # Catch any unexpected errors not handled by _mb wrappers
            logger.warning(f"Unexpected error attempting to gmute {target_user_id} in group {group_id}: {e}")
            fail_count += 1

        await asyncio.sleep(BROADCAST_SLEEP_INTERVAL)  # Delay between API calls

        # Update status message periodically (using edit_message_text_mb)
        if (original_msg_id and original_chat_id_for_update and (i + 1) % 10 == 0 or
                (i + 1) == len(all_groups)):  # Update every 10 groups or on last
            progress_text = f"Processed {i+1}/{len(all_groups)} groups. Success: {success_count}, Failed: {fail_count}."
            try:
                # Use edit_message_text_mb
                await edit_message_text_mb(
                    context.bot,
                    text=await get_language_string(
                        context,
                        "GMUTE_STARTED",
                        user_id=user.id,
                        target_user_id=target_user_id,
                        count=len(all_groups),
                    ) + "\n" + progress_text,
                    chat_id=original_chat_id_for_update,
                    message_id=original_msg_id,
                )
            except Exception:
                pass  # Ignore edit errors

    # Send final completion message (using send_message_safe which uses _mb)
    final_message_text = await get_language_string(
        context,
        "GMUTE_COMPLETED",
        user_id=user.id,
        target_user_id=target_user_id,
        success_count=success_count,
        fail_count=fail_count,
        total_groups=len(all_groups),
    )

    if original_msg_id and original_chat_id_for_update:
        try:
            # Edit the initial status message to the final summary (using edit_message_text_mb)
            await edit_message_text_mb(
                context.bot,
                text=final_message_text,
                chat_id=original_chat_id_for_update,
                message_id=original_msg_id,
                reply_markup=None,
            )  # Remove any potential reply markup
        except Exception as e:
            logger.error(f"Failed to edit final status message for GMUTE in chat {original_chat_id_for_update}: {e}")
            # If edit fails, send as a new message (using send_message_safe)
            await send_message_safe(context, original_chat_id_for_update, final_message_text)
    else:
        # If initial status message wasn't sent (e.g., failed), send the final message as a new one.
        await send_message_safe(context, chat.id if chat else user.id, final_message_text)

    logger.info(
        f"GMUTE operation for user {target_user_id} completed by {user.id}. Success: {success_count}, Failed: {fail_count}."
    )


@feature_controlled("gban")
async def gban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Globally bans a user from all groups the bot is an admin in."""
    user = update.effective_user
    chat = update.effective_chat  # Command issuer's chat
    command_name = "gban"

    if not user or not await _is_super_admin(user.id):
        # Use send_message_safe (which uses the multi-bot version)
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(context, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", user_id=user.id),
        )
        return

    if not context.args:
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(context, "GBAN_USAGE", user_id=user.id),
        )
        return

    # Expected arguments: target_identifier [reason...]
    target_identifier = context.args[0]
    reason = (" ".join(context.args[1:])
              if len(context.args) > 1 else await get_language_string(context, "GBAN_DEFAULT_REASON", user_id=user.id))

    # Resolve target identifier to user ID using cached helper (uses is_real_telegram_user_cached which uses get_chat_mb)
    target_user_id: Optional[int] = None
    if target_identifier.startswith("@"):
        resolved_id, is_bot = await is_real_telegram_user_cached(context,
                                                                 target_identifier)  # Use cached helper (uses _mb)
        if resolved_id and not is_bot:  # Don't gban bots
            target_user_id = resolved_id
            logger.debug(f"Resolved username '{target_identifier}' to user ID {target_user_id}.")
        elif resolved_id and is_bot:
            await send_message_safe(
                context,
                chat.id if chat else user.id,
                await get_language_string(context, "CANNOT_ACTION_BOT", user_id=user.id),
            )
            return

    elif target_identifier.isdigit():
        target_user_id = int(target_identifier)
        # Optional: Verify if this ID is a real user/bot using get_chat_mb if needed
        try:
            target_chat_info = await get_chat_mb(context.bot, target_user_id)  # Use _mb
            if target_chat_info and target_chat_info.type == TGChat.BOT:
                await send_message_safe(
                    context,
                    chat.id if chat else user.id,
                    await get_language_string(context, "CANNOT_ACTION_BOT", user_id=user.id),
                )
                return
        except Exception:
            logger.debug(f"Could not verify if ID {target_user_id} is a bot via get_chat_mb.")

    if not target_user_id:
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(
                context,
                "USER_NOT_FOUND_MESSAGE",
                user_id=user.id,
                identifier=target_identifier,
            ),
        )
        return

    # Prevent Super Admins from gmute/gban each other or self.
    if target_user_id in AUTHORIZED_USERS:
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(context, "CANNOT_ACTION_SUPER_ADMIN", user_id=user.id),
        )
        return

    # Do not allow banning the bot itself
    if target_user_id == context.bot.id:
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(context, "CANNOT_ACTION_BOT_SELF", user_id=user.id),
        )
        return

    # Get all groups from DB
    all_groups = await get_all_groups_from_db()  # Uses db_fetchall (Part 2)
    if not all_groups:
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(context, "GBAN_NO_GROUPS", user_id=user.id),
        )
        return

    # Send initial status message (using send_message_safe which uses _mb)
    status_message = await send_message_safe(
        context,
        chat.id if chat else user.id,
        await get_language_string(
            context,
            "GBAN_STARTED",
            user_id=user.id,
            target_user_id=target_user_id,
            count=len(all_groups),
        ),
    )
    original_msg_id = status_message.message_id if status_message else None
    original_chat_id_for_update = (chat.id if chat else user.id)  # Use the chat where command was issued or user's PM

    success_count = 0
    fail_count = 0
    applied_at_iso = datetime.now(timezone.utc).isoformat()

    # Iterate through groups and attempt to ban
    for i, group_id in enumerate(all_groups):
        if SHUTTING_DOWN:
            logger.warning("GBAN operation interrupted due to shutdown.")
            break
        try:
            # Check if bot has ban permissions in this group using get_chat_member_mb
            bot_member = await get_chat_member_mb(context.bot, group_id, context.bot.id)  # Use _mb version
            if bot_member and getattr(bot_member, "can_ban_members", False):
                # Use ban_chat_member_mb to ban
                success = await ban_chat_member_mb(context.bot, chat_id=group_id,
                                                   user_id=target_user_id)  # Use _mb, default ban is permanent
                if success:
                    # Log to bot_restrictions for this group and user
                    await db_execute(
                        """INSERT OR REPLACE INTO bot_restrictions (user_id, chat_id, restriction_type, applied_at, expires_at, is_active, reason, applied_by_admin_id)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(user_id, chat_id, restriction_type, is_active) WHERE is_active = 1 DO UPDATE SET
                           applied_at = excluded.applied_at, expires_at = excluded.expires_at, reason = excluded.reason, applied_by_admin_id = excluded.applied_by_admin_id""",
                        (
                            target_user_id,
                            group_id,
                            "ban",
                            applied_at_iso,
                            None,
                            1,
                            reason[:1000],
                            user.id,
                        ),  # reason limited, applied_by super admin
                    )
                    success_count += 1
                    logger.debug(f"Gbanned user {target_user_id} in group {group_id}.")
                else:
                    fail_count += 1  # API call failed after _mb retries/fallbacks
                    logger.warning(f"Failed to gban {target_user_id} in group {group_id} via ban_chat_member_mb.")
            else:
                # Bot lacks permissions in this group
                fail_count += 1
                logger.warning(f"Bot lacks ban permissions in group {group_id} to gban user {target_user_id}.")
        except (Exception) as e:  # Catch any unexpected errors not handled by _mb wrappers
            logger.warning(f"Unexpected error attempting to gban {target_user_id} in group {group_id}: {e}")
            fail_count += 1

        await asyncio.sleep(BROADCAST_SLEEP_INTERVAL)  # Delay between API calls

        # Update status message periodically (using edit_message_text_mb)
        if (original_msg_id and original_chat_id_for_update and (i + 1) % 10 == 0 or
                (i + 1) == len(all_groups)):  # Update every 10 groups or on last
            progress_text = f"Processed {i+1}/{len(all_groups)} groups. Success: {success_count}, Failed: {fail_count}."
            try:
                # Use edit_message_text_mb
                await edit_message_text_mb(
                    context.bot,
                    text=await get_language_string(
                        context,
                        "GBAN_STARTED",
                        user_id=user.id,
                        target_user_id=target_user_id,
                        count=len(all_groups),
                    ) + "\n" + progress_text,
                    chat_id=original_chat_id_for_update,
                    message_id=original_msg_id,
                )
            except Exception:
                pass  # Ignore edit errors

    # Send final completion message (using send_message_safe which uses _mb)
    final_message_text = await get_language_string(
        context,
        "GBAN_COMPLETED",
        user_id=user.id,
        target_user_id=target_user_id,
        success_count=success_count,
        fail_count=fail_count,
        total_groups=len(all_groups),
    )

    if original_msg_id and original_chat_id_for_update:
        try:
            # Edit the initial status message to the final summary (using edit_message_text_mb)
            await edit_message_text_mb(
                context.bot,
                text=final_message_text,
                chat_id=original_chat_id_for_update,
                message_id=original_msg_id,
                reply_markup=None,
            )  # Remove any potential reply markup
        except Exception as e:
            logger.error(f"Failed to edit final status message for GBAN in chat {original_chat_id_for_update}: {e}")
            # If edit fails, send as a new message (using send_message_safe)
            await send_message_safe(context, original_chat_id_for_update, final_message_text)
    else:
        # If initial status message wasn't sent (e.g., failed), send the final message as a new one.
        await send_message_safe(context, chat.id if chat else user.id, final_message_text)

    logger.info(
        f"GBAN operation for user {target_user_id} completed by {user.id}. Success: {success_count}, Failed: {fail_count}."
    )


# --- Bulk Unmute/Unban Background Task Helper ---
# This task performs the actual API calls for bulk operations (/unmuteall, /gunmuteall, /unbanall, /gunbanall)


async def _perform_bulk_unrestrict_operation_task(
        # Pass necessary data, avoid passing full context directly if it's not pickleable by create_task
        application: Application,  # Pass the Application instance to get bot object
        chat_id_to_operate_in: int,
        user_ids_to_process: List[int],  # IDs of users potentially affected
        operation_name: str,  # e.g., "UnmuteAll", "GUnmuteAll", "UnbanAll", "GUnbanAll"
        initiating_admin_id: int,  # ID of the admin who started the task
        target_bot_only_setting: bool,  # True if only restrictions by this bot instance should be targeted
        restriction_type_to_target: str,  # 'mute' or 'ban'
        original_message_id_to_update: Optional[int] = None,  # For status updates message ID
        original_chat_id_for_update: Optional[int] = None,  # Chat ID for status updates message
):
    """
    Background task for bulk unmuting/unbanning users in a specific chat.
    Iterates through potential users and attempts to unrestrict them based on settings.
    """
    # Ensure bot instance is available from the application
    bot = application.bot
    if not bot:
        logger.error(f"{operation_name}: Could not get bot instance from application for background task. Aborting.")
        # Cannot update status message here easily.
        return

    unrestricted_count = 0
    failed_count = 0
    skipped_count = 0  # Users skipped because they weren't restricted in the target way

    # Determine language context for the task (using the initiating admin's language or target chat language)
    # For simplicity, let's try to use the language of the chat where the update message was, or the admin's lang.
    # Creating a dummy context-like object might be needed for await get_language_string inside a task.
    # Or, pass the language code explicitly to the task.
    # For now, will use await get_language_string with chat_id=original_chat_id_for_update or user_id=initiating_admin_id
    # It requires DB access which is async, might be slow, or use the cached language from settings/chat_data/user_data
    # Since this is a task, it might not have the original update/context objects readily available.
    # Let's rely on await get_language_string's ability to fetch from DB if context is None.

    # Determine correct language string keys based on operation type
    status_text_key_progress = ("BULK_UNMUTE_PROGRESS"
                                if restriction_type_to_target == "mute" else "BULK_UNBAN_PROGRESS")
    status_text_key_complete = ("BULK_UNMUTE_COMPLETE"
                                if restriction_type_to_target == "mute" else "BULK_UNBAN_COMPLETE")
    operation_display_name = ("unmute" if restriction_type_to_target == "mute" else "unban")

    total_to_process = len(user_ids_to_process)

    logger.info(
        f"Background task '{operation_name}' started for chat {chat_id_to_operate_in} by admin {initiating_admin_id}. Processing {total_to_process} potential users. Target bot restrictions only: {target_bot_only_setting}"
    )

    # Check bot's permissions once before the loop for the target chat
    bot_can_act = False
    required_permission = ("can_restrict_members" if restriction_type_to_target == "mute" else "can_ban_members")
    try:
        bot_member_in_target_chat = await get_chat_member_mb(bot, chat_id_to_operate_in, bot.id)  # Use _mb
        if bot_member_in_target_chat and (bot_member_in_target_chat.status == ChatMemberStatus.OWNER or
                                          getattr(bot_member_in_target_chat, required_permission, False)):
            bot_can_act = True
    # Catch specific API errors that get_chat_member_mb might not suppress completely
    except (Forbidden, BadRequest):
        logger.warning(
            f"Task '{operation_name}': Bot lacks perms or not in chat {chat_id_to_operate_in}. API check failed.")
        bot_can_act = False  # Cannot proceed without knowing perms
    except Exception as e:
        logger.error(
            f"Task '{operation_name}': Unexpected error checking bot perms in {chat_id_to_operate_in}: {e}",
            exc_info=True,
        )
        bot_can_act = False

    if not bot_can_act:
        logger.error(
            f"Task '{operation_name}': Bot lacks necessary permissions ({required_permission}) or is not in chat {chat_id_to_operate_in}. Aborting task."
        )
        # Update status message to reflect abortion due to permissions
        if original_message_id_to_update and original_chat_id_for_update:
            abort_message = await get_language_string(
                None,
                "BULK_OP_ABORTED_NO_PERMS",  # Need pattern
                chat_id=original_chat_id_for_update,
                user_id=initiating_admin_id,
                operation_type=operation_display_name,
                group_id_display=chat_id_to_operate_in,
            )
            # Use edit_message_text_mb
            await edit_message_text_mb(
                bot,
                text=abort_message,
                chat_id=original_chat_id_for_update,
                message_id=original_message_id_to_update,
            )
        return  # Stop the task

    # Define appropriate permissions object for unmuting
    # unmute_permissions object is defined globally (Part 1)

    for i, user_id in enumerate(user_ids_to_process):
        if SHUTTING_DOWN:
            logger.warning(f"{operation_name}: Shutting down, task interrupted.")
            break

        # Check if the user is currently restricted in the target chat with the target type
        # Use get_chat_member_mb to get the user's current status
        current_member_status: Optional[ChatMember] = None
        try:
            # Pass the bot object to get_chat_member_mb
            current_member_status = await get_chat_member_mb(bot, chat_id_to_operate_in, user_id)  # Use _mb
        except Exception:
            logger.debug(
                f"Task '{operation_name}': Could not get member status for user {user_id} in chat {chat_id_to_operate_in}. Skipping."
            )
            skipped_count += 1
            continue  # Skip this user if status cannot be determined

        is_restricted_as_target = False
        if current_member_status:
            if restriction_type_to_target == "mute":
                # User is muted if status is restricted AND they cannot send messages
                if (current_member_status.status == ChatMemberStatus.RESTRICTED and
                        not current_member_status.can_send_messages):
                    is_restricted_as_target = True
            elif restriction_type_to_target == "ban":
                # User is banned if status is banned
                if current_member_status.status == ChatMemberStatus.BANNED:
                    is_restricted_as_target = True

        if not is_restricted_as_target:
            logger.debug(
                f"Task '{operation_name}': User {user_id} not currently restricted as '{operation_display_name}' in chat {chat_id_to_operate_in}. Skipping."
            )
            skipped_count += 1
            continue  # Skip if user is not currently restricted in the way we're targeting

        # If targeting only bot restrictions, check the bot_restrictions table
        remove_restriction = False
        if target_bot_only_setting:
            # Check if this bot instance applied the active restriction
            restriction_entry = await db_fetchone(
                "SELECT id FROM bot_restrictions WHERE chat_id = ? AND user_id = ? AND restriction_type = ? AND is_active = 1 AND applied_by_admin_id = ?",
                (
                    chat_id_to_operate_in,
                    user_id,
                    restriction_type_to_target,
                    bot.id,
                ),  # Check against current bot's ID
            )
            if restriction_entry:
                remove_restriction = True
            else:
                # User is restricted, but not by this bot instance
                logger.debug(
                    f"Task '{operation_name}': User {user_id} is restricted in {chat_id_to_operate_in}, but not by this bot ({bot.id}). Skipping due to target_bot_only setting."
                )
                skipped_count += 1
                continue  # Skip if not restricted by this bot and target_bot_only is True
        else:
            # Target any user who is currently restricted in the target way (already checked by get_chat_member_mb above)
            remove_restriction = True

        if remove_restriction:
            try:
                success = False
                
                if restriction_type_to_target == "mute":
                    # Use restrict_chat_member_mb to unmute
                    # unmute_permissions object is defined globally (Part 1)
                    success = await restrict_chat_member_mb(
                        bot,
                        chat_id_to_operate_in,
                        user_id,
                        permissions=unmute_permissions,
                    )  # Use _mb
                elif restriction_type_to_target == "ban":
                    # Use unban_chat_member_mb to unban
                    success = await unban_chat_member_mb(bot, chat_id_to_operate_in, user_id,
                                                         only_if_banned=True)  # Use _mb

                if success:
                    unrestricted_count += 1
                    # Update bot_restrictions table to mark any restrictions by this bot as inactive for this user/chat/type
                    # Note: This might deactivate restrictions applied by OTHER bots if target_bot_only_setting is False
                    # and we don't filter by applied_by_admin_id here.
                    # If target_bot_only_setting is False, the bot_restrictions table might not be the source of truth for the restriction.
                    # We should only update records applied by *this* bot instance if target_bot_only_setting is True.
                    # If target_bot_only_setting is False, updating bot_restrictions based on *any* active restriction is complex - maybe log elsewhere?
                    # Sticking to the plan: update bot_restrictions applied by *this* bot instance regardless of the toggle,
                    # but *only attempt the API call* if remove_restriction is True based on the toggle and live status.
                    await db_execute(
                        """UPDATE bot_restrictions SET is_active = 0
                           WHERE chat_id = ? AND user_id = ? AND restriction_type = ? AND applied_by_admin_id = ? AND is_active = 1""",
                        (
                            chat_id_to_operate_in,
                            user_id,
                            restriction_type_to_target,
                            bot.id,
                        ),  # Only deactivate restrictions applied by *this* bot
                    )
                    logger.debug(
                        f"Task '{operation_name}': Successfully unrestricted user {user_id} in chat {chat_id_to_operate_in}."
                    )

                else:
                    # API call failed after _mb retries/fallbacks
                    logger.warning(
                        f"Task '{operation_name}': Failed to unrestrict user {user_id} in chat {chat_id_to_operate_in} via _mb call."
                    )
                    failed_count += 1

            except (Exception) as e:  # Catch any unexpected errors not handled by _mb wrappers
                logger.warning(
                    f"Task '{operation_name}': Unexpected error attempting to unrestrict user {user_id} in chat {chat_id_to_operate_in}: {e}"
                )
                failed_count += 1

        await asyncio.sleep(BROADCAST_SLEEP_INTERVAL)  # API call delay to avoid hitting limits

        # Update status message periodically if message details are available
        if original_message_id_to_update and original_chat_id_for_update:
            processed_count = i + 1
            # Only update if a significant number processed or it's the last user
            if processed_count % 20 == 0 or processed_count == total_to_process:
                progress_text = await get_language_string(
                    None,
                    # No context here, use None; language derived from original_chat_id_for_update/initiating_admin_id in await get_language_string
                    status_text_key_progress,
                    chat_id=original_chat_id_for_update,
                    user_id=initiating_admin_id,
                    processed_count=processed_count,
                    total_count=total_to_process,
                    success_count=unrestricted_count,
                    fail_count=failed_count,
                    skipped_count=skipped_count,
                )
                try:
                    # Use edit_message_text_mb (passing the bot object)
                    await edit_message_text_mb(
                        bot,
                        text=progress_text,
                        chat_id=original_chat_id_for_update,
                        message_id=original_message_id_to_update,
                    )
                except Exception:
                    # Ignore edit errors (e.g., message not found, message not modified)
                    pass  # logger.debug(f"Failed to edit progress message for task {operation_name}.")

    # --- Task Completion ---
    final_status_text = await get_language_string(
        None,
        status_text_key_complete,  # No context, language from chat/user ID
        chat_id=original_chat_id_for_update,
        user_id=initiating_admin_id,
        success_count=unrestricted_count,
        fail_count=failed_count,
        skipped_count=skipped_count,
        total_users=total_to_process,
        operation_type=operation_display_name,
        group_id_display=chat_id_to_operate_in,
    )

    # Update the final status message (using edit_message_text_mb)
    if original_message_id_to_update and original_chat_id_for_update:
        try:
            await edit_message_text_mb(
                bot,
                text=final_status_text,
                chat_id=original_chat_id_for_update,
                message_id=original_message_id_to_update,
                reply_markup=None,
            )  # Remove buttons if any
        except Exception as e:
            logger.error(f"Failed to edit final status for {operation_name} in chat {original_chat_id_for_update}: {e}")
            # If edit fails, send as new message (using send_message_safe, needs application or bot)
            # send_message_safe needs context or application. Let's pass application.
            # send_message_safe signature is `context, chat_id, text...`
            # We need to adjust send_message_safe to accept application, or create a dummy context.
            # Simpler: use send_message_safe_mb directly here passing the bot object.
            await send_message_safe_mb(bot, original_chat_id_for_update, final_status_text)

    else:
        # If no original message to update (e.g. initial send failed), send the final result as a new message
        # Send to the admin who initiated it (user's PM or command chat)
        # Use send_message_safe_mb directly
        await send_message_safe_mb(bot, original_chat_id_for_update or chat_id_to_operate_in,
                                   final_status_text)  # Fallback to group ID if update chat is none

    logger.info(
        f"Background task '{operation_name}' for chat {chat_id_to_operate_in} completed. Unrestricted: {unrestricted_count}, Failed: {failed_count}, Skipped: {skipped_count}"
    )


# main.py - Part 7 of 20

# --- Bulk Unmute/Unban Commands (Initiate Background Task) ---


@feature_controlled("unmuteall")
async def unmuteall_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initiates a bulk unmute operation in the current group."""
    user = update.effective_user
    chat = update.effective_chat
    command_name = "unmuteall"

    if not user or not chat:
        return
    if chat.type not in [TGChat.GROUP, TGChat.SUPERGROUP]:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "COMMAND_GROUP_ONLY_MESSAGE",
                chat_id=chat.id,
                user_id=user.id,
                command_name=command_name,
            ),
        )
        return

    # Check admin status (group admin or super admin)
    # Uses _is_user_group_admin_or_creator which uses get_cached_admins (_mb)
    is_chat_admin_or_super = await _is_user_group_admin_or_creator(context, chat.id, user.id)
    if not is_chat_admin_or_super:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "ADMIN_ONLY_COMMAND_MESSAGE", chat_id=chat.id, user_id=user.id),
        )
        return

    # Rate limit check (per chat, per command)
    # command_cooldown_check_and_update now takes context
    if not await command_cooldown_check_and_update(context, chat.id, user.id, command_name,
                                                   BULK_COMMAND_COOLDOWN_SECONDS):
        # command_cooldown_check_and_update will send the cooldown message internally.
        return

    # Get all users from the database (potential targets)
    # In a group setting, we might want to fetch users who are *currently muted* in THIS group, not all users in the DB.
    # However, the design seems to iterate over ALL users in the DB and then check their status in the target group.
    # This could be inefficient for large user databases. A better approach might be to get muted users *from the group* via API.
    # Telegram API does not provide a direct way to list all muted members.
    # The current approach iterating DB users and checking status via get_chat_member_mb is a workaround.

    # Let's fetch all users from the database as potential targets.
    all_user_ids_in_db = await get_all_users_from_db(
        started_only=False)  # Consider all users known to the bot? Or just those who started?
    # The `_perform_bulk_unrestrict_operation_task` will check the user's *current* status in the target chat.
    # So fetching all users from DB is the intended approach here.

    if not all_user_ids_in_db:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "BULK_UNMUTE_NO_TARGETS",
                chat_id=chat.id,
                user_id=user.id,
                operation_type="unmute",
            ),
        )
        return

    # Send initial status message (using send_message_safe which uses _mb)
    # The status message will be updated by the background task.
    initial_status_text = await get_language_string(
        context,
        "BULK_UNMUTE_STARTED_STATUS",
        chat_id=chat.id,
        user_id=user.id,
        operation_type="unmute",
        group_id_display=chat.title or str(chat.id),
        target_count=len(all_user_ids_in_db),
        target_bot_mutes_only=UNMUTEALL_TARGET_BOT_MUTES_ONLY,
    )  # Indicate the setting

    status_message = await send_message_safe(context, chat.id, initial_status_text)
    original_message_id = status_message.message_id if status_message else None

    logger.info(
        f"Admin {user.id} initiated bulk unmute in group {chat.id} for {len(all_user_ids_in_db)} potential users. Target bot mutes only: {UNMUTEALL_TARGET_BOT_MUTES_ONLY}"
    )

    # Start the background task to perform the operation
    # Pass the application instance, chat ID, user IDs, operation name, admin ID, bot_only setting, and message details
    context.application.create_task(
        _perform_bulk_unrestrict_operation_task(
            context.application,  # Pass application instance
            chat_id_to_operate_in=chat.id,
            user_ids_to_process=all_user_ids_in_db,  # Pass list of IDs
            operation_name="UnmuteAll",
            initiating_admin_id=user.id,
            target_bot_only_setting=UNMUTEALL_TARGET_BOT_MUTES_ONLY,
            restriction_type_to_target="mute",
            original_message_id_to_update=original_message_id,
            original_chat_id_for_update=chat.id,
        ))


@feature_controlled("gunmuteall")
async def gunmuteall_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initiates a global bulk unmute operation across all known groups."""
    user = update.effective_user
    chat = update.effective_chat  # Command issuer's chat
    command_name = "gunmuteall"

    if not user or not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(context, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", user_id=user.id),
        )
        return

    # Rate limit check (per super admin, global context)
    # Use user.id as chat_id for global command context
    cooldown_chat_id_context = user.id

    # command_cooldown_check_and_update now takes context
    if not await command_cooldown_check_and_update(
            context,
            cooldown_chat_id_context,
            user.id,
            command_name,
            BULK_COMMAND_COOLDOWN_SECONDS,
    ):
        # command_cooldown_check_and_update will send the cooldown message internally (if in a chat).
        # If in PM, send explicitly.
        if chat.type == TGChat.PRIVATE:
            remaining_cooldown = BULK_COMMAND_COOLDOWN_SECONDS  # Simplified
            await send_message_safe(
                context,
                user.id,
                await get_language_string(
                    context,
                    "COMMAND_COOLDOWN_MESSAGE",
                    user_id=user.id,
                    duration=format_duration(remaining_cooldown),
                ),
            )  # Need precise duration from cooldown func
        return

    # Get all groups from DB
    all_groups = await get_all_groups_from_db()  # Uses db_fetchall (Part 2)
    if not all_groups:
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(
                context,
                "BULK_UNMUTE_NO_GROUPS_GLOBAL",
                user_id=user.id,
                operation_type="unmute",
            ),
        )
        return

    # Get all users from DB (potential targets)
    all_user_ids_in_db = await get_all_users_from_db(started_only=False)  # Consider all users known to the bot?
    if not all_user_ids_in_db:
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(
                context,
                "BULK_UNMUTE_NO_TARGETS",
                user_id=user.id,
                operation_type="unmute",
            ),
        )  # Re-use no targets pattern
        return

    # Send initial status message (using send_message_safe which uses _mb)
    initial_status_text = await get_language_string(
        context,
        "BULK_UNMUTE_STARTED_GLOBAL_STATUS",
        user_id=user.id,  # Use user ID for language context
        group_count=len(all_groups),
    )

    status_message = await send_message_safe(context, chat.id if chat else user.id, initial_status_text)
    original_message_id = status_message.message_id if status_message else None
    original_chat_id_for_update = (chat.id if chat else user.id)  # Use the chat where command was issued or user's PM

    logger.info(
        f"Super admin {user.id} initiated global bulk unmute across {len(all_groups)} groups for {len(all_user_ids_in_db)} potential users. Target bot mutes only: {GUNMUTEALL_TARGET_BOT_MUTES_ONLY}"
    )

    # Dispatch background tasks for each group
    dispatched_count = 0
    for group_id in all_groups:
        if SHUTTING_DOWN:
            logger.warning("GUNMUTEALL operation interrupted due to shutdown, stopping task dispatch.")
            break

        # Create a separate task for each group's bulk operation
        # Pass the application instance for the task to access bots
        context.application.create_task(
            _perform_bulk_unrestrict_operation_task(
                context.application,  # Pass application instance
                chat_id_to_operate_in=group_id,
                user_ids_to_process=all_user_ids_in_db,  # Pass the full list of potential user IDs to each task
                operation_name=f"GUnmuteAll (Group {group_id})",  # Specific name for logging
                initiating_admin_id=user.id,
                target_bot_only_setting=GUNMUTEALL_TARGET_BOT_MUTES_ONLY,
                restriction_type_to_target="mute",
                # No message ID update per group for global command status - the initial message confirms dispatch
                original_message_id_to_update=None,
                original_chat_id_for_update=None,
            ))
        dispatched_count += 1

        # Optional: slight delay between dispatching tasks
        # await asyncio.sleep(0.1) # Maybe not necessary, create_task is fast

    # Send completion message indicating tasks are dispatched
    final_message_text = await get_language_string(
        context,
        "BULK_UNMUTE_ALL_TASKS_DISPATCHED_GLOBAL",
        user_id=user.id,  # Use user ID for language context
        group_count=dispatched_count,
        operation_type="unmute",
    )

    # Use edit_message_text_mb to update the initial status message
    if original_message_id and original_chat_id_for_update:
        try:
            await edit_message_text_mb(
                context.bot,
                text=final_message_text,
                chat_id=original_chat_id_for_update,
                message_id=original_message_id,
                reply_markup=None,
            )  # Remove any potential reply markup
        except Exception as e:
            logger.error(
                f"Failed to edit final dispatch status message for GUNMUTEALL in chat {original_chat_id_for_update}: {e}"
            )
            # If edit fails, send as a new message (using send_message_safe)
            await send_message_safe(context, original_chat_id_for_update, final_message_text)
    else:
        # If initial status message wasn't sent, send the final message as a new one.
        await send_message_safe(context, chat.id if chat else user.id, final_message_text)

    logger.info(f"Super admin {user.id} dispatched global bulk unmute tasks for {dispatched_count} groups.")


@feature_controlled("unbanall")
async def unbanall_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initiates a bulk unban operation in the current group."""
    user = update.effective_user
    chat = update.effective_chat
    command_name = "unbanall"

    if not user or not chat:
        return
    if chat.type not in [TGChat.GROUP, TGChat.SUPERGROUP]:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "COMMAND_GROUP_ONLY_MESSAGE",
                chat_id=chat.id,
                user_id=user.id,
                command_name=command_name,
            ),
        )
        return

    # Check admin status (group admin or super admin)
    is_chat_admin_or_super = await _is_user_group_admin_or_creator(context, chat.id,
                                                                   user.id)  # Uses get_cached_admins (_mb)
    if not is_chat_admin_or_super:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "ADMIN_ONLY_COMMAND_MESSAGE", chat_id=chat.id, user_id=user.id),
        )
        return

    # Rate limit check (per chat, per command)
    # command_cooldown_check_and_update now takes context
    if not await command_cooldown_check_and_update(context, chat.id, user.id, command_name,
                                                   BULK_COMMAND_COOLDOWN_SECONDS):
        # command_cooldown_check_and_update will send the cooldown message internally.
        return

    # Get all users from the database (potential targets)
    all_user_ids_in_db = await get_all_users_from_db(started_only=False)  # Consider all users known to the bot?
    # The `_perform_bulk_unrestrict_operation_task` will check the user's *current* status in the target group.
    # Fetching all users from DB is the intended approach here.

    if not all_user_ids_in_db:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "BULK_UNBAN_NO_TARGETS",
                chat_id=chat.id,
                user_id=user.id,
                operation_type="unban",
            ),
        )
        return

    # Send initial status message (using send_message_safe which uses _mb)
    initial_status_text = await get_language_string(
        context,
        "BULK_UNBAN_STARTED_STATUS",
        chat_id=chat.id,
        user_id=user.id,
        operation_type="unban",
        group_id_display=chat.title or str(chat.id),
        target_count=len(all_user_ids_in_db),
        target_bot_mutes_only=UNBANALL_TARGET_BOT_BANS_ONLY,
    )  # Indicate the setting

    status_message = await send_message_safe(context, chat.id, initial_status_text)
    original_message_id = status_message.message_id if status_message else None

    logger.info(
        f"Admin {user.id} initiated bulk unban in group {chat.id} for {len(all_user_ids_in_db)} potential users. Target bot bans only: {UNBANALL_TARGET_BOT_BANS_ONLY}"
    )

    # Start the background task to perform the operation
    # Pass the application instance, chat ID, user IDs, operation name, admin ID, bot_only setting, and message details
    context.application.create_task(
        _perform_bulk_unrestrict_operation_task(
            context.application,  # Pass application instance
            chat_id_to_operate_in=chat.id,
            user_ids_to_process=all_user_ids_in_db,  # Pass list of IDs
            operation_name="UnbanAll",
            initiating_admin_id=user.id,
            target_bot_only_setting=UNBANALL_TARGET_BOT_BANS_ONLY,
            restriction_type_to_target="ban",
            original_message_id_to_update=original_message_id,
            original_chat_id_for_update=chat.id,
        ))


@feature_controlled("gunbanall")
async def gunbanall_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initiates a global bulk unban operation across all known groups."""
    user = update.effective_user
    chat = update.effective_chat  # Command issuer's chat
    command_name = "gunbanall"

    if not user or not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(context, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", user_id=user.id),
        )
        return

    # Rate limit check (per super admin, global context)
    # Use user.id as chat_id for global command context
    cooldown_chat_id_context = user.id

    # command_cooldown_check_and_update now takes context
    if not await command_cooldown_check_and_update(
            context,
            cooldown_chat_id_context,
            user.id,
            command_name,
            BULK_COMMAND_COOLDOWN_SECONDS,
    ):
        # command_cooldown_check_and_update will send the cooldown message internally (if in a chat).
        # If in PM, send explicitly.
        if chat.type == TGChat.PRIVATE:
            remaining_cooldown = BULK_COMMAND_COOLDOWN_SECONDS  # Simplified
            await send_message_safe(
                context,
                user.id,
                await get_language_string(
                    context,
                    "COMMAND_COOLDOWN_MESSAGE",
                    user_id=user.id,
                    duration=format_duration(remaining_cooldown),
                ),
            )
        return

    # Get all groups from DB
    all_groups = await get_all_groups_from_db()  # Uses db_fetchall (Part 2)
    if not all_groups:
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(
                context,
                "BULK_UNBAN_NO_GROUPS_GLOBAL",
                user_id=user.id,
                operation_type="unban",
            ),
        )
        return

    # Get all users from DB (potential targets)
    all_user_ids_in_db = await get_all_users_from_db(started_only=False)  # Consider all users known to the bot?
    if not all_user_ids_in_db:
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(
                context,
                "BULK_UNBAN_NO_TARGETS",
                user_id=user.id,
                operation_type="unban",
            ),
        )  # Re-use no targets pattern
        return

    # Send initial status message (using send_message_safe which uses _mb)
    initial_status_text = await get_language_string(
        context,
        "BULK_UNBAN_STARTED_GLOBAL_STATUS",
        user_id=user.id,  # Use user ID for language context
        group_count=len(all_groups),
    )

    status_message = await send_message_safe(context, chat.id if chat else user.id, initial_status_text)
    original_message_id = status_message.message_id if status_message else None
    original_chat_id_for_update = (chat.id if chat else user.id)  # Use the chat where command was issued or user's PM

    logger.info(
        f"Super admin {user.id} initiated global bulk unban across {len(all_groups)} groups for {len(all_user_ids_in_db)} potential users. Target bot bans only: {GUNBANALL_TARGET_BOT_BANS_ONLY}"
    )

    # Dispatch background tasks for each group
    dispatched_count = 0
    for group_id in all_groups:
        if SHUTTING_DOWN:
            logger.warning("GUNBANALL operation interrupted due to shutdown, stopping task dispatch.")
            break

        # Create a separate task for each group's bulk operation
        # Pass the application instance for the task to access bots
        context.application.create_task(
            _perform_bulk_unrestrict_operation_task(
                context.application,  # Pass application instance
                chat_id_to_operate_in=group_id,
                user_ids_to_process=all_user_ids_in_db,  # Pass the full list of potential user IDs to each task
                operation_name=f"GUnbanAll (Group {group_id})",  # Specific name for logging
                initiating_admin_id=user.id,
                target_bot_only_setting=GUNBANALL_TARGET_BOT_BANS_ONLY,
                restriction_type_to_target="ban",
                # No message ID update per group for global command status - the initial message confirms dispatch
                original_message_id_to_update=None,
                original_chat_id_for_update=None,
            ))
        dispatched_count += 1

        # Optional: slight delay between dispatching tasks
        # await asyncio.sleep(0.1) # Maybe not necessary, create_task is fast

    # Send completion message indicating tasks are dispatched
    final_message_text = await get_language_string(
        context,
        "BULK_UNBAN_ALL_TASKS_DISPATCHED_GLOBAL",
        user_id=user.id,  # Use user ID for language context
        group_count=dispatched_count,
        operation_type="unban",
    )

    # Use edit_message_text_mb to update the initial status message
    if original_message_id and original_chat_id_for_update:
        try:
            await edit_message_text_mb(
                context.bot,
                text=final_message_text,
                chat_id=original_chat_id_for_update,
                message_id=original_message_id,
                reply_markup=None,
            )  # Remove any potential reply markup
        except Exception as e:
            logger.error(
                f"Failed to edit final dispatch status message for GUNBANALL in chat {original_chat_id_for_update}: {e}"
            )
            # If edit fails, send as a new message (using send_message_safe)
            await send_message_safe(context, original_chat_id_for_update, final_message_text)
    else:
        # If initial status message wasn't sent, send the final message as a new one.
        await send_message_safe(context, chat.id if chat else user.id, final_message_text)

    logger.info(f"Super admin {user.id} dispatched global bulk unban tasks for {dispatched_count} groups.")

# Reload functions 
async def reload_admin_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type not in ("group", "supergroup"):
        await update.message.reply_text(
            await patterns.get_language_string(chat_id, "GROUP_ONLY_COMMAND")
        )
        return

    # Check rate limit (per-group)
    cooldown_seconds = ADMIN_CACHE_REFRESH_COOLDOWN_SECONDS
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute(
            "SELECT last_used_timestamp FROM command_cooldowns WHERE chat_id = ? AND command_name = ?",
            (chat_id, "reload")
        )
        row = await cursor.fetchone()
        if row:
            last_used = float(row[0])
            if time.time() - last_used < cooldown_seconds:
                await update.message.reply_text(
                    await patterns.get_language_string(chat_id, "COOLDOWN_MESSAGE",
                        seconds=int(cooldown_seconds - (time.time() - last_used))
                    )
                )
                return

        # Update cooldown
        await db.execute(
            "INSERT OR REPLACE INTO command_cooldowns (chat_id, user_id, command_name, last_used_timestamp) VALUES (?, ?, ?, ?)",
            (chat_id, 0, "reload", time.time())  # user_id=0 for per-group cooldown
        )
        await db.commit()

    # Refresh group admin cache
    try:
        await refresh_admin_cache(context.bot, chat_id)
        await update.message.reply_text(
            await patterns.get_language_string(chat_id, "RELOAD_COMMAND")
        )
    except TelegramError as e:
        logger.error(f"Error refreshing admin cache for chat {chat_id}: {e}")
        await update.message.reply_text(
            await patterns.get_language_string(chat_id, "ERROR_MESSAGE")
        )

async def greload_admin_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # Restrict to superadmins
    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text(
            await patterns.get_language_string(chat_id, "UNAUTHORIZED_MESSAGE")
        )
        return

    # Determine cooldown key (per-group or global)
    cooldown_key = chat_id if update.effective_chat.type in ("group", "supergroup") else 0
    cooldown_name = "greload"

    # Check rate limit
    cooldown_seconds = ADMIN_CACHE_REFRESH_COOLDOWN_SECONDS
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute(
            "SELECT last_used_timestamp FROM command_cooldowns WHERE chat_id = ? AND command_name = ?",
            (cooldown_key, cooldown_name)
        )
        row = await cursor.fetchone()
        if row:
            last_used = float(row[0])
            if time.time() - last_used < cooldown_seconds:
                await update.message.reply_text(
                    await patterns.get_language_string(chat_id, "COOLDOWN_MESSAGE",
                        seconds=int(cooldown_seconds - (time.time() - last_used))
                    )
                )
                return

        # Update cooldown
        await db.execute(
            "INSERT OR REPLACE INTO command_cooldowns (chat_id, user_id, command_name, last_used_timestamp) VALUES (?, ?, ?, ?)",
            (cooldown_key, 0, cooldown_name, time.time())  # user_id=0 for per-group/global cooldown
        )
        await db.commit()

    # Refresh all groups
    try:
        await refresh_all_admin_caches(context.bot)
        await update.message.reply_text(
            await patterns.get_language_string(chat_id, "GRELOAD_COMMAND")
        )
    except Exception as e:
        logger.error(f"Error refreshing all admin caches: {e}")
        await update.message.reply_text(
            await patterns.get_language_string(chat_id, "ERROR_MESSAGE")
        )

async def has_admin_privileges(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is an admin."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if chat_id in context.bot_data.get("admin_cache", {}):
        return user_id in context.bot_data["admin_cache"][chat_id]
    try:
        admins = await rate_limited_api_call(context.bot.get_chat_administrators, chat_id)
        context.bot_data.setdefault("admin_cache", {})[chat_id] = [admin.user.id for admin in admins]
        return user_id in context.bot_data["admin_cache"][chat_id]
    except telegram.error.TelegramError:
        return False

async def refresh_admin_cache(bot, chat_id):
    try:
        admins = await get_chat_safe_administrators(chat_id)
        async with aiosqlite.connect(DATABASE_NAME) as db:
            for admin in admins:
                await db.execute(
                    """
                    INSERT OR REPLACE INTO group_admin_log
                    (chat_id, user_id, changer_user_id, old_status, new_status, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (chat_id, admin.user.id, None, None, admin.status, datetime.datetime.now().isoformat())
                )
            await db.commit()
    except TelegramError as e:
        logger.error(f"Failed to refresh admin cache for chat {chat_id}: {e}")
        raise

async def refresh_all_admin_caches(bot):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("SELECT group_id FROM groups")
        groups = await cursor.fetchall()
        for (group_id,) in groups:
            try:
                await refresh_admin_cache(bot, group_id)
            except TelegramError:
                logger.warning(f"Skipped refreshing admin cache for group {group_id} due to error.")
                continue

# gunmute and gunban command 

async def ungmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    args = context.args

    # Check superadmin
    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text(
            await patterns.get_language_string(chat_id, "UNAUTHORIZED_MESSAGE")
        )
        return

    # Validate target user
    if not args:
        await update.message.reply_text(
            await patterns.get_language_string(chat_id, "NO_USER_PROVIDED")
        )
        return

    target_user_id = None
    target_input = args[0].lstrip("@")
    if target_input.isdigit():
        target_user_id = int(target_input)
    elif target_input in username_to_id_cache:
        target_user_id = username_to_id_cache[target_input]
    else:
        async with aiosqlite.connect(DATABASE_NAME) as db:
            cursor = await db.execute(
                "SELECT user_id FROM users WHERE username = ?",
                (f"@{target_input}",)
            )
            row = await cursor.fetchone()
            if row:
                target_user_id = row[0]
                username_to_id_cache[target_input] = target_user_id

    if not target_user_id:
        await update.message.reply_text(
            await patterns.get_language_string(chat_id, "INVALID_USER")
        )
        return

    # Remove global and group-specific mutes
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Get all known groups
        cursor = await db.execute("SELECT group_id FROM groups")
        groups = await cursor.fetchall()
        group_ids = [group_id for (group_id,) in groups]

        # Delete global mute
        await db.execute(
            "DELETE FROM restrictions WHERE user_id = ? AND action_type = ? AND is_global = ?",
            (target_user_id, "mute", 1)
        )

        # Delete group-specific mutes in known groups
        if group_ids:
            await db.execute(
                f"DELETE FROM restrictions WHERE user_id = ? AND action_type = ? AND is_global = ? AND chat_id IN ({','.join('?' * len(group_ids))})",
                [target_user_id, "mute", 0] + group_ids
            )

        # Log action
        await db.execute(
            "INSERT INTO action_log (chat_id, user_id, target_user_id, action_type, timestamp) VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, target_user_id, "ungmute", datetime.datetime.now().isoformat())
        )
        await db.commit()

    await update.message.reply_text(
        await patterns.get_language_string(chat_id, "UNGMUTE_COMMAND", user_id=target_user_id)
    )

async def ungban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    args = context.args

    # Check superadmin
    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text(
            await patterns.get_language_string(chat_id, "UNAUTHORIZED_MESSAGE")
        )
        return

    # Validate target user
    if not args:
        await update.message.reply_text(
            await patterns.get_language_string(chat_id, "NO_USER_PROVIDED")
        )
        return

    target_user_id = None
    target_input = args[0].lstrip("@")
    if target_input.isdigit():
        target_user_id = int(target_input)
    elif target_input in username_to_id_cache:
        target_user_id = username_to_id_cache[target_input]
    else:
        async with aiosqlite.connect(DATABASE_NAME) as db:
            cursor = await db.execute(
                "SELECT user_id FROM users WHERE username = ?",
                (f"@{target_input}",)
            )
            row = await cursor.fetchone()
            if row:
                target_user_id = row[0]
                username_to_id_cache[target_input] = target_user_id

    if not target_user_id:
        await update.message.reply_text(
            await patterns.get_language_string(chat_id, "INVALID_USER")
        )
        return

    # Remove global and group-specific bans
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Get all known groups
        cursor = await db.execute("SELECT group_id FROM groups")
        groups = await cursor.fetchall()
        group_ids = [group_id for (group_id,) in groups]

        # Delete global ban
        await db.execute(
            "DELETE FROM restrictions WHERE user_id = ? AND action_type = ? AND is_global = ?",
            (target_user_id, "ban", 1)
        )

        # Delete group-specific bans in known groups
        if group_ids:
            await db.execute(
                f"DELETE FROM restrictions WHERE user_id = ? AND action_type = ? AND is_global = ? AND chat_id IN ({','.join('?' * len(group_ids))})",
                [target_user_id, "ban", 0] + group_ids
            )

        # Log action
        await db.execute(
            "INSERT INTO action_log (chat_id, user_id, target_user_id, action_type, timestamp) VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, target_user_id, "ungban", datetime.datetime.now().isoformat())
        )
        await db.commit()

    await update.message.reply_text(
        await patterns.get_language_string(chat_id, "UNGBAN_COMMAND", user_id=target_user_id)
    )

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # Check superadmin
    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text(
            await patterns.get_language_string(chat_id, "UNAUTHORIZED_MESSAGE")
        )
        return

    # Check if a bulk command is running
    if chat_id not in bulk_command_state:
        await update.message.reply_text(
            await patterns.get_language_string(chat_id, "NO_BULK_COMMAND")
        )
        return

    # Cancel the bulk command
    bulk_command_state[chat_id]["cancelled"] = True
    command_name = bulk_command_state[chat_id]["command"]
    del bulk_command_state[chat_id]

    await update.message.reply_text(
        await patterns.get_language_string(chat_id, "CANCEL_COMMAND", command=command_name)
    )
# Global state for bulk command cancellation
bulk_command_state = {}  # {chat_id: {"command": str, "cancelled": bool}}

async def ungmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    args = context.args

    # Check superadmin
    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text(
            await patterns.get_language_string(chat_id, "UNAUTHORIZED_MESSAGE")
        )
        return

    # Validate target user
    if not args:
        await update.message.reply_text(
            await patterns.get_language_string(chat_id, "NO_USER_PROVIDED")
        )
        return

    target_user_id = None
    target_input = args[0].lstrip("@")
    if target_input.isdigit():
        target_user_id = int(target_input)
    elif target_input in username_to_id_cache:
        target_user_id = username_to_id_cache[target_input]
    else:
        async with aiosqlite.connect(DATABASE_NAME) as db:
            cursor = await db.execute(
                "SELECT user_id FROM users WHERE username = ?",
                (f"@{target_input}",)
            )
            row = await cursor.fetchone()
            if row:
                target_user_id = row[0]
                username_to_id_cache[target_input] = target_user_id

    if not target_user_id:
        await update.message.reply_text(
            await patterns.get_language_string(chat_id, "INVALID_USER")
        )
        return

    # Remove global and group-specific mutes
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Get all known groups
        cursor = await db.execute("SELECT group_id FROM groups")
        groups = await cursor.fetchall()
        group_ids = [group_id for (group_id,) in groups]

        # Delete global mute
        await db.execute(
            "DELETE FROM restrictions WHERE user_id = ? AND action_type = ? AND is_global = ?",
            (target_user_id, "mute", 1)
        )

        # Delete group-specific mutes in known groups
        if group_ids:
            await db.execute(
                f"DELETE FROM restrictions WHERE user_id = ? AND action_type = ? AND is_global = ? AND chat_id IN ({','.join('?' * len(group_ids))})",
                [target_user_id, "mute", 0] + group_ids
            )

        # Log action
        await db.execute(
            "INSERT INTO action_log (chat_id, user_id, target_user_id, action_type, timestamp) VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, target_user_id, "ungmute", datetime.datetime.now().isoformat())
        )
        await db.commit()

    await update.message.reply_text(
        await patterns.get_language_string(chat_id, "UNGMUTE_COMMAND", user_id=target_user_id)
    )

async def ungban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    args = context.args

    # Check superadmin
    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text(
            await patterns.get_language_string(chat_id, "UNAUTHORIZED_MESSAGE")
        )
        return

    # Validate target user
    if not args:
        await update.message.reply_text(
            await patterns.get_language_string(chat_id, "NO_USER_PROVIDED")
        )
        return

    target_user_id = None
    target_input = args[0].lstrip("@")
    if target_input.isdigit():
        target_user_id = int(target_input)
    elif target_input in username_to_id_cache:
        target_user_id = username_to_id_cache[target_input]
    else:
        async with aiosqlite.connect(DATABASE_NAME) as db:
            cursor = await db.execute(
                "SELECT user_id FROM users WHERE username = ?",
                (f"@{target_input}",)
            )
            row = await cursor.fetchone()
            if row:
                target_user_id = row[0]
                username_to_id_cache[target_input] = target_user_id

    if not target_user_id:
        await update.message.reply_text(
            await patterns.get_language_string(chat_id, "INVALID_USER")
        )
        return

    # Remove global and group-specific bans
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Get all known groups
        cursor = await db.execute("SELECT group_id FROM groups")
        groups = await cursor.fetchall()
        group_ids = [group_id for (group_id,) in groups]

        # Delete global ban
        await db.execute(
            "DELETE FROM restrictions WHERE user_id = ? AND action_type = ? AND is_global = ?",
            (target_user_id, "ban", 1)
        )

        # Delete group-specific bans in known groups
        if group_ids:
            await db.execute(
                f"DELETE FROM restrictions WHERE user_id = ? AND action_type = ? AND is_global = ? AND chat_id IN ({','.join('?' * len(group_ids))})",
                [target_user_id, "ban", 0] + group_ids
            )

        # Log action
        await db.execute(
            "INSERT INTO action_log (chat_id, user_id, target_user_id, action_type, timestamp) VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, target_user_id, "ungban", datetime.datetime.now().isoformat())
        )
        await db.commit()

    await update.message.reply_text(
        await patterns.get_language_string(chat_id, "UNGBAN_COMMAND", user_id=target_user_id)
    )

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # Check superadmin
    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text(
            await patterns.get_language_string(chat_id, "UNAUTHORIZED_MESSAGE")
        )
        return

    # Check if a bulk command is running
    if chat_id not in bulk_command_state:
        await update.message.reply_text(
            await patterns.get_language_string(chat_id, "NO_BULK_COMMAND")
        )
        return

    # Cancel the bulk command
    bulk_command_state[chat_id]["cancelled"] = True
    command_name = bulk_command_state[chat_id]["command"]
    del bulk_command_state[chat_id]

    await update.message.reply_text(
        await patterns.get_language_string(chat_id, "CANCEL_COMMAND", command=command_name)
    )

# Error handler


async def on_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.error("Update '%s' caused error '%s'", update, context.error, exc_info=context.error)

    # Optional: Send a message to a super admin about the error
    # This can be helpful for critical errors, but be mindful of potential spam
    # if errors are frequent.

    # Get the first authorized user's ID from config
    super_admin_id = AUTHORIZED_USERS[0] if AUTHORIZED_USERS else None

    if super_admin_id:
        error_message = (f"An error occurred while processing an update:\n"
                         f"Error: `{context.error}`\n"
                         f"Update: `{update}`")
        # Truncate the message if it's too long for a Telegram message
        if len(error_message) > 4000:
            error_message = error_message[:3900] + "\n... (truncated)"

        try:
            # Use send_message_safe which handles potential API errors and uses multi-bot
            await send_message_safe(
                context,  # Use the context from the error handler
                super_admin_id,
                error_message,
                parse_mode=ParseMode.MARKDOWN_V2,  # Use MarkdownV2 for formatting the error details
            )
            logger.debug(f"Sent error notification to super admin {super_admin_id}.")
        except Exception as e:
            # Log if sending the error notification fails
            logger.error(f"Failed to send error notification to super admin {super_admin_id}: {e}")

from cachetools import TTLCache

# Rate limit cache (chat_id -> timestamp)
reload_rate_limit_cache = TTLCache(maxsize=int(config.get("Cache", "MaxSize", fallback=1024)), ttl=ADMIN_CACHE_REFRESH_COOLDOWN)

async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Refresh the admin list for the current group with rate limiting."""
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user or chat.type not in (TGChat.GROUP, TGChat.SUPERGROUP):
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(context, "GROUP_ONLY_COMMAND", user_id=user.id),
        )
        return

    chat_id = chat.id
    user_id = user.id

    # Check rate limit
    if chat_id in reload_rate_limit_cache:
        await send_message_safe(
            context,
            chat_id,
            await get_language_string(
                context,
                "RELOAD_RATE_LIMITED",
                user_id=user_id,
                seconds=ADMIN_CACHE_REFRESH_COOLDOWN,
            ),
        )
        return

    # Check admin privileges (exclude super admins unless global)
    is_super_admin = await _is_super_admin(user_id)
    is_admin = await has_admin_privileges(update, context)
    if not is_admin or (is_super_admin and not config.getboolean("Admin", "SuperAdminsAreGlobalAdmins", fallback=True)):
        await send_message_safe(
            context,
            chat_id,
            await get_language_string(context, "ADMIN_ONLY_COMMAND", user_id=user_id),
        )
        return

    logger.info(f"Reload initiated by user {user_id} in group {chat_id}")

    # Refresh admin list
    try:
        admins = await rate_limited_api_call(context.bot.get_chat_administrators, chat_id)
        context.bot_data.setdefault("admin_cache", {})[chat_id] = [admin.user.id for admin in admins]
        logger.debug(f"Updated admin cache for group {chat_id}: {context.bot_data['admin_cache'][chat_id]}")
    except telegram.error.TelegramError as e:
        logger.error(f"Failed to refresh admins in group {chat_id}: {e}")
        await send_message_safe(
            context,
            chat_id,
            await get_language_string(context, "RELOAD_FAILED", user_id=user_id),
        )
        return

    # Clear pending batch operations
    try:
        with sqlite3.connect(DATABASE_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pending_batch_ops WHERE chat_id = ?", (chat_id,))
            conn.commit()
            logger.debug(f"Cleared pending batch operations for group {chat_id}")
    except sqlite3.Error as e:
        logger.error(f"Database error clearing pending ops in group {chat_id}: {e}")

    # Set rate limit
    reload_rate_limit_cache[chat_id] = True

    await send_message_safe(
        context,
        chat_id,
        await get_language_string(context, "RELOAD_SUCCESS", user_id=user_id),
    )

# --- Standard Command Handlers ---


@feature_controlled("start")
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command in private chat or groups."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        logger.warning("No user or chat in start_command")
        return

    # Add user to DB and mark as started
    asyncio.create_task(
        add_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=getattr(user, "last_name", ""),
            has_started_bot=True,
        )
    )
    asyncio.create_task(mark_user_started_bot(user.id))

    # Parse start payload (e.g., from "Unmute Me" button)
    start_payload = context.args[0] if context.args else None

    if start_payload and start_payload.startswith("unmuteme_"):
        try:
            group_id_str = start_payload.split("_")[1]
            target_group_id = int(group_id_str)
            logger.info(f"User {user.id} started bot with unmute payload for group {target_group_id}")

            # Check profile issues
            has_profile_issue, problematic_field, _ = await user_has_links_cached(context, user.id)
            if has_profile_issue:
                msg = await get_language_string(
                    context,
                    "UNMUTE_ME_PROFILE_ISSUE_PM",
                    user_id=user.id,
                    field=problematic_field or "unknown",
                )
                await send_message_safe(
                    context,
                    chat.id,
                    msg,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                return

            # Check channel subscription
            if settings.get("channel_id"):
                is_subbed = await is_user_subscribed(context, user.id, chat_id_for_pm_guidance=user.id)
                if not is_subbed:
                    channel_link = settings.get("channel_invite_link") or f"Channel ID: {settings.get('channel_id')}"
                    msg = await get_language_string(
                        context,
                        "UNMUTE_ME_CHANNEL_ISSUE_PM",
                        user_id=user.id,
                        channel_link=channel_link,
                    )
                    await send_message_safe(
                        context,
                        chat.id,
                        msg,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                    )
                    return

            # Inform user about unmute process
            unmute_info_msg = await get_language_string(
                context,
                "UNMUTE_ME_START_PAYLOAD_INFO",
                user_id=user.id,
                group_id=target_group_id,
            )

            # Check for active mutes by this bot
            muted_in_chats = await db_fetchall(
                "SELECT id FROM bot_restrictions WHERE user_id = ? AND restriction_type = 'mute' AND is_active = 1 AND applied_by_admin_id = ?",
                (user.id, context.bot.id),
            )
            reply_markup = None
            if muted_in_chats:
                button_text = await get_language_string(context, "UNMUTE_ME_ALL_BOT_MUTES_BUTTON", user_id=user.id)
                reply_markup = InlineKeyboardMarkup(
                    [[InlineKeyboardButton(button_text, callback_data="unmute_me_all_bot_mutes")]]
                )

            await send_message_safe(context, chat.id, unmute_info_msg, reply_markup=reply_markup)

        except (ValueError, IndexError) as e:
            logger.warning(f"User {user.id} used /start with invalid unmute payload: {start_payload}, error: {e}")

    # Standard /start handling
    if chat.type == ChatType.PRIVATE:
        await send_private_start_message(update, context)
    else:
        await send_group_start_message(update, context)

async def send_private_start_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends the start message in private chat."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    # Standard welcome message
    bot_username = (await get_bot_username(context) or "your_bot")  # Uses get_chat_mb (_mb)
    welcome_message = await get_language_string(
        context,
        "START_MESSAGE_PRIVATE_BASE",
        user_id=user.id,
        bot_username=bot_username,
    )

    # Add buttons: Language, Help, Add to Group (if bot is not in too many groups?), Join Channel (if set)
    keyboard: List[List[InlineKeyboardButton]] = []

    # Language button
    lang_button_text = await get_language_string(context, "LANG_BUTTON_SELECT_LANGUAGE", user_id=user.id)
    keyboard.append([InlineKeyboardButton(lang_button_text,
                                          callback_data=f"{LANG_CALLBACK_PREFIX}page_0")])  # Start with page 0

    # Help button (links to command list or help text)
    # For PM, maybe a link to a help page or just text?
    # Let's provide a basic text help prompt, /help command should provide detailed list in groups.
    help_button_text = await get_language_string(context, "HELP_BUTTON_TEXT", user_id=user.id)
    # This could be a callback query or a URL if hosted help is available.
    # Let's make it a callback to trigger help text in PM for now.
    keyboard.append([InlineKeyboardButton(help_button_text,
                                          callback_data="show_pm_help")])  # Need handler for "show_pm_help"

    # "Add bot to group" button (if bot is not already in too many groups)
    # Check if the bot is already added to a reasonable number of groups (optional limit based on API calls/DB size)
    # Getting total group count might be slow. Skip this check for now or make it a config setting.
    # If we decide to limit, get_all_groups_count() is available (uses db_fetchone, Part 2)
    bot_username = await get_bot_username(context)  # Ensure username is fetched again
    if bot_username:
        add_to_group_button_text = await get_language_string(
            context,
            "ADD_BOT_TO_GROUP_BUTTON_TEXT",
            user_id=user.id,
            bot_username=bot_username,
        )
        # Link format: https://t.me/{bot_username}?startgroup=true
        add_to_group_url = f"https://t.me/{bot_username}?startgroup=true"
        keyboard.append([InlineKeyboardButton(add_to_group_button_text, url=add_to_group_url)])

    # "Unmute Me From All Bot Mutes" button
    # Only show if the user has any active mutes by this bot instance
    muted_in_chats = await db_fetchall(
        "SELECT id FROM bot_restrictions WHERE user_id = ? AND restriction_type = 'mute' AND is_active = 1 AND applied_by_admin_id = ?",
        (user.id, context.bot.id),  # Check against current bot's ID
    )
    if muted_in_chats:
        unmute_me_button_text = await get_language_string(context, "UNMUTE_ME_ALL_BOT_MUTES_BUTTON", user_id=user.id)
        # The callback data should trigger the handle_unmute_me_button_all logic
        keyboard.append([InlineKeyboardButton(unmute_me_button_text,
                                              callback_data="unmute_me_all_bot_mutes")])  # Use defined callback data

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Use send_message_safe (which uses the multi-bot version)
    await send_message_safe(
        context,
        chat.id,
        welcome_message,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def send_group_start_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends the start message in a group chat."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    # Add group to DB if not exists - fire and forget
    asyncio.create_task(
        add_group(
            chat.id,
            chat.title or f"Group {chat.id}",
            added_at=datetime.now(timezone.utc).isoformat(),
        ))

    # Send welcome message in group
    bot_username = (await get_bot_username(context) or "your_bot")  # Uses get_chat_mb (_mb)
    welcome_message = await get_language_string(
        context,
        "START_MESSAGE_GROUP",
        chat_id=chat.id,
        user_id=user.id,
        bot_username=bot_username,
    )

    # Add buttons: Language, Help, Join Channel (if set)
    keyboard: List[List[InlineKeyboardButton]] = []

    # Language button (for admins to set group language)
    # Only show if user is admin, or always show and check admin status on callback?
    # Let's show and check admin status on callback.
    lang_button_text = await get_language_string(context,
                                                 "LANG_BUTTON_SELECT_LANGUAGE",
                                                 chat_id=chat.id,
                                                 user_id=user.id)
    keyboard.append([InlineKeyboardButton(lang_button_text, callback_data=f"{LANG_CALLBACK_PREFIX}page_0")])

    # Help button (directs to /help command)
    help_button_text = await get_language_string(context, "HELP_BUTTON_TEXT", chat_id=chat.id, user_id=user.id)
    # This should likely trigger the /help command handler for this chat.
    # A callback query could trigger a dummy message with instructions, or edit the current message.
    # Let's make it a callback that triggers the /help command functionality within the group.
    # Need a handler for the callback data, which then calls the /help command logic.
    keyboard.append([InlineKeyboardButton(help_button_text,
                                          callback_data="show_group_help")])  # Need handler for "show_group_help"

    # Join Channel button (if channel is configured)
    if settings.get("channel_id"):
        channel_link = settings.get("channel_invite_link")
        if channel_link:
            join_channel_button_text = await get_language_string(
                context,
                "JOIN_VERIFICATION_CHANNEL_BUTTON_TEXT",
                chat_id=chat.id,
                user_id=user.id,
            )
            keyboard.append([InlineKeyboardButton(join_channel_button_text, url=channel_link)])

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Use send_message_safe (which uses the multi-bot version)
    await send_message_safe(
        context,
        chat.id,
        welcome_message,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


# Handler for the "show_pm_help" callback from PM start
async def handle_show_pm_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat if query.message else None

    if not user or not query or not chat or chat.type != TGChat.PRIVATE:
        return
    await query.answer()  # Acknowledge button press

    # Send the PM help message (could be a static text or generated list of PM commands)
    # Need a language string for PM help.
    help_text_pm = await get_language_string(
        context, "HELP_MESSAGE_PM",
        user_id=user.id)  # Need pattern like "Available commands in private chat: /start, /help, /unmuteme [group_id]"

    # Use edit_message_text_mb to edit the message that had the button, showing help text
    try:
        await edit_message_text_mb(
            context.bot,
            text=help_text_pm,
            chat_id=chat.id,
            message_id=query.message.message_id,
            parse_mode=ParseMode.HTML,  # Use HTML if help text has formatting
            reply_markup=None,
        )  # Remove buttons
    except Exception as e:
        logger.error(f"Failed to edit message to show PM help for user {user.id}: {e}")
        # Send as a new message if editing fails
        await send_message_safe(context, chat.id, help_text_pm, parse_mode=ParseMode.HTML)


# Handler for the "show_group_help" callback from group start
async def handle_show_group_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat if query.message else None

    if not user or not query or not chat or chat.type == TGChat.PRIVATE:
        return
    await query.answer()  # Acknowledge button press

    # Trigger the /help command logic for this chat
    help_prompt_text = await get_language_string(context, "START_MESSAGE_HELP_PROMPT", chat_id=chat.id, user_id=user.id)

    # Use edit_message_text_mb to edit the message that had the button, showing the prompt
    try:
        await edit_message_text_mb(
            context.bot,
            text=help_prompt_text,
            chat_id=chat.id,
            message_id=query.message.message_id,
            reply_markup=None,
        )  # Remove buttons
    except Exception as e:
        logger.error(f"Failed to edit message to show group help prompt for user {user.id} in chat {chat.id}: {e}")
        # Send as a new message if editing fails
        await send_message_safe(context, chat.id, help_prompt_text)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.error:
        logger.warning("Error handler triggered with no error in context")
        return
    logger.error(f"Update {update} caused error: {context.error}", exc_info=True)
    admin_chat_id = context.bot_data.get("settings", {}).get("admin_chat_id")
    if admin_chat_id:
        try:
            error_msg = await get_language_string(
                context,
                "BOT_ERROR_NOTIFICATION",
                error=str(context.error),
                update=str(update)[:100],
            )
            await send_message_safe(
                context,
                chat_id=admin_chat_id,
                text=error_msg,
                parse_mode=ParseMode.HTML,
            )
            logger.info(f"Notified admin chat {admin_chat_id} of error")
        except Exception as e:
            logger.error(f"Failed to notify admin chat {admin_chat_id}: {e}")
            
# Placeholder for check_for_links_enhanced - defined in Part 6
# async def check_for_links_enhanced(...): ...

# main.py - Part 8 of 20


@feature_controlled("help")
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /help command in groups (admin only) or private (all users)."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    is_super_admin = user.id in AUTHORIZED_USERS
    is_group_admin = False

    if chat.type != TGChat.PRIVATE:
        # In groups, only admins can see the full help
        # Uses _is_user_group_admin_or_creator which uses get_cached_admins (_mb)
        is_group_admin = await _is_user_group_admin_or_creator(context, chat.id, user.id)
        if not is_group_admin and not is_super_admin:
            await send_message_safe(
                context,
                chat.id,
                await get_language_string(
                    context,
                    "ADMIN_ONLY_COMMAND_MESSAGE",
                    chat_id=chat.id,
                    user_id=user.id,
                ),
            )
            return

    # Determine help message based on context (PM or group) and admin status
    help_message_key = ("HELP_MESSAGE_PM" if chat.type == TGChat.PRIVATE else "HELP_MESSAGE_GROUP_ADMIN"
                        )  # Need group admin help pattern

    # Need to define HELP_MESSAGE_PM and HELP_MESSAGE_GROUP_ADMIN patterns with command lists
    # Example: patterns.py could have HELP_MESSAGE_PM = "Available commands: /start, /help, /unmuteme [group_id]"
    # Example: patterns.py could have HELP_MESSAGE_GROUP_ADMIN = "Admin commands: /mute, /ban, /kick, /unmuteall, /banall, /reload, /lang"

    help_text = await get_language_string(context, help_message_key, chat_id=chat.id, user_id=user.id)

    # For super admins, maybe add global commands or a separate super admin help section?
    if is_super_admin:
        help_text += "\n\n" + await get_language_string(
            context, "HELP_MESSAGE_SUPER_ADMIN", chat_id=chat.id, user_id=user.id)  # Need pattern for super admin help

    # Use send_message_safe (which uses the multi-bot version)
    await send_message_safe(
        context,
        chat.id,
        help_text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


@feature_controlled("status")
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /status command (admin only) to show bot status and stats."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    is_super_admin = user.id in AUTHORIZED_USERS
    is_group_admin = False

    if chat.type != TGChat.PRIVATE:
        # In groups, only admins can see status
        is_group_admin = await _is_user_group_admin_or_creator(context, chat.id,
                                                               user.id)  # Uses get_cached_admins (_mb)

    if not is_group_admin and not is_super_admin:
        # In PM, any user can see basic status? Or only super admins? Let's say only super admins for full status.
        if chat.type == TGChat.PRIVATE:
            if not is_super_admin:
                await send_message_safe(
                    context,
                    chat.id,
                    await get_language_string(context, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", user_id=user.id),
                )
                return
        else:  # In group, not admin/super admin
            await send_message_safe(
                context,
                chat.id,
                await get_language_string(
                    context,
                    "ADMIN_ONLY_COMMAND_MESSAGE",
                    chat_id=chat.id,
                    user_id=user.id,
                ),
            )
            return

    # Gather status information
    uptime = time.time() - bot_start_time
    uptime_formatted = format_duration(int(uptime))  # Uses format_duration (Part 2)

    # Database stats (counts)
    group_count = await get_all_groups_count()  # Uses db_fetchone (Part 2)
    user_count_total = await get_all_users_count(started_only=False)  # Uses db_fetchone (Part 2)
    user_count_started = await get_all_users_count(started_only=True)  # Uses db_fetchone (Part 2)
    bad_actor_count = await db_fetchone("SELECT COUNT(*) FROM bad_actors")  # Uses db_fetchone (Part 2)
    bad_actor_count = bad_actor_count[0] if bad_actor_count else 0

    # Active restrictions count
    active_mutes_count = await db_fetchone(
        "SELECT COUNT(*) FROM bot_restrictions WHERE restriction_type = 'mute' AND is_active = 1")
    active_mutes_count = active_mutes_count[0] if active_mutes_count else 0
    active_bans_count = await db_fetchone(
        "SELECT COUNT(*) FROM bot_restrictions WHERE restriction_type = 'ban' AND is_active = 1")
    active_bans_count = active_bans_count[0] if active_bans_count else 0

    # Cache stats
    user_profile_cache_size = len(user_profile_cache) if user_profile_cache else 0
    username_to_id_cache_size = len(username_to_id_cache) if username_to_id_cache else 0
    admin_cache_size = len(admin_cache)

    # Memory usage (approximate - requires 'psutil' if available, otherwise basic)
    try:
        import psutil

        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        memory_usage_mb = mem_info.rss / (1024 * 1024)  # Resident Set Size
        memory_usage_str = f"{memory_usage_mb:.2f} MB"
    except ImportError:
        memory_usage_str = "N/A (install 'psutil' for details)"
    except Exception as e:
        memory_usage_str = f"Error: {e}"

    # Job Queue stats (if available)
    jobs_info = "N/A (JobQueue not available)"
    if context.application.job_queue:
        all_jobs = context.application.job_queue.get_all_jobs()
        job_names = [job.name for job in all_jobs]
        jobs_info = f"{len(all_jobs)} active jobs: {', '.join(job_names)}"

    # Multi-bot status
    primary_bot_id = context.bot.id
    active_bot_ids = [app.bot.id for app in applications if app.running]
    bot_status_str = f"Primary: {primary_bot_id}. Active: {', '.join(map(str, active_bot_ids))}. Configured: {len(BOT_TOKENS)}"

    # Feature Control Status
    # Fetch all feature states (requires iterating feature_control table)
    feature_states = {}
    try:
        rows = await db_fetchall("SELECT feature_name, is_enabled FROM feature_control")
        for row in rows:
            feature_states[row["feature_name"]] = ("Enabled" if row["is_enabled"] else "Disabled")
    except Exception as e:
        logger.error(f"Error fetching feature states for status command: {e}", exc_info=True)
        feature_states["Database Error"] = str(e)

    # Construct the status message
    status_text = await get_language_string(
        context,
        "STATUS_MESSAGE_TEMPLATE",
        chat_id=chat.id,
        user_id=user.id,  # Need pattern
        uptime=uptime_formatted,
        group_count=group_count,
        user_count_total=user_count_total,
        user_count_started=user_count_started,
        bad_actor_count=bad_actor_count,
        active_mutes_count=active_mutes_count,
        active_bans_count=active_bans_count,
        user_profile_cache_size=user_profile_cache_size,
        username_to_id_cache_size=username_to_id_cache_size,
        admin_cache_size=admin_cache_size,
        memory_usage=memory_usage_str,
        jobs_info=jobs_info,
        bot_status=bot_status_str,
        maintenance_mode=MAINTENANCE_MODE,
        db_name=DATABASE_NAME,
        log_path=LOG_FILE_PATH or "Console Only",
        log_level=LOG_LEVEL,
        config_file=CONFIG_FILE_NAME,
    )

    # Append feature states
    status_text += "\n\n<b>Feature Status:</b>\n"  # Need pattern
    if feature_states:
        for feature, state in feature_states.items():
            status_text += f"- {feature}: {state}\n"
    else:
        status_text += "No feature states found in DB.\n"

    # Use send_message_safe (which uses the multi-bot version)
    await send_message_safe(context, chat.id, status_text, parse_mode=ParseMode.HTML)


# --- Content Scanning Helper ---


# check_for_links_enhanced is used by handle_message (Part 5) and user_has_links_cached (Part 4)
from typing import Tuple, Optional
from telegram.ext import ContextTypes
import patterns  # Assuming patterns.py exists
from logging import getLogger

logger = getLogger(__name__)

from telegram.ext import ContextTypes
from typing import Tuple, Optional
import patterns

# Replace in main.py
async def check_for_links_enhanced(
    context: ContextTypes.DEFAULT_TYPE, 
    text: str, 
    source_field: str
) -> Tuple[bool, Optional[str]]:
    from patterns import (
        PROHIBITED_LINKS, PROHIBITED_URL_PATTERNS, PROHIBITED_KEYWORDS,
        SUSPICIOUS_PATTERNS, FAST_PAYOUT_KEYWORDS, FAST_PAYOUT_REGEX, BOT_MENTION_PATTERN
    )
    
    if not text:
        return False, None

    try:
        # Check prohibited links
        for link in PROHIBITED_LINKS:
            if link.lower() in text.lower():
                logger.debug(f"Found prohibited link '{link}' in {source_field}")
                return True, "forbidden_link"

        # Check URL patterns
        for pattern in PROHIBITED_URL_PATTERNS:
            if pattern.search(text):
                logger.debug(f"Found URL pattern '{pattern.pattern}' in {source_field}")
                return True, "forbidden_url_pattern"

        # Check keywords
        for keyword in PROHIBITED_KEYWORDS:
            if keyword.lower() in text.lower():
                logger.debug(f"Found keyword '{keyword}' in {source_field}")
                return True, "prohibited_keyword"

        # Check suspicious patterns
        for pattern in SUSPICIOUS_PATTERNS:
            if pattern.search(text):
                logger.debug(f"Found suspicious pattern '{pattern.pattern}' in {source_field}")
                return True, "suspicious_pattern"

        # Check fast payout keywords and regex
        if any(keyword.lower() in text.lower() for keyword in FAST_PAYOUT_KEYWORDS):
            logger.debug(f"Found fast payout keyword in {source_field}")
            return True, "fast_payout_keyword"
        if FAST_PAYOUT_REGEX.search(text):
            logger.debug(f"Found fast payout regex match in {source_field}")
            return True, "fast_payout_pattern"

        # Check bot mentions
        if BOT_MENTION_PATTERN.search(text):
            logger.debug(f"Found bot mention in {source_field}")
            return True, "bot_mention"

        return False, None
    except Exception as e:
        logger.error(f"Error checking {source_field}: {e}", exc_info=True)
        return False, None

  # --- STUBS TO SATISFY MISSING CALLS ----------------

async def check_message_content(update, context, text: str):
    """
    Stub for the content‐checking pipeline.
    The real logic is in check_for_links_enhanced(), etc.,
    so here we just delegate and ignore the result.
    """
    # if you want to re-use your existing enhanced checker:
    try:
        # check_for_links_enhanced returns (bool, reason_key)
        flagged, reason = await check_for_links_enhanced(context, text, "message")
        if flagged:
            # if you need to take immediate action, do it here,
            # or simply log it and return:
            logging.getLogger(__name__).warning(f"Content flagged: {reason}")
    except NameError:
        # no checker available, silently continue
        pass
    return  # never raise


async def check_new_member(context, chat_id, member):
    """
    Stub for the new-member profile check.
    Delegates to your internal _check_new_member_profile_and_act if you want,
    or simply returns so you don’t get a NameError.
    """
    try:
        # if you want full logic, you can call:
        await _check_new_member_profile_and_act(None, context, member, 
                                                patterns.NEW_MEMBER_PUNISH_ACTION, 
                                                patterns.NEW_MEMBER_PUNISH_DURATION_SECONDS)
    except Exception:
        # swallow all errors so the bot keeps running
        pass
    return
# ---------------------------------------------------      
# --- Scheduled Tasks ---


async def load_and_schedule_timed_broadcasts(application: Application):
    try:
        broadcasts = await get_all_timed_broadcasts_from_db()
        if not broadcasts:
            logger.info("No timed broadcasts found in database to schedule.")
            return
        for broadcast in broadcasts:
            job_name = broadcast['job_name']
            target_type = broadcast['target_type']
            message_text = broadcast['message_text']
            interval_seconds = broadcast['interval_seconds']
            first_run_time = broadcast['first_run_time']
            # Parse first_run_time if it's a string
            if isinstance(first_run_time, str):
                first_run_time = datetime.fromisoformat(first_run_time.replace('Z', '+00:00')).timestamp()
            # Skip if job already scheduled
            if application.job_queue.get_jobs_by_name(job_name):
                logger.warning(f"Job {job_name} already scheduled, skipping.")
                continue
            application.job_queue.run_repeating(
                timed_broadcast_job_callback,
                interval=interval_seconds,
                first=max(0, first_run_time - time.time()),
                data={
                    'target_type': target_type,
                    'message_text': message_text,
                },
                name=job_name,
            )
            settings["active_timed_broadcasts"][job_name] = True
            logger.info(f"Scheduled timed broadcast '{job_name}' for {target_type} every {interval_seconds}s.")
    except Exception as e:
        logger.error(f"Error loading timed broadcasts: {e}", exc_info=True)
        
from datetime import datetime, timezone
from telegram.ext import ContextTypes

async def deactivate_expired_restrictions_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deactivates expired bot restrictions in the database."""
    logger.info("Running job: Deactivating expired restrictions...")
    if db_pool is None:
        logger.error("Cannot deactivate expired restrictions: db_pool is None")
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        async with db_pool.execute(
            """
            SELECT id, user_id, chat_id, restriction_type
            FROM bot_restrictions
            WHERE is_active = 1 AND expires_at IS NOT NULL AND expires_at < ?
            """,
            (now_iso,),
        ) as cursor:
            expired_restrictions = await cursor.fetchall()

        if expired_restrictions:
            logger.info(f"Found {len(expired_restrictions)} expired restrictions to deactivate.")
            ids_to_deactivate = [row["id"] for row in expired_restrictions]
            await db_pool.execute(
                f"UPDATE bot_restrictions SET is_active = 0 WHERE id IN ({','.join('?' for _ in ids_to_deactivate)})",
                ids_to_deactivate,
            )
            logger.info(f"Deactivated {len(ids_to_deactivate)} expired restrictions.")
        else:
            logger.debug("No expired restrictions found to deactivate.")
    except Exception as e:
        logger.error(f"Error in deactivate_expired_restrictions_job: {e}", exc_info=True)  
        
# Job for checking DB size and dumping
async def check_db_size_and_dump(context: ContextTypes.DEFAULT_TYPE):
    try:
        db_size_mb = os.path.getsize(DATABASE_NAME) / (1024 * 1024)
        max_size_mb = config.getfloat("MemoryManagement", "DbMaxSizeMB", fallback=300)
        if db_size_mb > max_size_mb and config.getboolean("MemoryManagement", "EnableDBDump", fallback=False):
            channel_id = config.getint("MemoryManagement", "DbDumpChannelId", fallback=None)
            if channel_id:
                with open(DATABASE_NAME, 'rb') as db_file:
                    await send_document_safe_mb(
                        context.bot,  # Could use _execute_bot_action_mb for multi-bot
                        channel_id,
                        db_file,
                        caption=f"Database dump at {datetime.now(timezone.utc).isoformat()} (Size: {db_size_mb:.2f} MB)",
                    )
                logger.info(f"Dumped database to channel {channel_id} (Size: {db_size_mb:.2f} MB).")
    except FileNotFoundError:
        logger.error(f"Database file {DATABASE_NAME} not found.")
    except Forbidden:
        logger.error(f"Bot lacks permission to send document to channel {channel_id}.")
    except Exception as e:
        logger.error(f"Error in check_db_size_and_dump: {e}", exc_info=True)
        
async def setup_timed_broadcasts_from_db(context: ContextTypes.DEFAULT_TYPE):
    """Loads timed broadcasts from the database and schedules them with the JobQueue."""
    logger.info("Setting up timed broadcasts from database...")

    if not context.job_queue:
        logger.warning(await get_language_string(None, "JOBQUEUE_NOT_AVAILABLE_MESSAGE"))
        return

    try:
        broadcasts = (await get_all_timed_broadcasts_from_db())  # Uses db_fetchall (Part 2)

        if not broadcasts:
            logger.info("No timed broadcasts found in database.")
            return

        logger.info(f"Found {len(broadcasts)} timed broadcasts in database. Scheduling...")

        for broadcast in broadcasts:
            job_name = broadcast["job_name"]
            target_type = broadcast["target_type"]
            message_text = broadcast["message_text"]
            interval_seconds = broadcast["interval_seconds"]
            next_run_time = broadcast["next_run_time"]  # Unix timestamp (float)
            markup_json = broadcast["markup_json"]
            target_id = broadcast.get("target_id")  # Optional

            # Check if a job with this name already exists (e.g., bot restart)
            existing_job = context.job_queue.get_jobs_by_name(job_name)
            if existing_job:
                logger.warning(f"Job '{job_name}' already exists. Skipping database entry.")
                continue  # Skip this database entry if job is already scheduled

            # Calculate the first run time. If next_run_time from DB is in the past, schedule immediately.
            now = time.time()
            run_at = max(now + 1, next_run_time)  # Schedule at least 1 second from now or at recorded time

            # Schedule the job with the JobQueue
            # Pass necessary data as job.data (must be pickleable)
            job_data = {
                "target_type": target_type,
                "message_text": message_text,
                "markup_json": markup_json,
                "target_id": target_id,  # Include target_id in job data
            }

            # The callback function is timed_broadcast_job_callback (defined in Part 3 logic block)
            context.job_queue.run_repeating(
                timed_broadcast_job_callback,  # The callback function
                interval=interval_seconds,
                first=run_at,  # Initial run time
                data=job_data,
                name=job_name,
            )
            logger.info(
                f"Scheduled timed broadcast job '{job_name}' (runs every {interval_seconds}s, first at {datetime.fromtimestamp(run_at, timezone.utc)})"
            )

    except Exception as e:
        logger.error(f"Error setting up timed broadcasts from database: {e}", exc_info=True)


# main.py - Part 9 of 20

# --- Self-Promotion Broadcast Commands ---


@feature_controlled("bcastselfuser")
async def bcastselfuser_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initiates a self-promotion broadcast to users who started the bot."""
    user = update.effective_user
    chat = update.effective_chat
    command_name = "bcastselfuser"

    if not user or not chat:
        return
    if not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", user_id=user.id),
        )
        return

    # Parse optional interval argument
    interval_duration_str = (context.args[0] if context.args else "0")  # Default to instant send (0 interval)
    interval_seconds = parse_duration(interval_duration_str)  # Uses parse_duration (Part 2)

    if interval_seconds is None:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "BCASTSELF_USER_USAGE_ERROR_ARGS", user_id=user.id),
        )
        return

    job_name = f"bcastselfuser_{user.id}"  # Unique job name for scheduling

    # Check if a job with this name already exists
    if (context.application.job_queue and context.application.job_queue.get_jobs_by_name(job_name)):
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "JOB_ALREADY_EXISTS", user_id=user.id, job_name=job_name),
        )  # Need pattern
        return

    bot_username = (await get_bot_username(context) or "your_bot")  # Uses get_chat_mb (_mb)
    if not bot_username:
        await send_message_safe(context, chat.id, "Error fetching bot username.", user_id=user.id)  # Fallback
        return

    # Construct the message text and markup
    # The message should be a standard welcome/promotion message with an "Add to Group" button
    message_text = await get_language_string(
        context,
        "BCASTSELF_MESSAGE_TEMPLATE",
        user_id=user.id,
        bot_username=bot_username,
    )  # Need pattern

    add_to_group_button_text = await get_language_string(
        context,
        "ADD_BOT_TO_GROUP_BUTTON_TEXT",
        user_id=user.id,
        bot_username=bot_username,
    )  # Re-use pattern
    add_to_group_url = f"https://t.me/{bot_username}?startgroup=true"
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(add_to_group_button_text, url=add_to_group_url)]])

    markup_json = json.dumps(reply_markup.to_dict())  # Serialize markup to JSON

    if interval_seconds > 0:
        # Schedule the job with JobQueue
        if not context.application.job_queue:
            await send_message_safe(
                context,
                chat.id,
                await get_language_string(context, "JOBQUEUE_NOT_AVAILABLE_MESSAGE", user_id=user.id),
            )
            return

        job_data = {
            "target_type": "all_users",
            "message_text": message_text,
            "markup_json": markup_json,
            "target_id": None,  # Not applicable for all_users
        }

        context.application.job_queue.run_repeating(
            timed_broadcast_job_callback,  # Uses timed_broadcast_job_callback (Part 3 logic)
            interval=interval_seconds,
            first=time.time() + 5,  # Start in 5 seconds
            data=job_data,
            name=job_name,
        )
        # Add to DB for persistence across restarts
        await add_timed_broadcast_to_db(
            job_name,
            "all_users",
            message_text,
            interval_seconds,
            time.time() + 5,
            markup_json,
        )  # Uses add_timed_broadcast_to_db (Part 2 logic)

        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "BCAST_SCHEDULED_USERS",
                user_id=user.id,
                duration=format_duration(interval_seconds),
                job_name=job_name,
            ),
        )  # Needs pattern

    else:  # Instant broadcast
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "BCASTSELF_STARTED_MESSAGE",
                user_id=user.id,
                target_type_plural="users",
            ),
        )  # Needs pattern

        # Execute broadcast directly
        sent_count, failed_count = await _execute_broadcast(
            context,
            message_text,
            "all_users",
            reply_markup=reply_markup,
            job_name_for_log=command_name,
        )  # Uses _execute_broadcast (Part 3)

        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "BCASTSELF_COMPLETE_MESSAGE",
                user_id=user.id,
                target_type_plural="users",
                sent_count=sent_count,
                failed_count=failed_count,
            ),
        )  # Needs pattern


@feature_controlled("bcastselfgroup")
async def bcastselfgroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initiates a self-promotion broadcast to all groups the bot is in."""
    user = update.effective_user
    chat = update.effective_chat
    command_name = "bcastselfgroup"

    if not user or not chat:
        return
    if not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", user_id=user.id),
        )
        return

    # Parse optional interval argument
    interval_duration_str = (context.args[0] if context.args else "0")  # Default to instant send (0 interval)
    interval_seconds = parse_duration(interval_duration_str)  # Uses parse_duration (Part 2)

    if interval_seconds is None:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "BCASTSELF_GROUP_USAGE_ERROR_ARGS", user_id=user.id),
        )
        return

    job_name = f"bcastselfgroup_{user.id}"  # Unique job name for scheduling

    # Check if a job with this name already exists
    if (context.application.job_queue and context.application.job_queue.get_jobs_by_name(job_name)):
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "JOB_ALREADY_EXISTS", user_id=user.id, job_name=job_name),
        )
        return

    bot_username = (await get_bot_username(context) or "your_bot")  # Uses get_chat_mb (_mb)
    if not bot_username:
        await send_message_safe(context, chat.id, "Error fetching bot username.", user_id=user.id)  # Fallback
        return

    # Construct the message text (group welcome message or similar)
    # This should be a message suitable for a group chat.
    message_text = await get_language_string(context, "START_MESSAGE_GROUP", user_id=user.id, bot_username=bot_username
                                             )  # Re-use group start message template? Or new pattern?
    # Let's re-use START_MESSAGE_GROUP template, passing a dummy chat_id for await get_language_string context if needed.
    # A specific broadcast message pattern might be better:
    # message_text = await get_language_string(context, 'BCASTSELF_GROUP_MESSAGE_TEMPLATE', user_id=user.id, bot_username=bot_username) # Need pattern

    # No standard buttons needed for group broadcast unless specifically required
    reply_markup = None  # No buttons

    markup_json = (json.dumps(reply_markup.to_dict()) if reply_markup else None)  # Serialize markup to JSON

    if interval_seconds > 0:
        # Schedule the job with JobQueue
        if not context.application.job_queue:
            await send_message_safe(
                context,
                chat.id,
                await get_language_string(context, "JOBQUEUE_NOT_AVAILABLE_MESSAGE", user_id=user.id),
            )
            return

        job_data = {
            "target_type": "all_groups",
            "message_text": message_text,
            "markup_json": markup_json,
            "target_id": None,  # Not applicable for all_groups
        }

        context.application.job_queue.run_repeating(
            timed_broadcast_job_callback,  # Uses timed_broadcast_job_callback (Part 3 logic)
            interval=interval_seconds,
            first=time.time() + 5,  # Start in 5 seconds
            data=job_data,
            name=job_name,
        )
        # Add to DB for persistence across restarts
        await add_timed_broadcast_to_db(
            job_name,
            "all_groups",
            message_text,
            interval_seconds,
            time.time() + 5,
            markup_json,
        )  # Uses add_timed_broadcast_to_db (Part 2 logic)

        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "BCAST_SCHEDULED_GROUPS",
                user_id=user.id,
                duration=format_duration(interval_seconds),
                job_name=job_name,
            ),
        )  # Needs pattern

    else:  # Instant broadcast
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "BCASTSELF_STARTED_MESSAGE",
                user_id=user.id,
                target_type_plural="groups",
            ),
        )  # Re-use pattern

        # Execute broadcast directly
        sent_count, failed_count = await _execute_broadcast(
            context,
            message_text,
            "all_groups",
            reply_markup=reply_markup,
            job_name_for_log=command_name,
        )  # Uses _execute_broadcast (Part 3)

        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "BCASTSELF_COMPLETE_MESSAGE",
                user_id=user.id,
                target_type_plural="groups",
                sent_count=sent_count,
                failed_count=failed_count,
            ),
        )  # Re-use pattern


@feature_controlled("bcastself")
async def bcastself_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initiates a self-promotion broadcast to all known users and groups."""
    user = update.effective_user
    chat = update.effective_chat
    command_name = "bcastself"

    if not user or not chat:
        return
    if not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", user_id=user.id),
        )
        return

    # Parse optional interval argument
    interval_duration_str = (context.args[0] if context.args else "0")  # Default to instant send (0 interval)
    interval_seconds = parse_duration(interval_duration_str)  # Uses parse_duration (Part 2)

    if interval_seconds is None:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "BCASTSELF_COMBINED_USAGE_ERROR_ARGS", user_id=user.id),
        )  # Need pattern
        return

    job_name_users = f"bcastself_users_{user.id}"  # Unique job name for user scheduling
    job_name_groups = (
        f"bcastself_groups_{user.id}"  # Unique job name for group scheduling
    )

    # Check if jobs with these names already exist
    if context.application.job_queue and (context.application.job_queue.get_jobs_by_name(job_name_users) or
                                          context.application.job_queue.get_jobs_by_name(job_name_groups)):
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "JOB_ALREADY_EXISTS",
                user_id=user.id,
                job_name=f"{job_name_users} / {job_name_groups}",
            ),
        )  # Re-use pattern
        return

    bot_username = (await get_bot_username(context) or "your_bot")  # Uses get_chat_mb (_mb)
    if not bot_username:
        await send_message_safe(context, chat.id, "Error fetching bot username.", user_id=user.id)  # Fallback
        return

    # Construct user broadcast message (PM style)
    user_message_text = await get_language_string(
        context,
        "BCASTSELF_MESSAGE_TEMPLATE",
        user_id=user.id,
        bot_username=bot_username,
    )  # Use PM template

    add_to_group_button_text = await get_language_string(
        context,
        "ADD_BOT_TO_GROUP_BUTTON_TEXT",
        user_id=user.id,
        bot_username=bot_username,
    )  # Re-use pattern
    add_to_group_url = f"https://t.me/{bot_username}?startgroup=true"
    user_reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(add_to_group_button_text, url=add_to_group_url)]])
    user_markup_json = json.dumps(user_reply_markup.to_dict())  # Serialize markup to JSON

    # Construct group broadcast message (Group style)
    group_message_text = await get_language_string(context,
                                                   "START_MESSAGE_GROUP",
                                                   user_id=user.id,
                                                   bot_username=bot_username)  # Re-use group start template
    # Or use a dedicated pattern:
    # group_message_text = await get_language_string(context, 'BCASTSELF_GROUP_MESSAGE_TEMPLATE', user_id=user.id, bot_username=bot_username) # Need pattern
    group_reply_markup = None  # No buttons for group broadcast by default
    group_markup_json = (json.dumps(group_reply_markup.to_dict()) if group_reply_markup else None
                         )  # Serialize markup to JSON

    if interval_seconds > 0:
        # Schedule jobs with JobQueue
        if not context.application.job_queue:
            await send_message_safe(
                context,
                chat.id,
                await get_language_string(context, "JOBQUEUE_NOT_AVAILABLE_MESSAGE", user_id=user.id),
            )
            return

        # User broadcast job
        user_job_data = {
            "target_type": "all_users",
            "message_text": user_message_text,
            "markup_json": user_markup_json,
            "target_id": None,  # Not applicable for all_users
        }
        context.application.job_queue.run_repeating(
            timed_broadcast_job_callback,  # Uses timed_broadcast_job_callback (Part 3 logic)
            interval=interval_seconds,
            first=time.time() + 5,  # Start in 5 seconds
            data=user_job_data,
            name=job_name_users,
        )
        await add_timed_broadcast_to_db(
            job_name_users,
            "all_users",
            user_message_text,
            interval_seconds,
            time.time() + 5,
            user_markup_json,
        )  # Uses add_timed_broadcast_to_db (Part 2 logic)

        # Group broadcast job
        group_job_data = {
            "target_type": "all_groups",
            "message_text": group_message_text,
            "markup_json": group_markup_json,
            "target_id": None,  # Not applicable for all_groups
        }
        context.application.job_queue.run_repeating(
            timed_broadcast_job_callback,  # Uses timed_broadcast_job_callback (Part 3 logic)
            interval=interval_seconds,
            first=time.time() + 5,  # Start in 5 seconds
            data=group_job_data,
            name=job_name_groups,
        )
        await add_timed_broadcast_to_db(
            job_name_groups,
            "all_groups",
            group_message_text,
            interval_seconds,
            time.time() + 5,
            group_markup_json,
        )  # Uses add_timed_broadcast_to_db (Part 2 logic)

        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "BCAST_SCHEDULED_COMBINED",
                user_id=user.id,
                duration=format_duration(interval_seconds),
                job_name_users=job_name_users,
                job_name_groups=job_name_groups,
            ),
        )  # Needs pattern

    else:  # Instant combined broadcast
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "BCASTSELF_STARTED_MESSAGE_COMBINED", user_id=user.id),
        )  # Needs pattern

        # Execute user broadcast directly
        sent_users, failed_users = await _execute_broadcast(
            context,
            user_message_text,
            "all_users",
            reply_markup=user_reply_markup,
            job_name_for_log=f"{command_name}_users",
        )  # Uses _execute_broadcast (Part 3)

        # Execute group broadcast directly
        sent_groups, failed_groups = await _execute_broadcast(
            context,
            group_message_text,
            "all_groups",
            reply_markup=group_reply_markup,
            job_name_for_log=f"{command_name}_groups",
        )  # Uses _execute_broadcast (Part 3)

        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "BCASTSELF_COMPLETE_MESSAGE_COMBINED",
                user_id=user.id,
                sent_users=sent_users,
                failed_users=failed_users,
                sent_groups=sent_groups,
                failed_groups=failed_groups,
            ),
        )  # Needs pattern


# --- Bot Membership Handlers ---


async def my_chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles updates when the bot's membership status in a chat changes."""
    # This handler receives ChatMemberUpdated updates for the bot itself.
    # The update.chat_member object represents the bot's new status.
    # The update.effective_chat is the chat where the change occurred (group/channel/user).
    # The update.effective_user is the user who caused the change (admin adding/removing bot).

    chat_member_update = update.my_chat_member
    chat = update.effective_chat
    user = update.effective_user  # The admin who changed the bot's status

    if not chat_member_update or not chat or not user:
        logger.warning("my_chat_member_handler received update without chat_member_update, chat, or user.")
        return

    old_status = chat_member_update.old_chat_member.status
    new_status = chat_member_update.new_chat_member.status
    bot_id = context.bot.id  # The ID of the bot instance that received this update

    logger.info(
        f"Bot {bot_id} status changed in chat {chat.id} ({chat.title or chat.type}) by user {user.id} (@{user.username}): {old_status} -> {new_status}"
    )

    # --- Handle Bot Added to a Group ---
    if old_status == ChatMemberStatus.LEFT and new_status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
    ]:
        # Bot was added to a chat (presumably a group)
        # Add or update the group in the database
        asyncio.create_task(
            add_group(
                chat.id,
                chat.title or f"Group {chat.id}",
                added_at=datetime.now(timezone.utc).isoformat(),
            ))  # Uses add_group (Part 2 logic)
        logger.info(f"Bot {bot_id} added to group {chat.id} ({chat.title}). Added to DB.")

        # Send a welcome message in the group (similar to /start in group)
        # Use the same logic as send_group_start_message but call it directly
        await send_group_start_message(update, context)  # Re-uses send_group_start_message (Part 7)

    # --- Handle Bot Removed from a Group ---
    elif new_status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED]:
        # Bot was removed or banned from a chat
        # Remove the group from the database
        if chat.type in [TGChat.GROUP, TGChat.SUPERGROUP]:
            asyncio.create_task(remove_group_from_db(chat.id))  # Uses remove_group_from_db (Part 2 logic)
            logger.info(f"Bot {bot_id} removed/banned from group {chat.id} ({chat.title}). Removed from DB.")
            # Also clean up admin cache for this group
            if chat.id in admin_cache:
                del admin_cache[chat.id]

        # If the bot was removed from a channel it was using for verification, log a warning
        if chat.type == TGChat.CHANNEL and settings.get("channel_id") == chat.id:
            logger.critical(
                f"Bot {bot_id} removed/banned from configured verification channel {chat.id}. Verification feature may be broken!"
            )
            settings["channel_id"] = None  # Disable the feature
            settings["channel_invite_link"] = None
            # Potentially notify super admins

    # --- Handle Bot Promoted/Demoted in a Group ---
    elif (old_status == ChatMemberStatus.MEMBER and new_status == ChatMemberStatus.ADMINISTRATOR):
        # Bot was promoted to admin
        logger.info(f"Bot {bot_id} promoted to admin in group {chat.id} ({chat.title}). Refreshing admin cache.")
        # Force refresh admin cache for this group
        asyncio.create_task(get_cached_admins(context, chat.id,
                                              force_refresh=True))  # Uses get_cached_admins (Part 2), run in background
        # Send a message in the group indicating admin status and features unlocked
        # Need a pattern: BOT_PROMOTED_TO_ADMIN_MESSAGE
        # await send_message_safe(context, chat.id, await get_language_string(context, 'BOT_PROMOTED_TO_ADMIN_MESSAGE', chat_id=chat.id, bot_username=context.bot.username or "Bot"))

    elif (old_status == ChatMemberStatus.ADMINISTRATOR and new_status == ChatMemberStatus.MEMBER):
        # Bot was demoted from admin
        logger.warning(
            f"Bot {bot_id} demoted from admin in group {chat.id} ({chat.title}). Features requiring admin perms will stop working."
        )
        # Force refresh admin cache to reflect loss of status
        asyncio.create_task(get_cached_admins(context, chat.id,
                                              force_refresh=True))  # Uses get_cached_admins (Part 2), run in background
        # Send a message in the group indicating loss of admin status and limitations
        # Need a pattern: BOT_DEMOTED_FROM_ADMIN_MESSAGE
        # await send_message_safe(context, chat.id, await get_language_string(context, 'BOT_DEMOTED_FROM_ADMIN_MESSAGE', chat_id=chat.id, bot_username=context.bot.username or "Bot"))

    # --- Handle Bot Admin Rights Changed ---
    # This fires when an admin's specific rights change, including the bot's
    # The new_chat_member object has attributes like can_restrict_members etc.
    if (old_status == ChatMemberStatus.ADMINISTRATOR and new_status == ChatMemberStatus.ADMINISTRATOR):
        # Check if specific permissions relevant to the bot's function changed
        old_can_restrict = getattr(chat_member_update.old_chat_member, "can_restrict_members", False)
        new_can_restrict = getattr(chat_member_update.new_chat_member, "can_restrict_members", False)
        old_can_ban = getattr(chat_member_update.old_chat_member, "can_ban_members", False)
        new_can_ban = getattr(chat_member_update.new_chat_member, "can_ban_members", False)
        old_can_delete = getattr(chat_member_update.old_chat_member, "can_delete_messages", False)
        new_can_delete = getattr(chat_member_update.new_chat_member, "can_delete_messages", False)

        if (old_can_restrict != new_can_restrict or old_can_ban != new_can_ban or old_can_delete != new_can_delete):
            logger.warning(
                f"Bot {bot_id} admin permissions changed in chat {chat.id} ({chat.title}). Restrict: {old_can_restrict}->{new_can_restrict}, Ban: {old_can_ban}->{new_can_ban}, Delete: {old_can_delete}->{new_can_delete}. Refreshing admin cache."
            )
            # Force refresh admin cache
            asyncio.create_task(get_cached_admins(
                context, chat.id, force_refresh=True))  # Uses get_cached_admins (Part 2), run in background
            # Optionally notify in the group if crucial permissions were lost


# --- Shutdown and Restart Handlers ---

from cachetools import TTLCache

# Initialize rate limit cache (chat_id -> timestamp)
reload_rate_limit_cache = TTLCache(maxsize=1024, ttl=ADMIN_CACHE_REFRESH_COOLDOWN)

async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Refresh the admin list for the current group with rate limiting."""
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user or chat.type not in (TGChat.GROUP, TGChat.SUPERGROUP):
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            await get_language_string(context, "GROUP_ONLY_COMMAND", user_id=user.id),
        )
        return

    chat_id = chat.id
    user_id = user.id

    # Check rate limit
    if chat_id in reload_rate_limit_cache:
        await send_message_safe(
            context,
            chat_id,
            await get_language_string(
                context,
                "RELOAD_RATE_LIMITED",
                user_id=user_id,
                seconds=ADMIN_CACHE_REFRESH_COOLDOWN,
            ),
        )
        return

    # Check admin privileges
    if not await has_admin_privileges(update, context):
        await send_message_safe(
            context,
            chat_id,
            await get_language_string(context, "ADMIN_ONLY_COMMAND", user_id=user_id),
        )
        return

    logger.info(f"Reload initiated by user {user_id} in group {chat_id}")

    # Refresh admin list
    try:
        admins = await rate_limited_api_call(context.bot.get_chat_administrators, chat_id)
        context.bot_data.setdefault("admin_cache", {})[chat_id] = [admin.user.id for admin in admins]
        logger.debug(f"Updated admin cache for group {chat_id}: {context.bot_data['admin_cache'][chat_id]}")
    except telegram.error.TelegramError as e:
        logger.error(f"Failed to refresh admins in group {chat_id}: {e}")
        await send_message_safe(
            context,
            chat_id,
            await get_language_string(context, "RELOAD_FAILED", user_id=user_id),
        )
        return

    # Clear pending batch operations
    try:
        with sqlite3.connect(config.get("Bot", "DatabaseName", fallback="bards_sentinel_async.db")) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pending_batch_ops WHERE chat_id = ?", (chat_id,))
            conn.commit()
            logger.debug(f"Cleared pending batch operations for group {chat_id}")
    except sqlite3.Error as e:
        logger.error(f"Database error clearing pending ops in group {chat_id}: {e}")

    # Set rate limit
    reload_rate_limit_cache[chat_id] = True

    await send_message_safe(
        context,
        chat_id,
        await get_language_string(context, "RELOAD_SUCCESS", user_id=user_id),
    )

async def shutdown_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /shutdown command (Super Admin only) to stop the bot."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return
    if not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", user_id=user.id),
        )
        return

    logger.warning(f"Shutdown initiated by Super Admin {user.id} in chat {chat.id}.")
    await send_message_safe(
        context,
        chat.id,
        await get_language_string(context, "BOT_SHUTTING_DOWN_MESSAGE", chat_id=chat.id, user_id=user.id),
    )  # Need pattern

    global SHUTTING_DOWN
    SHUTTING_DOWN = True  # Set global flag

    for app in applications:
        # Send shutdown message to the primary bot's admin channel if configured and possible?
        # Or just log? Logging is safer.
        logger.info(f"Stopping Application for bot {app.bot.id}...")
        await app.stop()
        logger.info(f"Application for bot {app.bot.id} stopped.")

    logger.info("All bot applications stopped. Closing database.")
    # Close the database pool after all applications are stopped
    await close_db_pool()  # Uses close_db_pool (Part 3)

    logger.info("Shutdown complete. Exiting.")
    os._exit(0)  # Exit the process


async def restart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /restart command (Super Admin only) to restart the bot process."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return
    if not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", user_id=user.id),
        )
        return

    logger.warning(f"Restart initiated by Super Admin {user.id} in chat {chat.id}.")
    await send_message_safe(
        context,
        chat.id,
        await get_language_string(context, "BOT_RESTARTING_MESSAGE", chat_id=chat.id, user_id=user.id),
    )  # Need pattern

    # This is tricky in pure Python. It typically requires an external process manager (like systemd, supervisord, Docker)
    # that is configured to restart the script if it exits.
    # The current Python process cannot reliably restart itself.
    # The standard way is to stop the application(s) and then the process exits, relying on the external manager to restart it.

    global SHUTTING_DOWN
    SHUTTING_DOWN = True  # Set global flag

    # Stop all running bot applications gracefully
    for app in applications:
        logger.info(f"Stopping Application for bot {app.bot.id} for restart...")
        await app.stop()
        logger.info(f"Application for bot {app.bot.id} stopped for restart.")

    logger.info("All bot applications stopped for restart. Closing database.")
    await close_db_pool()  # Uses close_db_pool (Part 3)

    logger.info("Restart sequence complete. Exiting, expecting external process manager to restart.")
    # Exit with a specific code if needed for process manager, or standard 0
    os._exit(0)  # Exit the process, expecting restart


# main.py - Part 10 of 20

# --- Admin/Super Admin Configuration Commands ---


@feature_controlled("addbadactor")
async def addbadactor_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /addbadactor command (Super Admin only)."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return
    if not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", user_id=user.id),
        )
        return

    if not context.args:
        await send_message_safe(context, chat.id, "Usage: /addbadactor <user_id or @username> [reason]")  # Need pattern
        return

    target_identifier = context.args[0]
    reason = (" ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided."
              )  # Need default reason pattern

    # Resolve target identifier to user ID using cached helper (uses is_real_telegram_user_cached which uses get_chat_mb)
    target_user_id: Optional[int] = None
    if target_identifier.startswith("@"):
        resolved_id, is_bot = await is_real_telegram_user_cached(context, target_identifier)  # Uses _mb
        if resolved_id and not is_bot:
            target_user_id = resolved_id
        elif resolved_id and is_bot:
            await send_message_safe(
                context,
                chat.id,
                await get_language_string(context, "CANNOT_ACTION_BOT", user_id=user.id),
            )
            return

    elif target_identifier.isdigit():
        target_user_id = int(target_identifier)
        # Optional: verify if this ID is a real user/bot using get_chat_mb if needed
        try:
            target_chat_info = await get_chat_mb(context.bot, target_user_id)  # Uses _mb
            if target_chat_info and target_chat_info.type == TGChat.BOT:
                await send_message_safe(
                    context,
                    chat.id,
                    await get_language_string(context, "CANNOT_ACTION_BOT", user_id=user.id),
                )
                return
        except Exception:
            logger.debug(f"Could not verify if ID {target_user_id} is a bot via get_chat_mb.")

    if not target_user_id:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "USER_NOT_FOUND_MESSAGE",
                user_id=user.id,
                identifier=target_identifier,
            ),
        )  # Uses pattern
        return

    # Prevent adding Super Admins as bad actors
    if target_user_id in AUTHORIZED_USERS:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "CANNOT_ACTION_SUPER_ADMIN", user_id=user.id),
        )  # Uses pattern
        return

    # Add to bad_actors table
    try:
        await add_bad_actor(target_user_id, reason)  # Uses add_bad_actor (Part 2 logic)
        await send_message_safe(context, chat.id, f"User {target_user_id} marked as bad actor.")  # Need pattern
        logger.info(f"Super Admin {user.id} marked user {target_user_id} as bad actor. Reason: {reason}")
    except Exception as e:
        logger.error(f"DB error adding bad actor {target_user_id}: {e}", exc_info=True)
        await send_message_safe(context, chat.id, f"Error marking user as bad actor: {e}")  # Need pattern


@feature_controlled("removebadactor")
async def removebadactor_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /removebadactor command (Super Admin only)."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return
    if not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", user_id=user.id),
        )
        return

    if not context.args:
        await send_message_safe(context, chat.id, "Usage: /removebadactor <user_id or @username>")  # Need pattern
        return

    target_identifier = context.args[0]

    # Resolve target identifier to user ID using cached helper (uses is_real_telegram_user_cached which uses get_chat_mb)
    target_user_id: Optional[int] = None
    if target_identifier.startswith("@"):
        resolved_id, _ = await is_real_telegram_user_cached(context, target_identifier)  # Uses _mb
        target_user_id = resolved_id

    elif target_identifier.isdigit():
        target_user_id = int(target_identifier)

    if not target_user_id:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "USER_NOT_FOUND_MESSAGE",
                user_id=user.id,
                identifier=target_identifier,
            ),
        )  # Uses pattern
        return

    # Remove from bad_actors table
    try:
        cursor = await db_pool.execute("DELETE FROM bad_actors WHERE user_id = ?", (target_user_id, ))
        if cursor.rowcount > 0:
            await send_message_safe(context, chat.id,
                                    f"User {target_user_id} removed from bad actors list.")  # Need pattern
            logger.info(f"Super Admin {user.id} removed user {target_user_id} from bad actors list.")
        else:
            await send_message_safe(
                context,
                chat.id,
                f"User {target_user_id} was not found in the bad actors list.",
            )  # Need pattern

    except Exception as e:
        logger.error(f"DB error removing bad actor {target_user_id}: {e}", exc_info=True)
        await send_message_safe(context, chat.id, f"Error removing user from bad actors list: {e}")  # Need pattern


@feature_controlled("addexempt")
async def addexempt_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /addexempt <user_id or @username> command (Admin only)."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return
    if chat.type not in [TGChat.GROUP, TGChat.SUPERGROUP]:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "COMMAND_GROUP_ONLY_MESSAGE",
                chat_id=chat.id,
                user_id=user.id,
                command_name="addexempt",
            ),
        )
        return

    # Check admin status (group admin or super admin)
    is_chat_admin_or_super = await _is_user_group_admin_or_creator(context, chat.id,
                                                                   user.id)  # Uses get_cached_admins (_mb)
    if not is_chat_admin_or_super:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "ADMIN_ONLY_COMMAND_MESSAGE", chat_id=chat.id, user_id=user.id),
        )
        return

    if not context.args:
        await send_message_safe(context, chat.id, "Usage: /addexempt <user_id or @username>")  # Need pattern
        return

    target_identifier = context.args[0]

    # Resolve target identifier to user ID using cached helper (uses is_real_telegram_user_cached which uses get_chat_mb)
    target_user_id: Optional[int] = None
    if target_identifier.startswith("@"):
        resolved_id, is_bot = await is_real_telegram_user_cached(context, target_identifier)  # Uses _mb
        if resolved_id and not is_bot:
            target_user_id = resolved_id
        elif resolved_id and is_bot:
            await send_message_safe(
                context,
                chat.id,
                await get_language_string(context, "CANNOT_ACTION_BOT", chat_id=chat.id, user_id=user.id),
            )  # Add chat_id/user_id context
            return

    elif target_identifier.isdigit():
        target_user_id = int(target_identifier)
        # Optional: verify if this ID is a real user/bot using get_chat_mb
        try:
            target_chat_info = await get_chat_mb(context.bot, target_user_id)  # Uses _mb
            if target_chat_info and target_chat_info.type == TGChat.BOT:
                await send_message_safe(
                    context,
                    chat.id,
                    await get_language_string(context, "CANNOT_ACTION_BOT", chat_id=chat.id, user_id=user.id),
                )
                return
        except Exception:
            logger.debug(f"Could not verify if ID {target_user_id} is a bot via get_chat_mb.")

    if not target_user_id:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "USER_NOT_FOUND_MESSAGE",
                chat_id=chat.id,
                user_id=user.id,
                identifier=target_identifier,
            ),
        )  # Add chat_id/user_id context
        return

    # Prevent adding Super Admins as exempt
    if target_user_id in AUTHORIZED_USERS:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "CANNOT_ACTION_SUPER_ADMIN", chat_id=chat.id, user_id=user.id),
        )
        return

    # Add to group_user_exemptions table
    try:
        await add_group_user_exemption(chat.id, target_user_id)  # Uses add_group_user_exemption (Part 2 logic)
        await send_message_safe(
            context,
            chat.id,
            f"User {target_user_id} added to exemptions in this group.",
        )  # Need pattern
        logger.info(f"Admin {user.id} added user {target_user_id} to exemptions in group {chat.id}.")
    except Exception as e:
        logger.error(
            f"DB error adding exemption for {target_user_id} in {chat.id}: {e}",
            exc_info=True,
        )
        await send_message_safe(context, chat.id, f"Error adding user to exemptions: {e}")  # Need pattern


@feature_controlled("removeexempt")
async def removeexempt_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /removeexempt <user_id or @username> command (Admin only)."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return
    if chat.type not in [TGChat.GROUP, TGChat.SUPERGROUP]:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "COMMAND_GROUP_ONLY_MESSAGE",
                chat_id=chat.id,
                user_id=user.id,
                command_name="removeexempt",
            ),
        )
        return

    # Check admin status (group admin or super admin)
    is_chat_admin_or_super = await _is_user_group_admin_or_creator(context, chat.id,
                                                                   user.id)  # Uses get_cached_admins (_mb)
    if not is_chat_admin_or_super:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "ADMIN_ONLY_COMMAND_MESSAGE", chat_id=chat.id, user_id=user.id),
        )
        return

    if not context.args:
        await send_message_safe(context, chat.id, "Usage: /removeexempt <user_id or @username>")  # Need pattern
        return

    target_identifier = context.args[0]

    # Resolve target identifier to user ID using cached helper (uses is_real_telegram_user_cached which uses get_chat_mb)
    target_user_id: Optional[int] = None
    if target_identifier.startswith("@"):
        resolved_id, _ = await is_real_telegram_user_cached(context, target_identifier)  # Uses _mb
        target_user_id = resolved_id

    elif target_identifier.isdigit():
        target_user_id = int(target_identifier)

    if not target_user_id:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "USER_NOT_FOUND_MESSAGE",
                chat_id=chat.id,
                user_id=user.id,
                identifier=target_identifier,
            ),
        )  # Add chat_id/user_id context
        return

    # Remove from group_user_exemptions table
    try:
        removed = await remove_group_user_exemption(
            chat.id, target_user_id)  # Uses remove_group_user_exemption (Part 2 logic), returns True if removed
        if removed:
            await send_message_safe(
                context,
                chat.id,
                f"User {target_user_id} removed from exemptions in this group.",
            )  # Need pattern
            logger.info(f"Admin {user.id} removed user {target_user_id} from exemptions in group {chat.id}.")
        else:
            await send_message_safe(
                context,
                chat.id,
                f"User {target_user_id} was not found in exemptions for this group.",
            )  # Need pattern

    except Exception as e:
        logger.error(
            f"DB error removing exemption for {target_user_id} in {chat.id}: {e}",
            exc_info=True,
        )
        await send_message_safe(context, chat.id, f"Error removing user from exemptions: {e}")  # Need pattern


@feature_controlled("feature")
async def feature_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /feature <feature_name> <enable|disable> (Super Admin only)."""
    user = update.effective_user
    chat = update.effective_chat
    global MAINTENANCE_MODE

    if not user or not chat:
        return
    if not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", user_id=user.id),
        )
        return

    if len(context.args) != 2:
        # Also add a way to list features? /feature list
        await send_message_safe(
            context,
            chat.id,
            "Usage: /feature <feature_name> <enable|disable> or /feature list",
        )  # Need pattern
        return

    feature_name = context.args[0].lower()
    action = context.args[1].lower()

    if action not in ["enable", "disable"]:
        await send_message_safe(context, chat.id, "Action must be 'enable' or 'disable'.")  # Need pattern
        return

    # Check if feature_name is valid/known? Or allow any string?
    # Allowing any string adds flexibility but can lead to typos. Let's list known features in help/usage.
    # Known features correspond to the @feature_controlled decorators.
    known_features = [
        "start",
        "help",
        "status",
        "unmuteall",
        "gunmuteall",
        "unbanall",
        "gunbanall",
        "bcastselfuser",
        "bcastselfgroup",
        "bcastself",
        "addbadactor",
        "removebadactor",
        "addexempt",
        "removeexempt",
        "feature",
        "setaction",
        "setduration",
        "setallduration",
        "getsettings",
        "setsettings",
        "cancelbroadcast",
        "listbroadcasts",
        "maintenance_mode_active",
        "message_processing",
        "lang",
        "reload",
        "unmuteme",
    ]  # Add all used feature names

    if feature_name == "list":
        # List all known features and their current state
        status_msg = "<b>Feature States:</b>\n"  # Need pattern
        try:
            # Get states from DB (uses db_fetchall)
            rows = await db_fetchall("SELECT feature_name, is_enabled FROM feature_control")
            db_states = {row["feature_name"]: row["is_enabled"] for row in rows}

            for feature in known_features:
                state = db_states.get(feature, 1)  # Default to enabled if not in DB
                status_msg += f"- {feature}: {'Enabled' if state else 'Disabled'}\n"

            # Also show maintenance mode state
            status_msg += f"- maintenance_mode_active: {'Enabled' if MAINTENANCE_MODE else 'Disabled'} (Global override)\n"

        except Exception as e:
            logger.error(f"Error listing features: {e}", exc_info=True)
            status_msg += f"Error fetching states: {e}\n"

        await send_message_safe(context, chat.id, status_msg, parse_mode=ParseMode.HTML)
        return

    # If not listing, proceed to enable/disable
    is_enabled = action == "enable"

    try:
        # Set feature state in DB (uses set_feature_state)
        await set_feature_state(feature_name, is_enabled)  # Uses set_feature_state (Part 2 logic)
        await send_message_safe(
            context,
            chat.id,
            f"Feature '{feature_name}' has been {'enabled' if is_enabled else 'disabled'}.",
        )  # Need pattern
        logger.info(f"Super Admin {user.id} set feature '{feature_name}' to {action}.")

        # Special handling for maintenance_mode_active to update the global variable immediately
        if feature_name == "maintenance_mode_active":
            MAINTENANCE_MODE = is_enabled
            logger.warning(f"Maintenance mode global flag set to {MAINTENANCE_MODE}.")

    except Exception as e:
        logger.error(f"DB error setting feature state for '{feature_name}': {e}", exc_info=True)
        await send_message_safe(context, chat.id, f"Error setting feature state: {e}")  # Need pattern


@feature_controlled("setaction")
async def setaction_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /setaction <mute|ban|kick> command (Admin only). Sets default punish action for the group."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return
    if chat.type not in [TGChat.GROUP, TGChat.SUPERGROUP]:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "COMMAND_GROUP_ONLY_MESSAGE",
                chat_id=chat.id,
                user_id=user.id,
                command_name="setaction",
            ),
        )
        return

    # Check admin status (group admin or super admin)
    is_chat_admin_or_super = await _is_user_group_admin_or_creator(context, chat.id,
                                                                   user.id)  # Uses get_cached_admins (_mb)
    if not is_chat_admin_or_super:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "ADMIN_ONLY_COMMAND_MESSAGE", chat_id=chat.id, user_id=user.id),
        )
        return

    if len(context.args) != 1:
        await send_message_safe(context, chat.id, "Usage: /setaction <mute|ban|kick>")  # Need pattern
        return

    action = context.args[0].lower()
    if action not in ["mute", "ban", "kick"]:
        await send_message_safe(context, chat.id, "Action must be 'mute', 'ban', or 'kick'.")  # Need pattern
        return

    try:
        # Set punish action for the group in DB (uses set_group_punish_action_async)
        await set_group_punish_action_async(chat.id, chat.title or f"Group {chat.id}",
                                            action)  # Uses set_group_punish_action_async (Part 2 logic)
        await send_message_safe(context, chat.id,
                                f"Default punish action for this group set to '{action}'.")  # Need pattern
        logger.info(f"Admin {user.id} set punish action for group {chat.id} to '{action}'.")
    except Exception as e:
        logger.error(f"DB error setting punish action for group {chat.id}: {e}", exc_info=True)
        await send_message_safe(context, chat.id, f"Error setting punish action: {e}")  # Need pattern


@feature_controlled("setduration")
async def setduration_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /setduration <profile|message|mention_profile> <duration> command (Admin only)."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return
    if chat.type not in [TGChat.GROUP, TGChat.SUPERGROUP]:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "COMMAND_GROUP_ONLY_MESSAGE",
                chat_id=chat.id,
                user_id=user.id,
                command_name="setduration",
            ),
        )
        return

    # Check admin status (group admin or super admin)
    is_chat_admin_or_super = await _is_user_group_admin_or_creator(context, chat.id,
                                                                   user.id)  # Uses get_cached_admins (_mb)
    if not is_chat_admin_or_super:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "ADMIN_ONLY_COMMAND_MESSAGE", chat_id=chat.id, user_id=user.id),
        )
        return

    if len(context.args) != 2:
        await send_message_safe(
            context,
            chat.id,
            "Usage: /setduration <profile|message|mention_profile> <duration>",
        )  # Need pattern
        return

    trigger_type = context.args[0].lower()
    duration_str = context.args[1]

    if trigger_type not in ["profile", "message", "mention_profile"]:
        await send_message_safe(
            context,
            chat.id,
            "Trigger type must be 'profile', 'message', or 'mention_profile'.",
        )  # Need pattern
        return

    duration_seconds = parse_duration(duration_str)  # Uses parse_duration (Part 2)
    if duration_seconds is None:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "INVALID_DURATION_FORMAT_MESSAGE",
                chat_id=chat.id,
                user_id=user.id,
                duration_str=duration_str,
            ),
        )  # Uses pattern
        return

    try:
        # Set punish duration for the trigger type in DB (uses set_group_punish_duration_for_trigger_async)
        await set_group_punish_duration_for_trigger_async(
            chat.id, chat.title or f"Group {chat.id}", trigger_type,
            duration_seconds)  # Uses set_group_punish_duration_for_trigger_async (Part 2 logic)
        duration_formatted = format_duration(duration_seconds)  # Uses format_duration (Part 2)
        await send_message_safe(
            context,
            chat.id,
            f"Punish duration for '{trigger_type}' in this group set to {duration_formatted}.",
        )  # Need pattern
        logger.info(
            f"Admin {user.id} set punish duration for '{trigger_type}' in group {chat.id} to {duration_seconds}s.")
    except Exception as e:
        logger.error(
            f"DB error setting punish duration for '{trigger_type}' in group {chat.id}: {e}",
            exc_info=True,
        )
        await send_message_safe(context, chat.id, f"Error setting punish duration: {e}")  # Need pattern


@feature_controlled("setallduration")
async def setallduration_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /setallduration <duration> command (Admin only). Sets default punish duration for all triggers in the group."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return
    if chat.type not in [TGChat.GROUP, TGChat.SUPERGROUP]:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "COMMAND_GROUP_ONLY_MESSAGE",
                chat_id=chat.id,
                user_id=user.id,
                command_name="setallduration",
            ),
        )
        return

    # Check admin status (group admin or super admin)
    is_chat_admin_or_super = await _is_user_group_admin_or_creator(context, chat.id,
                                                                   user.id)  # Uses get_cached_admins (_mb)
    if not is_chat_admin_or_super:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "ADMIN_ONLY_COMMAND_MESSAGE", chat_id=chat.id, user_id=user.id),
        )
        return

    if len(context.args) != 1:
        await send_message_safe(context, chat.id, "Usage: /setallduration <duration>")  # Need pattern
        return

    duration_str = context.args[0]
    duration_seconds = parse_duration(duration_str)  # Uses parse_duration (Part 2)
    if duration_seconds is None:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "INVALID_DURATION_FORMAT_MESSAGE",
                chat_id=chat.id,
                user_id=user.id,
                duration_str=duration_str,
            ),
        )  # Uses pattern
        return

    try:
        # Set punish duration for all trigger types in DB (uses set_all_group_punish_durations_async)
        await set_all_group_punish_durations_async(chat.id, chat.title or f"Group {chat.id}", duration_seconds
                                                   )  # Uses set_all_group_punish_durations_async (Part 2 logic)
        duration_formatted = format_duration(duration_seconds)  # Uses format_duration (Part 2)
        await send_message_safe(
            context,
            chat.id,
            f"Default punish duration for all triggers in this group set to {duration_formatted}.",
        )  # Need pattern
        logger.info(f"Admin {user.id} set all punish durations in group {chat.id} to {duration_seconds}s.")
    except Exception as e:
        logger.error(
            f"DB error setting all punish durations in group {chat.id}: {e}",
            exc_info=True,
        )
        await send_message_safe(context, chat.id, f"Error setting all punish durations: {e}")  # Need pattern


@feature_controlled("gfreepunish")
async def gfreepunish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            update.effective_chat.id,
            getattr(patterns, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", "Super admin only."),
        )
        return
    if not context.args:
        await send_message_safe(
            context,
            update.effective_chat.id,
            getattr(patterns, "GFREEPUNISH_USAGE_MESSAGE", "Usage: /gfreepunish [user_id]"),
        )
        return
    try:
        target_user_id_str = context.args[0]
        target_user_id: Optional[int] = None
        if target_user_id_str.startswith("@"):
            target_user_id, _ = await is_real_telegram_user_cached(context, target_user_id_str)
            if target_user_id is None:
                await send_message_safe(
                    context,
                    update.effective_chat.id,
                    getattr(
                        patterns,
                        "USER_NOT_FOUND_MESSAGE",
                        "User {identifier} not found",
                    ).format(identifier=target_user_id_str),
                )
                return
        else:
            target_user_id = int(target_user_id_str)

        settings["free_users"].add(target_user_id)
        await send_message_safe(
            context,
            update.effective_chat.id,
            getattr(
                patterns,
                "GFREEPUNISH_SUCCESS_MESSAGE",
                "User {user_id} globally exempted",
            ).format(user_id=target_user_id),
        )
        logger.info(f"Super admin {user.id} granted global immunity to user {target_user_id}")
    except ValueError:
        await send_message_safe(
            context,
            update.effective_chat.id,
            getattr(patterns, "INVALID_USER_ID_MESSAGE", "Invalid user ID"),
        )
    except Exception as e:
        logger.error(f"Error in gfreepunish command for user {user.id}: {e}", exc_info=True)
        await send_message_safe(context, update.effective_chat.id, f"An error occurred: {e}")


@feature_controlled("gunfreepunish")
async def gunfreepunish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            update.effective_chat.id,
            getattr(patterns, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", "Super admin only."),
        )
        return
    if not context.args:
        await send_message_safe(
            context,
            update.effective_chat.id,
            getattr(
                patterns,
                "GUNFREEPUNISH_USAGE_MESSAGE",
                "Usage: /gunfreepunish [user_id]",
            ),
        )
        return
    try:
        target_user_id_str = context.args[0]
        target_user_id: Optional[int] = None
        if target_user_id_str.startswith("@"):
            target_user_id, _ = await is_real_telegram_user_cached(context, target_user_id_str)
            if target_user_id is None:
                await send_message_safe(
                    context,
                    update.effective_chat.id,
                    getattr(
                        patterns,
                        "USER_NOT_FOUND_MESSAGE",
                        "User {identifier} not found",
                    ).format(identifier=target_user_id_str),
                )
                return
        else:
            target_user_id = int(target_user_id_str)

        if target_user_id in settings.get("free_users", set()):
            settings["free_users"].remove(target_user_id)
            await send_message_safe(
                context,
                update.effective_chat.id,
                getattr(
                    patterns,
                    "GUNFREEPUNISH_SUCCESS_MESSAGE",
                    "User {user_id} global exemption removed",
                ).format(user_id=target_user_id),
            )
            logger.info(f"Super admin {user.id} removed global immunity from user {target_user_id}")
        else:
            await send_message_safe(
                context,
                update.effective_chat.id,
                getattr(
                    patterns,
                    "GUNFREEPUNISH_NOT_IMMUNE_MESSAGE",
                    "User {user_id} not immune",
                ).format(user_id=target_user_id),
            )
    except ValueError:
        await send_message_safe(
            context,
            update.effective_chat.id,
            getattr(patterns, "INVALID_USER_ID_MESSAGE", "Invalid user ID"),
        )
    except Exception as e:
        logger.error(f"Error in gunfreepunish command for user {user.id}: {e}", exc_info=True)
        await send_message_safe(context, update.effective_chat.id, f"An error occurred: {e}")


@feature_controlled("clearcache")
async def clear_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            update.effective_chat.id,
            getattr(patterns, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", "Super admin only."),
        )
        return
    pc, uc = (len(user_profile_cache) if user_profile_cache else 0), (len(username_to_id_cache)
                                                                      if username_to_id_cache else 0)
    if user_profile_cache:
        user_profile_cache.clear()
    if username_to_id_cache:
        username_to_id_cache.clear()
    await send_message_safe(
        context,
        update.effective_chat.id,
        getattr(patterns, "CLEAR_CACHE_SUCCESS_MESSAGE", "Cache cleared").format(profile_cache_count=pc,
                                                                                 username_cache_count=uc),
    )
    logger.info(f"Super admin {user.id} cleared caches. Cleared {pc} profile, {uc} username entries.")


@feature_controlled("checkbio")  # Feature name remains "checkbio" for the disable/enable command
async def check_bio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat  # Chat where command was issued
    if not user:
        logger.warning("check_bio_command received update without user.")
        return

    if not context.args and (not update.effective_message or not update.effective_message.reply_to_message):
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            getattr(
                patterns,
                "CHECKBIO_USAGE_MESSAGE",
                "Usage: /checkbio [user_id or reply]",
            ),
            parse_mode=ParseMode.HTML,
        )
        return

    target_user_id_to_check: Optional[int] = None
    identifier: Optional[str] = None
    target_user_obj: Optional[TGUser] = (
        None  # Store the target user object if we get it easily
    )

    if (update.effective_message and update.effective_message.reply_to_message and not context.args):
        target_user = update.effective_message.reply_to_message.from_user
        if target_user:
            target_user_id_to_check = target_user.id
            identifier = f"Reply to {target_user.id}"
            target_user_obj = target_user
    elif context.args:
        identifier = context.args[0]
        if identifier.startswith("@"):
            # --- MODIFICATION START ---
            # Attempt to resolve the username. is_real_telegram_user_cached handles bot usernames by returning (None, False).
            target_user_id_to_check, is_bot = await is_real_telegram_user_cached(context, identifier)

            # Check if the resolution failed OR if it resolved to a bot.
            if target_user_id_to_check is None or is_bot:
                # If it resolved to a bot, we can try to get the user object by ID later if needed,
                # but the initial lookup by username failed or indicated it's a bot.
                # If user_id is None, it means the username couldn't be resolved by API.
                # If is_bot is True, it means it was resolved but is a bot account.

                if is_bot:
                    # If it's a bot (resolved by ID lookup within the cached function, though lookup by @ failed),
                    # we still want to get the bot's profile details if possible via get_chat.
                    # Use the resolved user_id if available.
                    if target_user_id_to_check:
                        try:
                            target_user_obj = await get_chat_with_retry(context.bot, target_user_id_to_check)
                        except Exception as e:
                            logger.debug(
                                f"Could not fetch target bot obj {target_user_id_to_check} after username lookup: {e}")

                    # Regardless of getting the object here, the flag is_bot is set.
                    # The rest of the function will proceed knowing it's a bot.
                    # If the API lookup by username *failed* completely (user_id is None),
                    # the is_bot check will be False.
                    pass  # Continue to the check below.

                if target_user_id_to_check is None:
                    # Username lookup failed completely. This includes bot usernames where the lookup by @ fails.
                    # Inform the user that the username was not found or could not be resolved.
                    await send_message_safe(
                        context,
                        chat.id if chat else user.id,
                        getattr(
                            patterns,
                            "USER_NOT_FOUND_MESSAGE",
                            "User {identifier} not found",
                        ).format(identifier=identifier),
                    )
                    return
                    # This return is important to stop processing for unresolved usernames.
            else:
                # The username resolved to a real, non-bot user. Proceed as before.
                if not target_user_obj:
                    try:
                        target_user_obj = await get_chat_with_retry(context.bot, target_user_id_to_check)
                    except Exception as e:
                        logger.debug(
                            f"Could not fetch target user obj {target_user_id_to_check} after username lookup: {e}")
            # --- MODIFICATION END ---

        else:
            try:
                target_user_id_to_check = int(identifier)
                # If it's a numerical ID, attempt to get the user object
                if not target_user_obj:
                    try:
                        target_user_obj = await get_chat_with_retry(context.bot, target_user_id_to_check)
                    except Exception as e:
                        logger.debug(f"Could not fetch target user obj {target_user_id_to_check} after ID lookup: {e}")

            except ValueError:
                await send_message_safe(
                    context,
                    chat.id if chat else user.id,
                    getattr(patterns, "INVALID_USER_ID_MESSAGE", "Invalid user ID"),
                )
                return

    if target_user_id_to_check is None:
        await send_message_safe(context, chat.id if chat else user.id, "Could not determine target user.")
        return

    # Re-fetch target_user_obj by ID if it wasn't obtained yet (e.g., if input was ID string or replied message user object was minimal)
    if target_user_obj is None:
        try:
            target_user_obj = await get_chat_with_retry(context.bot, target_user_id_to_check)
            if target_user_obj is None:
                await send_message_safe(
                    context,
                    chat.id if chat else user.id,
                    getattr(
                        patterns,
                        "USER_NOT_FOUND_MESSAGE",
                        "User {identifier} not found",
                    ).format(identifier=identifier or str(target_user_id_to_check)),
                )
                return
        except Exception as e:
            logger.error(
                f"Error fetching target user obj {target_user_id_to_check} before check: {e}",
                exc_info=True,
            )
            await send_message_safe(
                context,
                chat.id if chat else user.id,
                getattr(patterns, "CHECKBIO_ERROR_MESSAGE", "Error checking bio: {error}").format(
                    user_id=target_user_id_to_check,
                    error="Could not fetch user details.",
                ),
            )
            return

    # Add/update user in DB. Use the fetched target_user_obj for comprehensive data.
    # Skip if it's the command issuer themselves to avoid unnecessary DB writes for their own check.
    if target_user_id_to_check != user.id:
        await add_user(
            target_user_id_to_check,
            target_user_obj.username or "",
            target_user_obj.first_name or "",
            getattr(target_user_obj, "last_name", ""),
        )

    # Check if the target is a bot account
    is_target_bot = getattr(target_user_obj, "is_bot", False)

    if is_target_bot:
        logger.info(f"Target user {target_user_id_to_check} is a bot. Providing basic bot info.")
        bio_text = (getattr(target_user_obj, "bio", None) or getattr(target_user_obj, "description", None) or
                    "")  # Bots might have description instead of bio
        username_text = target_user_obj.username or getattr(patterns, "NOT_APPLICABLE", "N/A")

        result_message = getattr(patterns, "CHECKBIO_RESULT_HEADER",
                                 "Profile check for {user_id}").format(user_id=target_user_id_to_check,
                                                                       username=username_text)
        result_message += f"\nIs a Bot: Yes"
        if bio_text:
            result_message += f"\nDescription/Bio: <pre>{bio_text}</pre>"  # Use pre for better formatting
        else:
            result_message += f"\nDescription/Bio: {getattr(patterns, 'BIO_IS_BLANK_MESSAGE', 'Bio is blank.')}"

        # For bots, we don't typically check for "problematic links" or "known bad actors" in the same way as users.
        # However, if you *want* to apply those checks to bot profiles, the logic would go here.
        # Based on the user's initial request regarding bot usernames, it seems they want them *flagged* when mentioned,
        # but the `/checkbio` on a bot ID should just provide information. Let's stick to providing info.
        # We can optionally add a check for known bad actor status *if* they are in the bad_actors table.

        is_bad = await is_bad_actor(target_user_id_to_check)  # Check bad actor table
        result_message += f"\nKnown Bad Actor: {'Yes' if is_bad else 'No'}"

        # Get the command issuer's mention for logging purposes
        issuer_mention_log = (user.mention_html() if hasattr(user, "mention_html") else f"@{user.username or user.id}")
        logger.info(f"User {user.id} ({issuer_mention_log}) checked bio for bot {target_user_id_to_check}.")

        await send_message_safe(
            context,
            chat.id if chat else user.id,
            result_message,
            parse_mode=ParseMode.HTML,
        )
        return  # Stop here for bot targets

    # If not a bot, proceed with the standard user profile check logic
    bio_text = (getattr(target_user_obj, "bio", None) or "")  # Get bio, fallback to empty string if None
    username_text = target_user_obj.username or getattr(patterns, "NOT_APPLICABLE", "N/A")

    # Check for problematic links in the user's profile fields
    has_issue, problematic_field, issue_type = await user_has_links_cached(context, target_user_id_to_check)

    # If profile issue found, add/update bad actor status
    if has_issue:
        logger.info(
            f"Profile issue detected for user {target_user_id_to_check} via /checkbio: {issue_type} in {problematic_field}. Marking as bad actor."
        )
        await add_bad_actor(
            target_user_id_to_check,
            f"Profile issue ({issue_type or patterns.UNKNOWN_TEXT}) in field {problematic_field or patterns.UNKNOWN_TEXT} found via /checkbio.",
        )

    result_message = getattr(patterns, "CHECKBIO_RESULT_HEADER",
                             "Profile check for {user_id}").format(user_id=target_user_id_to_check,
                                                                   username=username_text)
    result_message += f"\nBio: <pre>{bio_text}</pre>"  # Using pre for better formatting
    result_message += f"\nProblematic: {'Yes' if has_issue else 'No'}"
    if has_issue:
        result_message += getattr(
            patterns,
            "CHECKBIO_RESULT_PROBLEM_DETAILS",
            "\n  - Issue in <b>{field}</b> ({issue_type})",
        ).format(
            field=problematic_field or patterns.UNKNOWN_TEXT,
            issue_type=issue_type or patterns.NOT_APPLICABLE,
        )
    # Check bad actor status using the updated function ---
    is_bad = await is_bad_actor(target_user_id_to_check)
    result_message += f"\nKnown Bad Actor: {'Yes' if is_bad else 'No'}"

    # Get the command issuer's mention for logging purposes
    issuer_mention_log = (user.mention_html() if hasattr(user, "mention_html") else f"@{user.username or user.id}")
    logger.info(
        f"User {user.id} ({issuer_mention_log}) checked bio for user {target_user_id_to_check}. Has issue: {has_issue}. Is bad actor: {is_bad}"
    )

    await send_message_safe(context, chat.id if chat else user.id, result_message, parse_mode=ParseMode.HTML)


@feature_controlled("setchannel")
async def set_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            getattr(patterns, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", "Super admin only."),
        )
        return

    # Clear any pending forward request for this user
    if "awaiting_channel_forward" in context.user_data:
        del context.user_data["awaiting_channel_forward"]
        logger.debug(f"Cleared pending channel forward flag for user {user.id}.")

    if not context.args:
        context.user_data["awaiting_channel_forward"] = True  # Set flag for this user
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            getattr(patterns, "SET_CHANNEL_PROMPT", "Set channel prompt"),
            parse_mode=ParseMode.HTML,
        )
        logger.info(f"Super admin {user.id} prompted for channel forward/ID.")
        return

    arg = context.args[0].lower()
    if arg == "clear":
        settings["channel_id"] = None
        settings["channel_invite_link"] = None
        # Update config file
        config = configparser.ConfigParser()
        # Read existing config first to preserve other sections
        if os.path.exists(CONFIG_FILE_NAME):
            config.read(CONFIG_FILE_NAME)
        if "Channel" not in config:
            config.add_section("Channel")
        config.set("Channel", "ChannelId", "")
        config.set("Channel", "ChannelInviteLink", "")
        with open(CONFIG_FILE_NAME, "w") as configfile:
            config.write(configfile)
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            getattr(patterns, "SET_CHANNEL_CLEARED_MESSAGE", "Channel cleared."),
        )
        logger.info(f"Verification channel requirement cleared by super admin {user.id}")
        return

    channel_identifier = context.args[0]  # Original casing might be needed for usernames
    try:
        logger.info(f"Super admin {user.id} attempting to set verification channel to: {channel_identifier}")
        target_chat_obj = await get_chat_with_retry(context.bot, channel_identifier)

        if not target_chat_obj or target_chat_obj.type != TGChat.CHANNEL:
            error_msg = getattr(patterns, "SET_CHANNEL_NOT_A_CHANNEL_ERROR", "Not a channel.").format(
                identifier=channel_identifier,
                type=target_chat_obj.type if target_chat_obj else "unknown",
            )
            await send_message_safe(context, chat.id if chat else user.id, error_msg)
            return

        # Check if bot is admin in the target channel
        bot_member = await context.bot.get_chat_member(target_chat_obj.id, context.bot.id)
        if bot_member.status not in [
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.OWNER,
        ]:
            await send_message_safe(
                context,
                chat.id if chat else user.id,
                getattr(patterns, "SET_CHANNEL_BOT_NOT_ADMIN_ERROR", "Bot not admin."),
            )
            logger.warning(f"Bot is not an admin in target channel {target_chat_obj.id} set by admin {user.id}.")
            return

        # Try to get an invite link
        invite_link = getattr(target_chat_obj, "invite_link", None)
        if not invite_link:  # Try to create or export one if bot has permission
            bot_member_perms = getattr(bot_member, "can_invite_users", False) or getattr(
                bot_member, "can_create_invite_links", False)  # Check both old and new perms
            if bot_member_perms:
                try:
                    # Prefer creating a new one if permission exists
                    new_link_obj = await context.bot.create_chat_invite_link(
                        target_chat_obj.id,
                        name=f"{target_chat_obj.title or 'Verification'} Link",
                        creates_join_request=False,
                    )
                    invite_link = new_link_obj.invite_link
                    logger.info(f"Created new invite link for channel {target_chat_obj.id}.")
                except Exception as e_link_create:
                    logger.warning(
                        f"Could not create invite link for channel {target_chat_obj.id}: {e_link_create}. Trying export."
                    )
                    try:  # Fallback to exporting existing primary link
                        invite_link = await context.bot.export_chat_invite_link(target_chat_obj.id)
                        logger.info(f"Exported invite link for channel {target_chat_obj.id}.")
                    except Exception as e_export:
                        logger.warning(f"Could not export invite link for channel {target_chat_obj.id}: {e_export}")
            else:
                logger.warning(
                    f"Bot lacks permissions to create or export invite links for channel {target_chat_obj.id}.")

        settings["channel_id"] = target_chat_obj.id
        settings["channel_invite_link"] = (
            invite_link  # Store even if None, to indicate attempt was made
        )

        # Update config file
        config = configparser.ConfigParser()
        if os.path.exists(CONFIG_FILE_NAME):
            config.read(CONFIG_FILE_NAME)
        if "Channel" not in config:
            config.add_section("Channel")
        config.set("Channel", "ChannelId", str(target_chat_obj.id))
        config.set("Channel", "ChannelInviteLink", invite_link or "")  # Store empty string if None
        with open(CONFIG_FILE_NAME, "w") as configfile:
            config.write(configfile)

        reply_message_text = getattr(patterns, "SET_CHANNEL_SUCCESS_MESSAGE", "Channel set.").format(
            channel_title=target_chat_obj.title or target_chat_obj.username or target_chat_obj.id,
            channel_id=target_chat_obj.id,
        )
        if invite_link:
            reply_message_text += getattr(patterns, "SET_CHANNEL_INVITE_LINK_APPEND",
                                          "\nLink: {invite_link}").format(invite_link=invite_link)
        else:
            reply_message_text += getattr(patterns, "SET_CHANNEL_NO_INVITE_LINK_APPEND", "\nNo link.")

        await send_message_safe(
            context,
            chat.id if chat else user.id,
            reply_message_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        logger.info(
            f"Verification channel set to {target_chat_obj.id} (Invite: {invite_link or 'N/A'}) by super admin {user.id}"
        )

    except BadRequest as e:
        logger.error(
            f"BadRequest accessing channel '{channel_identifier}' for setchannel: {e}",
            exc_info=True,
        )
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            getattr(patterns, "SET_CHANNEL_BADREQUEST_ERROR", "BR error.").format(identifier=channel_identifier,
                                                                                  error=e),
        )
    except Forbidden as e:
        logger.error(
            f"Forbidden accessing channel '{channel_identifier}' for setchannel: {e}",
            exc_info=True,
        )
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            getattr(patterns, "SET_CHANNEL_FORBIDDEN_ERROR", "Forbidden error.").format(identifier=channel_identifier,
                                                                                        error=e),
        )
    except Exception as e:
        logger.error(
            f"Unexpected error setting verification channel to {channel_identifier}: {e}",
            exc_info=True,
        )
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            getattr(patterns, "SET_CHANNEL_UNEXPECTED_ERROR", "Unexpected error.").format(error=e),
        )


async def handle_forwarded_channel_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message
    chat = update.effective_chat  # This is the PM chat with the bot

    # This handler is only for super admins who were prompted by /setchannel
    if (not user or not chat or chat.type != TGChat.PRIVATE or not await _is_super_admin(user.id)):
        # If a non-super-admin forwards something in PM, or if the flag isn't set
        # and they forward something, just ignore it for this handler.
        # If the flag was set for a non-admin, clear it.
        if context.user_data.get("awaiting_channel_forward"):
            del context.user_data["awaiting_channel_forward"]
            logger.debug(f"Cleared awaiting_channel_forward flag for non-super-admin user {user.id}.")
        return  # Ignore if not in PM with super admin and awaiting forward

    # If we are here, it's a super admin in PM, potentially awaiting a forward.
    if not context.user_data.get("awaiting_channel_forward"):
        # Super admin forwarded something in PM, but was not prompted by /setchannel. Ignore for this handler.
        logger.debug(
            f"Super admin {user.id} forwarded message in PM but was not awaiting channel forward. Skipping handler.")
        return

    # We are a super admin, in PM, and awaiting a channel forward.
    del context.user_data["awaiting_channel_forward"]  # Consume the flag

    if (message and message.forward_from_chat and message.forward_from_chat.type == TGChat.CHANNEL):
        # Create a pseudo Update object or just call set_channel_command logic with the channel ID
        channel_id_from_forward = message.forward_from_chat.id
        logger.info(f"Super admin {user.id} forwarded message from channel {channel_id_from_forward}.")

        # We need to simulate the context.args for set_channel_command
        context.args = [str(channel_id_from_forward)]

        # Call set_channel_command logic, ensuring it replies to the admin's PM
        # set_channel_command already replies to update.effective_chat, which is correct here (admin's PM)
        await set_channel_command(update, context)

    else:
        await send_message_safe(
            context,
            user.id,
            getattr(
                patterns,
                "SET_CHANNEL_FORWARD_NOT_CHANNEL_ERROR",
                "Not forwarded from channel.",
            ),
        )
        logger.warning(
            f"Super admin {user.id} sent a message in PM but it was not a valid channel forward while awaiting one.")


@feature_controlled("stats")
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            getattr(patterns, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", "Super admin only."),
        )
        return

    groups_count = await get_all_groups_count()
    total_users_count = await get_all_users_count(started_only=False)
    started_users_count = await get_all_users_count(started_only=True)  # Users who have started the bot

    profile_cache_size = (len(user_profile_cache) if user_profile_cache else getattr(patterns, "NOT_APPLICABLE", "N/A"))
    username_cache_size = (len(username_to_id_cache) if username_to_id_cache else getattr(
        patterns, "NOT_APPLICABLE", "N/A"))
    globally_free_users_count = len(settings.get("free_users", set()))
    verification_channel_id = str(settings.get("channel_id", getattr(patterns, "NOT_APPLICABLE", "N/A")))
    bad_actors_count_row = await db_fetchone("SELECT COUNT(*) AS count FROM bad_actors")
    bad_actors_count = (bad_actors_count_row["count"]
                        if bad_actors_count_row and bad_actors_count_row.get("count") is not None else 0)

    uptime_seconds = 0
    if hasattr(context.application, "start_time_epoch"):
        uptime_seconds = int(time.time() - context.application.start_time_epoch)
    uptime_formatted = format_duration(uptime_seconds)

    stats_message = getattr(patterns, "STATS_COMMAND_MESSAGE", "Stats").format(
        groups_count=groups_count,
        total_users_count=total_users_count,
        started_users_count=started_users_count,
        profile_cache_size=profile_cache_size,
        username_cache_size=username_cache_size,
        globally_free_users_count=globally_free_users_count,
        verification_channel_id=verification_channel_id,
        bad_actors_count=bad_actors_count,
        uptime_formatted=uptime_formatted,
        ptb_version=TG_VER,
        maintenance_mode_status=(getattr(patterns, "ON_TEXT", "ON") if MAINTENANCE_MODE else getattr(
            patterns, "OFF_TEXT", "OFF")),
    )
    await send_message_safe(context, chat.id if chat else user.id, stats_message, parse_mode=ParseMode.HTML)


@feature_controlled("disable")
async def disable_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            getattr(patterns, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", "Super admin only."),
        )
        return
    if not context.args:
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            getattr(
                patterns,
                "DISABLE_COMMAND_USAGE_MESSAGE",
                "Usage: /disable [feature_name]",
            ),
        )
        return

    feature_name_to_disable = context.args[0].lower()
    # Prevent disabling critical commands/features
    critical_features = {
        "disable",
        "enable",
        "maintenance",
        "start",
        "help",
        "stats",
        "message_processing",
        "chat_member_processing",
    }  # Add chat_member_processing if used
    if feature_name_to_disable in critical_features:
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            getattr(
                patterns,
                "DISABLE_COMMAND_CRITICAL_ERROR",
                "Cannot disable {feature_name}",
            ).format(feature_name=feature_name_to_disable),
        )
        return

    await set_feature_state(feature_name_to_disable, False)
    await send_message_safe(
        context,
        chat.id if chat else user.id,
        getattr(
            patterns,
            "DISABLE_COMMAND_SUCCESS_MESSAGE",
            "Feature {feature_name} disabled",
        ).format(feature_name=feature_name_to_disable),
    )
    logger.info(f"Super admin {user.id} disabled feature: {feature_name_to_disable}")


@feature_controlled("enable")
async def enable_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            getattr(patterns, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", "Super admin only."),
        )
        return
    if not context.args:
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            getattr(
                patterns,
                "ENABLE_COMMAND_USAGE_MESSAGE",
                "Usage: /enable [feature_name]",
            ),
        )
        return

    feature_name_to_enable = context.args[0].lower()
    await set_feature_state(feature_name_to_enable, True)
    await send_message_safe(
        context,
        chat.id if chat else user.id,
        getattr(patterns, "ENABLE_COMMAND_SUCCESS_MESSAGE",
                "Feature {feature_name} enabled").format(feature_name=feature_name_to_enable),
    )
    logger.info(f"Super admin {user.id} enabled feature: {feature_name_to_enable}")


@feature_controlled("maintenance")
async def maintenance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    # MAINTENANCE_MODE global is updated by set_feature_state
    if not user or not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            getattr(patterns, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", "Super admin only."),
        )
        return

    current_state_str = (getattr(patterns, "ON_TEXT", "ON") if MAINTENANCE_MODE else getattr(
        patterns, "OFF_TEXT", "OFF"))
    if not context.args or context.args[0].lower() not in ["on", "off"]:
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            getattr(
                patterns,
                "MAINTENANCE_COMMAND_USAGE_MESSAGE",
                "Usage: /maintenance [on|off]",
            ).format(current_state=current_state_str),
        )
        return

    new_state_str = context.args[0].lower()
    new_state_bool = new_state_str == "on"

    # Check if state is already as requested
    if MAINTENANCE_MODE == new_state_bool:
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            f"Maintenance mode is already {current_state_str}.",
        )
        return

    await set_feature_state("maintenance_mode_active", new_state_bool)  # This will update MAINTENANCE_MODE global
    # MAINTENANCE_MODE is already updated by set_feature_state
    final_state_str = (getattr(patterns, "ENABLED_TEXT", "enabled").upper() if new_state_bool else getattr(
        patterns, "DISABLED_TEXT", "disabled").upper())  # Using different words for clarity
    action_str = "rests" if new_state_bool else "resumes its watch"
    await send_message_safe(
        context,
        chat.id if chat else user.id,
        getattr(patterns, "MAINTENANCE_COMMAND_SUCCESS_MESSAGE",
                "Maintenance mode {state}.").format(state=final_state_str, action=action_str),
    )
    logger.info(f"Super admin {user.id} set maintenance mode to {new_state_str.upper()}.")


# --- Broadcast Logic ---
def _detect_message_format(message_text: str) -> str | None:
    """Detects the probable parse mode (HTML or MarkdownV2) of a message."""
    if not message_text:
        return None

    html_tags = r"<\/?(?:b|i|u|s|strike|code|pre|a\s+href=)"
    if re.search(html_tags, message_text, re.IGNORECASE):
        return ParseMode.HTML

    mdv2_chars = r"(?<!\\)[*_~`]|(?<!\\)\|\|.+?(?<!\\)\|\||\[[^\]]+?\]\([^)]+?\)"
    if re.search(mdv2_chars, message_text):
        # If MD chars are present and no clear HTML was detected earlier, lean towards MDV2.
        # MDV2 requires strict escaping, so false positives are possible if user used these chars naturally.
        # HTML detection is often more reliable for user-provided text.
        # Given the potential for false positives with MDV2, prioritizing HTML if any tags are found might be safer.
        if not re.search(html_tags, message_text, re.IGNORECASE):  # Only suggest MDV2 if no HTML-like tags found
            return ParseMode.MARKDOWN_V2

    return None  # Default to Plain text if no specific formatting detected


async def _send_single_broadcast_message(
    context: ContextTypes.DEFAULT_TYPE,
    target_id: int,
    message_text: str,
    detected_parse_mode: str | None,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    job_name_for_log: str = "Broadcast",
) -> bool:
    """Sends a single broadcast message with retries and error handling."""
    if not message_text:
        logger.warning(f"{job_name_for_log}: Attempted to send empty message to {target_id}.")
        return False

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=message_text,
            parse_mode=detected_parse_mode,
            disable_web_page_preview=True,
            reply_markup=reply_markup,
        )
        await asyncio.sleep(BROADCAST_SLEEP_INTERVAL)  # Crucial for rate limiting
        return True
    except RetryAfter as e:
        logger.warning(f"{job_name_for_log}: Rate limit hit for {target_id}. Retrying after {e.retry_after}s.")
        await asyncio.sleep(e.retry_after)
        # Retry once more, could be made configurable
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=message_text,
                parse_mode=detected_parse_mode,
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )
            await asyncio.sleep(BROADCAST_SLEEP_INTERVAL)
            return True
        except Exception as e_retry:
            logger.error(f"{job_name_for_log}: Failed on retry for {target_id}: {e_retry}")
            return False
    except Forbidden:
        logger.warning(f"{job_name_for_log}: Forbidden to send to {target_id}.")
        if target_id < 0:
            await remove_group_from_db(target_id)  # Remove inactive group
        # Optionally remove user if Forbidden and chat_id > 0 (PM) - be careful with false positives
        # elif target_id > 0: await db_execute("DELETE FROM users WHERE user_id = ?", (target_id,))
    except BadRequest as e:
        # Handle common BadRequest errors more gracefully
        error_msg_lower = str(e).lower()
        if ("chat not found" in error_msg_lower or "user is deactivated" in error_msg_lower or
                "bot was blocked by the user" in error_msg_lower):
            logger.warning(
                f"{job_name_for_log}: BadRequest (Chat/User not found or blocked) for {target_id}: {e}. Text: {message_text[:50]}"
            )
            if target_id < 0:
                await remove_group_from_db(target_id)
            # elif target_id > 0: await db_execute("DELETE FROM users WHERE user_id = ?", (target_id,)) # Optionally remove inactive user
        elif "bad request: can't parse" in error_msg_lower:
            logger.warning(
                f"{job_name_for_log}: BadRequest (Parse error) for {target_id} with parse mode {detected_parse_mode}: {e}. Retrying as plain text."
            )
            # Retry sending as plain text if parse mode failed
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=message_text,
                    parse_mode=None,
                    disable_web_page_preview=True,
                    reply_markup=reply_markup,
                )
                await asyncio.sleep(BROADCAST_SLEEP_INTERVAL)
                return True
            except Exception as e_plain:
                logger.error(f"{job_name_for_log}: Failed on plain text retry for {target_id}: {e_plain}")
                return False
        else:
            logger.warning(
                f"{job_name_for_log}: BadRequest for {target_id}: {e} (ParseMode: {detected_parse_mode}, Text: {message_text[:100]})"
            )
    except Exception as e:
        logger.error(f"{job_name_for_log}: Unexpected error for {target_id}: {e}", exc_info=True)
    return False


async def _execute_broadcast(
    context: ContextTypes.DEFAULT_TYPE,
    message_text: str,
    target_type: str,  # 'all_groups', 'all_users', 'specific_target'
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    job_name_for_log: str = "Broadcast",
    specific_target_id: int | None = None,
):
    """Internal function to handle the logic of sending broadcasts."""
    detected_format = _detect_message_format(message_text)
    sent_count, failed_count = 0, 0
    target_ids: List[int] = []

    if specific_target_id is not None:
        target_ids = [specific_target_id]
    elif target_type == "all_groups":
        target_ids = await get_all_groups_from_db()
    elif target_type == "all_users":
        target_ids = await get_all_users_from_db(started_only=True)  # Only PM users who started the bot
    # Add other target types here if needed (e.g., 'all_groups_and_users')

    if not target_ids:
        logger.info(f"{job_name_for_log}: No targets found for type '{target_type}'.")
        return sent_count, failed_count

    logger.info(
        f"{job_name_for_log}: Starting broadcast to {len(target_ids)} targets of type '{target_type}' with format '{detected_format or 'Plain Text'}'."
    )

    for target_id in target_ids:
        # Check SHUTTING_DOWN flag periodically
        if SHUTTING_DOWN:
            logger.warning(f"{job_name_for_log}: Shutting down, stopping broadcast.")
            break

        if await _send_single_broadcast_message(
                context,
                target_id,
                message_text,
                detected_format,
                reply_markup=reply_markup,
                job_name_for_log=job_name_for_log,
        ):
            sent_count += 1
        else:
            failed_count += 1
        # Log progress more frequently for large broadcasts
        if (sent_count + failed_count) > 0 and (sent_count + failed_count) % 50 == 0:
            logger.info(
                f"{job_name_for_log}: Progress - Processed: {sent_count + failed_count}/{len(target_ids)}, Sent: {sent_count}, Failed: {failed_count}"
            )

    logger.info(
        f"{job_name_for_log}: Broadcast to type '{target_type}' complete. Sent: {sent_count}, Failed: {failed_count}.")
    return sent_count, failed_count


async def timed_broadcast_job_callback(context: ContextTypes.DEFAULT_TYPE):
    """Callback for timed broadcasts managed by JobQueue."""
    job = context.job
    if not job or not job.data:
        logger.error("Timed broadcast job callback executed without job data.")
        return

    job_name = job.name
    job_data = job.data

    target_type = job_data.get("target_type")
    message_text = job_data.get("message_text")
    reply_markup_json = job_data.get("markup")  # Get markup if stored as JSON <-- MODIFIED

    if not target_type or not message_text:
        logger.error(
            f"Timed broadcast job '{job_name}' is missing target_type or message_text in job.data. Removing job.")
        # Remove this faulty job
        running_jobs = context.job_queue.get_jobs_by_name(job_name)
        for r_job in running_jobs:
            r_job.schedule_removal()
        await remove_timed_broadcast_from_db(job_name)
        if job_name in settings["active_timed_broadcasts"]:
            del settings["active_timed_broadcasts"][job_name]
        return

    logger.info(f"Executing timed broadcast job: {job_name} (Target: {target_type})")

    reply_markup: Optional[InlineKeyboardMarkup] = None
    if reply_markup_json:
        try:
            # Attempt to parse the JSON string back into an InlineKeyboardMarkup
            reply_markup = InlineKeyboardMarkup.from_json(reply_markup_json)
        except Exception as e:
            logger.error(f"Failed to parse reply_markup JSON for job '{job_name}': {e}. Sending without markup.")
            reply_markup = None

    sent, failed = await _execute_broadcast(
        context,
        message_text,
        target_type,
        reply_markup=reply_markup,
        job_name_for_log=f"TimedBroadcast-{job_name}",
    )
    logger.info(f"Timed broadcast job {job_name} finished. Sent: {sent}, Failed: {failed}")


# --- Broadcast Commands ---
@feature_controlled("broadcast")  # Super admin command
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat  # Command sender chat
    if not user or not chat or not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            getattr(patterns, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", "Super admin only."),
        )
        return

    args = context.args
    # Expected formats:
    # /broadcast <message> (to all groups, no interval)
    # /broadcast [target_id] <message> (to specific group/user, no interval)
    # /broadcast [interval (e.g., 30m, 2h, 1d)] <message> (to all groups, repeating)
    # /broadcast [interval (e.g., 30m, 2h, 1d)] [target_id] <message> (NOT supported by this logic)

    if not args:
        await send_message_safe(
            context,
            chat.id,
            getattr(patterns, "BROADCAST_USAGE_MESSAGE", "Broadcast usage."),
        )
        return

    time_interval_str: Optional[str] = None
    target_id_input: Optional[str] = None
    message_start_index = 0

    # Check for time interval (e.g., "3h", "30m") as the first argument
    if (len(args) > 0 and parse_duration(args[0]) is not None and
            parse_duration(args[0]) != 0):  # 0 duration implies immediate, not repeating
        time_interval_str = args[0]
        message_start_index = 1
        if len(args) == 1:  # Only interval given
            await send_message_safe(context, chat.id, "Please provide a message for the timed broadcast.")
            return

    # Check for target_id if it's the next argument (only if interval wasn't the first arg or was).
    # Note: Original logic didn't support timed broadcasts to specific IDs via /broadcast, maintaining that.
    # If time_interval_str is None, check if args[0] is a target_id.
    # If time_interval_str is present, check if args[1] is a target_id.
    potential_target_idx = 0 if time_interval_str is None else 1

    if (len(args) > potential_target_idx and args[potential_target_idx].lstrip("-").isdigit()):
        target_id_input = args[potential_target_idx]
        message_start_index = potential_target_idx + 1
        # If an interval was also provided, this format (interval + target_id) is not supported by this command.
        if time_interval_str:
            await send_message_safe(
                context,
                chat.id,
                "Timed broadcasts with a specific target ID are not supported via /broadcast. Use /bcastall or /bcastself for timed global broadcasts, or omit target_id for timed group broadcast.",
            )
            return

    message_text = " ".join(args[message_start_index:])
    if not message_text:
        await send_message_safe(
            context,
            chat.id,
            getattr(patterns, "BROADCAST_NO_MESSAGE_ERROR", "No message provided."),
        )
        return

    interval_seconds: Optional[int] = None
    if time_interval_str:
        interval_seconds = parse_duration(time_interval_str)
        # We already checked for 0 duration earlier, this check confirms it's a valid positive interval
        if interval_seconds is None or interval_seconds <= 0:
            await send_message_safe(
                context,
                chat.id,
                f"Invalid time interval '{time_interval_str}'. Must be positive like 30m, 2h, 1d.",
            )
            return

    job_name = f"manual_broadcast_{int(time.time())}"  # Unique job name using timestamp

    if interval_seconds:  # Timed broadcast (only to all groups for this command)
        target_type_for_timed = "all_groups"
        # target_id_input is checked above to ensure it's not present with interval
        if context.job_queue:
            job_data = {
                "target_type": target_type_for_timed,
                "message_text": message_text,
            }
            context.job_queue.run_repeating(
                timed_broadcast_job_callback,
                interval=interval_seconds,
                first=0,
                data=job_data,
                name=job_name,
            )
            await add_timed_broadcast_to_db(
                job_name,
                target_type_for_timed,
                message_text,
                interval_seconds,
                time.time(),
            )
            settings["active_timed_broadcasts"][job_name] = True
            await send_message_safe(
                context,
                chat.id,
                f"Scheduled timed broadcast to all groups every {format_duration(interval_seconds)}. Job name: <code>{job_name}</code>\nMessage: {message_text[:100]}...",
                parse_mode=ParseMode.HTML,
            )
        else:
            await send_message_safe(
                context,
                chat.id,
                "JobQueue not available. Timed broadcast cannot be scheduled.",
            )
        return

    # --- Immediate Broadcast ---
    await send_message_safe(
        context,
        chat.id,
        getattr(patterns, "BROADCAST_STARTED_MESSAGE",
                "Broadcast started.").format(format=(_detect_message_format(message_text) or "Plain Text")),
    )

    specific_target_id_int: Optional[int] = None
    broadcast_target_type = "all_groups"  # Default target for immediate /broadcast

    if target_id_input:
        try:
            specific_target_id_int = int(target_id_input)
            broadcast_target_type = "specific_target"
        except ValueError:
            await send_message_safe(context, chat.id, f"Invalid target_id: {target_id_input}")
            return

    sent, failed = await _execute_broadcast(
        context,
        message_text,
        broadcast_target_type,
        specific_target_id=specific_target_id_int,
        job_name_for_log="Broadcast",
    )
    await send_message_safe(
        context,
        chat.id,
        getattr(patterns, "BROADCAST_COMPLETE_MESSAGE", "Broadcast complete.").format(sent_count=sent,
                                                                                      failed_count=failed),
    )


@feature_controlled("bcastall")  # Super admin command
async def bcastall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat or not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            chat.id if chat else user.id,
            getattr(patterns, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", "Super admin only."),
        )
        return

    args = context.args
    time_interval_str: Optional[str] = None
    message_start_index = 0

    if args and parse_duration(args[0]) is not None and parse_duration(args[0]) != 0:
        time_interval_str = args[0]
        message_start_index = 1
        if len(args) == 1:  # Only time given
            await send_message_safe(
                context,
                chat.id,
                "Please provide a message for the timed universal broadcast.",
            )
            return

    message_text = " ".join(args[message_start_index:])
    if not message_text:
        await send_message_safe(
            context,
            chat.id,
            getattr(patterns, "BCASTALL_USAGE_MESSAGE", "Bcastall usage."),
        )
        return

    interval_seconds: Optional[int] = None
    if time_interval_str:
        interval_seconds = parse_duration(time_interval_str)
        if interval_seconds is None or interval_seconds <= 0:
            await send_message_safe(
                context,
                chat.id,
                f"Invalid time interval '{time_interval_str}'. Must be positive like 30m, 2h, 1d.",
            )
            return

    job_name_base = "bcastall"
    job_name_timestamp = int(time.time())  # Use a single timestamp for related jobs

    if interval_seconds:  # Timed universal broadcast (groups and users)
        if context.job_queue:
            # Schedule job for all groups
            group_job_name = f"{job_name_base}_groups_{job_name_timestamp}"
            job_data_groups = {
                "target_type": "all_groups",
                "message_text": message_text,
            }
            context.job_queue.run_repeating(
                timed_broadcast_job_callback,
                interval=interval_seconds,
                first=0,
                data=job_data_groups,
                name=group_job_name,
            )
            await add_timed_broadcast_to_db(
                group_job_name,
                "all_groups",
                message_text,
                interval_seconds,
                time.time(),
            )
            settings["active_timed_broadcasts"][group_job_name] = True

            # Schedule job for all users (PMs)
            user_job_name = f"{job_name_base}_users_{job_name_timestamp}"
            job_data_users = {"target_type": "all_users", "message_text": message_text}
            # Stagger user broadcast slightly to avoid hitting API limits simultaneously with group broadcast
            user_first_run_delay = (interval_seconds / 2 if interval_seconds > 10 else 5
                                    )  # Delay by half interval or 5s, whichever is less (min 5s)
            context.job_queue.run_repeating(
                timed_broadcast_job_callback,
                interval=interval_seconds,
                first=user_first_run_delay,
                data=job_data_users,
                name=user_job_name,
            )
            await add_timed_broadcast_to_db(
                user_job_name,
                "all_users",
                message_text,
                interval_seconds,
                time.time() + user_first_run_delay,
            )
            settings["active_timed_broadcasts"][user_job_name] = True

            await send_message_safe(
                context,
                chat.id,
                f"Scheduled universal timed broadcast (groups and users) every {format_duration(interval_seconds)}.\nGroup Job: <code>{group_job_name}</code>, User Job: <code>{user_job_name}</code>\nMessage: {message_text[:100]}...",
                parse_mode=ParseMode.HTML,
            )
        else:
            await send_message_safe(
                context,
                chat.id,
                "JobQueue not available. Timed universal broadcast cannot be scheduled.",
            )
        return

    # Immediate bcastall
    await send_message_safe(
        context,
        chat.id,
        getattr(patterns, "BCASTALL_STARTED_MESSAGE",
                "Bcastall started.").format(format=(_detect_message_format(message_text) or "Plain Text")),
    )
    sent_g, failed_g = await _execute_broadcast(context, message_text, "all_groups", job_name_for_log="BcastAll-Groups")
    sent_u, failed_u = await _execute_broadcast(context, message_text, "all_users",
                                                job_name_for_log="BcastAll-Users")  # users who started bot

    await send_message_safe(
        context,
        chat.id,
        getattr(patterns, "BCASTALL_COMPLETE_MESSAGE", "Bcastall complete.").format(
            sent_groups=sent_g,
            failed_groups=failed_g,
            sent_users=sent_u,
            failed_users=failed_u,
        ),
    )


@feature_controlled("getsettings")
async def getsettings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /getsettings command (Admin only). Shows group settings."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return
    if chat.type not in [TGChat.GROUP, TGChat.SUPERGROUP]:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "COMMAND_GROUP_ONLY_MESSAGE",
                chat_id=chat.id,
                user_id=user.id,
                command_name="getsettings",
            ),
        )
        return

    # Check admin status (group admin or super admin)
    is_chat_admin_or_super = await _is_user_group_admin_or_creator(context, chat.id,
                                                                   user.id)  # Uses get_cached_admins (_mb)
    if not is_chat_admin_or_super:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "ADMIN_ONLY_COMMAND_MESSAGE", chat_id=chat.id, user_id=user.id),
        )
        return

    try:
        # Fetch group settings from DB (uses db_fetchone)
        group_settings_row = await db_fetchone("SELECT * FROM groups WHERE group_id = ?",
                                               (chat.id, ))  # Uses db_fetchone (Part 2)

        if not group_settings_row:
            await send_message_safe(context, chat.id, "Settings for this group not found in database.")  # Need pattern
            return

        settings_msg = (
            f"<b>Settings for {chat.title or 'this group'}:</b>\n"  # Need pattern
        )
        settings_msg += f"- Default Punish Action: {group_settings_row['punish_action']}\n"  # Need pattern
        # Need pattern
        settings_msg += f"- Punish Duration (Profile): {format_duration(group_settings_row['punish_duration_profile'] or 0)}\n"
        # Need pattern
        settings_msg += f"- Punish Duration (Message): {format_duration(group_settings_row['punish_duration_message'] or 0)}\n"
        # Need pattern
        settings_msg += f"- Punish Duration (Mention Profile): {format_duration(group_settings_row['punish_duration_mention_profile'] or 0)}\n"
        # Need pattern
        settings_msg += f"- Language Code: {group_settings_row['language_code'] or settings.get('default_lang', 'en')}\n"

        await send_message_safe(context, chat.id, settings_msg, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"DB error getting settings for group {chat.id}: {e}", exc_info=True)
        await send_message_safe(context, chat.id, f"Error getting settings: {e}")  # Need pattern


@feature_controlled("setsettings")
async def setsettings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /setsettings <setting_name> <value> command (Admin only). Sets specific group settings."""
    # This command offers more granular setting than setaction/setduration but requires careful implementation.
    # For example, /setsettings punish_action ban or /setsettings language_code es
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return
    if chat.type not in [TGChat.GROUP, TGChat.SUPERGROUP]:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(
                context,
                "COMMAND_GROUP_ONLY_MESSAGE",
                chat_id=chat.id,
                user_id=user.id,
                command_name="setsettings",
            ),
        )
        return

    # Check admin status (group admin or super admin)
    is_chat_admin_or_super = await _is_user_group_admin_or_creator(context, chat.id,
                                                                   user.id)  # Uses get_cached_admins (_mb)
    if not is_chat_admin_or_super:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "ADMIN_ONLY_COMMAND_MESSAGE", chat_id=chat.id, user_id=user.id),
        )
        return

    if len(context.args) < 2:
        # Need usage instructions and maybe list available settings
        await send_message_safe(
            context,
            chat.id,
            "Usage: /setsettings <setting_name> <value> or /setsettings list",
        )  # Need pattern
        return

    setting_name = context.args[0].lower()
    setting_value_raw = " ".join(context.args[1:])  # Value can have spaces

    # Handle listing available settings
    if setting_name == "list":
        available_settings = [
            "punish_action (mute|ban|kick)",
            "punish_duration_profile <duration>",
            "punish_duration_message <duration>",
            "punish_duration_mention_profile <duration>",
            "language_code <lang_code>",
        ]  # List of settable columns/logic names. Need pattern.
        list_msg = "<b>Available Group Settings:</b>\n" + "\n".join([f"- {s}"
                                                                     for s in available_settings])  # Need pattern
        await send_message_safe(context, chat.id, list_msg, parse_mode=ParseMode.HTML)
        return

    # If not listing, attempt to set the setting
    try:
        # This requires dynamic SQL based on setting_name, which is risky.
        # Safer: map setting_name to specific update logic.
        update_sql = None
        update_params = None
        success_message = None

        if setting_name == "punish_action":
            action = setting_value_raw.lower()
            if action not in ["mute", "ban", "kick"]:
                await send_message_safe(
                    context,
                    chat.id,
                    "Value for 'punish_action' must be 'mute', 'ban', or 'kick'.",
                )
                return
            update_sql = "UPDATE groups SET punish_action = ? WHERE group_id = ?"
            update_params = (action, chat.id)
            success_message = f"Default punish action set to '{action}'."

        elif setting_name in [
                "punish_duration_profile",
                "punish_duration_message",
                "punish_duration_mention_profile",
        ]:
            duration_seconds = parse_duration(setting_value_raw)  # Uses parse_duration (Part 2)
            if duration_seconds is None:
                await send_message_safe(
                    context,
                    chat.id,
                    await get_language_string(
                        context,
                        "INVALID_DURATION_FORMAT_MESSAGE",
                        chat_id=chat.id,
                        user_id=user.id,
                        duration_str=setting_value_raw,
                    ),
                )
                return
            column_name = setting_name  # Column name matches setting name
            update_sql = f"UPDATE groups SET {column_name} = ? WHERE group_id = ?"
            update_params = (duration_seconds, chat.id)
            duration_formatted = format_duration(duration_seconds)
            success_message = f"Punish duration for '{setting_name.replace('punish_duration_', '')}' set to {duration_formatted}."

        elif setting_name == "language_code":
            lang_code = setting_value_raw.lower()
            if lang_code not in LANGUAGES:
                available_langs_list = ", ".join(LANGUAGES.keys())
                await send_message_safe(
                    context,
                    chat.id,
                    f"Invalid language code '{lang_code}'. Available: {available_langs_list}",
                )
                return
            update_sql = "UPDATE groups SET language_code = ? WHERE group_id = ?"
            update_params = (lang_code, chat.id)
            lang_name = LANGUAGES.get(lang_code, {}).get("name", lang_code)
            success_message = await get_language_string(
                context,
                "LANG_UPDATED_GROUP",
                chat_id=chat.id,
                user_id=user.id,
                language_name=lang_name,
            )
            # Update in-memory chat_data cache immediately
            if context.application.chat_data.get(chat.id):
                context.application.chat_data.setdefault(chat.id, {})["language_code"] = lang_code
            else:
                context.application.chat_data[chat.id] = {"language_code": lang_code}  # Initialize if not exist

        else:
            await send_message_safe(
                context,
                chat.id,
                f"Unknown setting name: '{setting_name}'. Use /setsettings list to see available settings.",
            )  # Need pattern
            return

        # Execute the update if SQL and params are set
        if update_sql and update_params:
            cursor = await db_pool.execute(update_sql, update_params)
            if cursor.rowcount > 0:
                await send_message_safe(context, chat.id, success_message)
                logger.info(
                    f"Admin {user.id} set setting '{setting_name}' in group {chat.id} to '{setting_value_raw}'.")
            else:
                await send_message_safe(
                    context,
                    chat.id,
                    "Failed to update setting (group not found in DB?).",
                )  # Need pattern

    except Exception as e:
        logger.error(f"DB error setting '{setting_name}' in group {chat.id}: {e}", exc_info=True)
        await send_message_safe(context, chat.id, f"Error setting setting: {e}")  # Need pattern


@feature_controlled("cancelbroadcast")
async def cancelbroadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /cancelbroadcast <job_name or 'all'> command (Super Admin only)."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return
    if not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", user_id=user.id),
        )
        return

    if not context.args:
        await send_message_safe(context, chat.id, "Usage: /cancelbroadcast <job_name or 'all'>")  # Need pattern
        return

    target_job_name = context.args[0].lower()

    if not context.application.job_queue:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "JOBQUEUE_NOT_AVAILABLE_MESSAGE", user_id=user.id),
        )
        return

    cancelled_count = 0
    errors = []

    try:
        if target_job_name == "all":
            # Cancel all timed broadcast jobs
            jobs_to_cancel = context.application.job_queue.get_all_jobs()
            broadcast_jobs = [
                job for job in jobs_to_cancel
                if hasattr(job, "callback") and job.callback == timed_broadcast_job_callback
            ]

            if not broadcast_jobs:
                await send_message_safe(context, chat.id, "No timed broadcast jobs found to cancel.")  # Need pattern
                return

            for job in broadcast_jobs:
                try:
                    job.schedule_removal()  # Mark for removal
                    # Remove from DB as well
                    await remove_timed_broadcast_from_db(job.name)  # Uses remove_timed_broadcast_from_db (Part 2 logic)
                    cancelled_count += 1
                    logger.info(f"Cancelled timed broadcast job: {job.name}")
                except Exception as e:
                    errors.append(f"Error cancelling job '{job.name}': {e}")
                    logger.error(
                        f"Error cancelling timed broadcast job {job.name}: {e}",
                        exc_info=True,
                    )

            msg = f"Cancelled {cancelled_count} timed broadcast job(s)."  # Need pattern
            if errors:
                msg += "\nErrors:\n" + "\n".join(errors)
            await send_message_safe(context, chat.id, msg)

        else:  # Cancel a specific job by name
            jobs = context.application.job_queue.get_jobs_by_name(target_job_name)
            if not jobs:
                await send_message_safe(context, chat.id,
                                        f"No job found with name '{target_job_name}'.")  # Need pattern
                return

            # Assuming job names are unique identifiers for broadcasts, there should be at most one.
            job_to_cancel = jobs[0]

            # Verify it's a broadcast job to prevent cancelling random jobs by name
            if (hasattr(job_to_cancel, "callback") and job_to_cancel.callback == timed_broadcast_job_callback):
                try:
                    job_to_cancel.schedule_removal()  # Mark for removal
                    # Remove from DB
                    await remove_timed_broadcast_from_db(job_to_cancel.name
                                                         )  # Uses remove_timed_broadcast_from_db (Part 2 logic)
                    await send_message_safe(
                        context,
                        chat.id,
                        f"Timed broadcast job '{target_job_name}' cancelled.",
                    )  # Need pattern
                    logger.info(f"Super Admin {user.id} cancelled timed broadcast job: {target_job_name}.")
                except Exception as e:
                    logger.error(
                        f"Error cancelling timed broadcast job {target_job_name}: {e}",
                        exc_info=True,
                    )
                    await send_message_safe(
                        context,
                        chat.id,
                        f"Error cancelling job '{target_job_name}': {e}",
                    )  # Need pattern
            else:
                await send_message_safe(
                    context,
                    chat.id,
                    f"Job '{target_job_name}' is not a timed broadcast job.",
                )  # Need pattern

    except Exception as e:
        logger.error(f"Error in cancelbroadcast command: {e}", exc_info=True)
        await send_message_safe(context, chat.id, f"An unexpected error occurred: {e}")  # Need pattern


@feature_controlled("listbroadcasts")
async def listbroadcasts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /listbroadcasts command (Super Admin only). Lists active timed broadcast jobs."""
    user, chat = update.effective_user, update.effective_chat
    if not user or not chat:
        return
    if not await _is_super_admin(user.id):
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "SUPER_ADMIN_ONLY_COMMAND_MESSAGE", user_id=user.id),
        )
        return
    if not context.application.job_queue:
        await send_message_safe(
            context,
            chat.id,
            await get_language_string(context, "JOBQUEUE_NOT_AVAILABLE_MESSAGE", user_id=user.id),
        )
        return
    try:
        broadcast_jobs = [
            job for job in context.application.job_queue.get_all_jobs()
            if hasattr(job, "callback") and job.callback == timed_broadcast_job_callback
        ]
        if not broadcast_jobs:
            await send_message_safe(context, chat.id, "No active timed broadcast jobs.")
            return
        msg = "<b>Active Timed Broadcast Jobs:</b>\n"
        for job in broadcast_jobs:
            db_info = await db_fetchone(
                "SELECT target_type, target_id, interval_seconds, message_text FROM timed_broadcasts WHERE job_name = ?",
                (job.name, ),
            )
            job_details = [
                f"Name: <code>{job.name}</code>",
                f"Next Run: {job.next_run_time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
            ]
            if db_info:
                job_details += [
                    f"Target: {db_info['target_type']}{f' ({db_info['target_id']})' if db_info['target_id'] else ''}",
                    f"Interval: {format_duration(db_info['interval_seconds'])}",
                    f"Message Snippet: <i>{db_info['message_text'][:50].replace('\n', ' ') + ('...' if len(db_info['message_text']) > 50 else '')}</i>",
                ]
            msg += "- " + ", ".join(job_details) + "\n"
        await send_message_safe(context, chat.id, msg, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error listing broadcasts: {e}", exc_info=True)
        await send_message_safe(context, chat.id, f"Error listing broadcasts: {e}")


# -- Signal Handler ---

# This is crucial for graceful shutdown on SIGINT/SIGTERM


def signal_handler(signum, frame):
    """Handles OS signals for graceful shutdown."""
    logger.warning(f"Received signal {signum}. Initiating graceful shutdown.")
    global SHUTTING_DOWN
    SHUTTING_DOWN = True
    signal_name = (signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum))
    logger.warning(f"Shutdown requested via signal: {signal_name}")


# Register signal handlers early
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# --- Multi-Bot Aware API Call for Sending Documents ---
# Needed for DB dump feature.
async def send_document_safe_mb(
    initial_bot_instance: Any,  # Application or Bot object starting the attempt
    chat_id: int,
    document: Union[str, bytes, object],  # File path, bytes, or InputFile object
    # Add parameters for send_document if needed, or pass through kwargs
    **kwargs,
) -> Optional[TGMessage]:

    # Pass the send_document call as a factory function to the multi-bot executor
    def action_factory(bot_obj): return bot_obj.send_document(chat_id=chat_id, document=document, **kwargs)
    # Action name might include file name if available from 'document'
    action_name = f"send_document({chat_id})"

    try:
        # Execute the send_document action with multi-bot fallback
        # Use default retries/fallbacks from _execute_bot_action_mb
        sent_message = await _execute_bot_action_mb(initial_bot_instance, action_factory, action_name)
        return sent_message  # Return the sent Message object on success
    except (Forbidden, BadRequest) as e:
        # These are caught and logged by _execute_bot_action_mb before re-raising.
        # Add specific handling here if needed, e.g., remove group from DB on Forbidden.
        if isinstance(e, Forbidden) and chat_id < 0:
            logger.warning(
                f"Bot {initial_bot_instance.bot.id} forbidden to send document to group {chat_id}. Removing group from DB."
            )
            asyncio.create_task(remove_group_from_db(chat_id))  # Run DB removal in background task
        return None  # Return None on Forbidden or BadRequest
    except Exception as e:
        # Other exceptions re-raised by _execute_bot_action_mb
        # The error is already logged within _execute_bot_action_mb
        return None  # Return None on other failures


# --- Full take_action Implementation ---
# This function is the core of the anti-spam/moderation logic,
# taking action on users based on detected violations.
# It uses the _mb wrappers for API calls and interacts with the DB.
# It was conceptually introduced in Part 2 and refined in Part 5.
# Here is its complete body.

# Note: The code for `take_action` was partially included in Part 2's conceptual block
# to show its integration with the DB and basic structure. The full, correct
# implementation using the multi-bot wrappers (`restrict_chat_member_mb`, etc.)
# which were introduced in Part 4, is provided here as the complete function body.
# The version below incorporates multi-bot safety and db logging.
async def get_group_punish_action(group_id: int) -> str:
    """Get the punishment action for a group."""
    row = await db_fetchone(
        "SELECT punish_action FROM groups WHERE group_id = ?", (group_id,)
    )
    return row["punish_action"] if row and row["punish_action"] is not None else "restrict"


    
from telegram import ChatPermissions

async def restrict_chat_member_mb(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    permissions: dict,
    until_date: Optional[str] = None,
    **kwargs,
) -> bool:
    """Restricts a chat member with retry logic."""
    def action_factory(bot_obj: Bot):
        return bot_obj.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(**permissions),
            until_date=until_date,
            **kwargs,
        )
    
    try:
        await _execute_bot_action_mb(context.bot, action_factory, f"restrict_chat_member({chat_id},{user_id})")
        return True
    except (Forbidden, BadRequest):
        return False
    except Exception as e:
        logger.error(f"restrict_chat_member_mb: Unhandled exception for chat {chat_id}, user {user_id}: {e}", exc_info=True)
        return False
        
async def ban_chat_member_mb(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    until_date: Optional[str] = None,
    revoke_messages: bool = False,
    **kwargs,
) -> bool:
    """Bans a chat member with retry logic."""
    def action_factory(bot_obj: Bot):
        return bot_obj.ban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            until_date=until_date,
            revoke_messages=revoke_messages,
            **kwargs,
        )
    
    try:
        await _execute_bot_action_mb(context.bot, action_factory, f"ban_chat_member({chat_id},{user_id})")
        return True
    except (Forbidden, BadRequest):
        return False
    except Exception as e:
        logger.error(f"ban_chat_member_mb: Unhandled exception for chat {chat_id}, user {user_id}: {e}", exc_info=True)
        return False
        
import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple, Set
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, Bot, ChatPermissions
from telegram.error import Forbidden, BadRequest
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
import aiosqlite
import logging

# Initialize logging
logger = logging.getLogger(__name__)

# Assume global database pool (initialized elsewhere)
db_pool = None

# Assume settings and cache are defined globally
settings = {"free_users": set()}  # Replace with actual settings
notification_debounce_cache = {}  # Replace with actual cache implementation

# Mute permissions object
from telegram import ChatPermissions

mute_permissions_obj = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
    can_change_info=False,
    can_invite_users=False,
    can_pin_messages=False,
    can_manage_topics=False,
)

# LANGUAGE_STRINGS dictionary with required keys
LANGUAGE_STRINGS = {
    "PUNISHMENT_MESSAGE_SENDER": {
        "english": "<b>{user_mention}</b> has been {action_taken} due to {reason_detail}. {dialogue}",
        "hindi": "<b>{user_mention}</b> को {reason_detail} के कारण {action_taken} किया गया है। {dialogue}"
    },
    "PUNISHMENT_MESSAGE_MENTIONED": {
        "english": "Muted mentioned users: {user_list} for {duration} due to profile issues.",
        "hindi": "उल्लेखित उपयोगकर्ताओं को म्यूट किया गया: {user_list} को {duration} के लिए प्रोफाइल समस्याओं के कारण।"
    },
    "PUNISHMENT_DURATION_APPEND": {
        "english": "\nDuration: {duration}",
        "hindi": "\nअवधि: {duration}"
    },
    "UNMUTE_ME_BUTTON_TEXT": {
        "english": "Request Unmute",
        "hindi": "अनम्यूट का अनुरोध करें"
    },
    "ACTION_DEBOUNCED_SENDER": {
        "english": "Action on sender {user_id} in chat {chat_id} debounced.",
        "hindi": "चैट {chat_id} में प्रेषक {user_id} पर कार्रवाई डिबाउंस की गई।"
    },
    "ACTION_DEBOUNCED_MENTION": {
        "english": "Action on mentioned user {user_id} in chat {chat_id} debounced.",
        "hindi": "चैट {chat_id} में उल्लेखित उपयोगकर्ता {user_id} पर कार्रवाई डिबाउंस की गई।"
    },
    "NO_PERMS_TO_ACT_SENDER": {
        "english": "Bot lacks permission to {action} sender {user_id} in chat {chat_id}.",
        "hindi": "बॉट को चैट {chat_id} में प्रेषक {user_id} को {action} करने की अनुमति नहीं है।"
    },
    "NO_PERMS_TO_ACT_MENTION": {
        "english": "Bot lacks permission to act on mentioned user {user_id} (@{username}) in chat {chat_id}.",
        "hindi": "बॉट को चैट {chat_id} में उल्लेखित उपयोगकर्ता {user_id} (@{username}) पर कार्रवाई करने की अनुमति नहीं है।"
    },
    "BADREQUEST_TO_ACT_SENDER": {
        "english": "Bad request when attempting to {action} sender {user_id} in chat {chat_id}: {e}",
        "hindi": "चैट {chat_id} में प्रेषक {user_id} को {action} करने का प्रयास करते समय खराब अनुरोध: {e}"
    },
    "BADREQUEST_TO_ACT_MENTION": {
        "english": "Bad request when attempting to act on mentioned user {user_id} (@{username}) in chat {chat_id}: {e}",
        "hindi": "चैट {chat_id} में उल्लेखित उपयोगकर्ता {user_id} (@{username}) पर कार्रवाई करने का प्रयास करते समय खराब अनुरोध: {e}"
    },
    "ERROR_ACTING_SENDER": {
        "english": "Error {action} sender {user_id} in chat {chat_id}: {e}",
        "hindi": "चैट {chat_id} में प्रेषक {user_id} को {action} करने में त्रुटि: {e}"
    },
    "ERROR_ACTING_MENTION": {
        "english": "Error acting on mentioned user {user_id} (@{username}) in chat {chat_id}: {e}",
        "hindi": "चैट {chat_id} में उल्लेखित उपयोगकर्ता {user_id} (@{username}) पर कार्रवाई करने में त्रुटि: {e}"
    },
    "NEW_USER_PROFILE_VIOLATION_REASON": {
        "english": "Profile {field} violation: {issue_type}",
        "hindi": "प्रोफाइल {field} उल्लंघन: {issue_type}"
    },
    "MESSAGE_VIOLATION_REASON": {
        "english": "Message content violation: {message_issue_type}",
        "hindi": "संदेश सामग्री उल्लंघन: {message_issue_type}"
    },
    "SENDER_IS_BAD_ACTOR_REASON": {
        "english": "Sender is a known bad actor",
        "hindi": "प्रेषक एक ज्ञात खराब अभिनेता है"
    },
    "BIO_LINK_DIALOGUES_LIST": {
        "english": ["Please review the group rules.", "Follow the community guidelines."],
        "hindi": ["कृपया समूह नियमों की समीक्षा करें।", "समुदाय दिशानिर्देशों का पालन करें।"]
    },
}

async def get_language_string(
    context,
    key: str,
    chat_id: Optional[int] = None,
    user_id: Optional[int] = None,
    lang_code: Optional[str] = None,
    **format_kwargs
) -> str:
    """Retrieve and format a language string based on chat or user language settings."""
    # Determine the language to use
    if lang_code:
        lang = lang_code
    else:
        lang = "english"  # Default to English
        if chat_id:
            row = await db_fetchone("SELECT language_code FROM groups WHERE group_id = ?", (chat_id,))
            if row and row["language_code"]:
                lang = row["language_code"]
        elif user_id:
            row = await db_fetchone("SELECT language_code FROM users WHERE user_id = ?", (user_id,))
            if row and row["language_code"]:
                lang = row["language_code"]

    # Get the template from LANGUAGE_STRINGS
    template = LANGUAGE_STRINGS.get(key, {"english": key, "hindi": key})
    if isinstance(template, dict):
        template = template.get(lang, template.get("english", key))
    elif isinstance(template, list):
        template = random.choice(template) if template else key
    elif not isinstance(template, str):
        logger.warning(f"Invalid LANGUAGE_STRINGS['{key}']: {template}. Using key as fallback.")
        template = key

    # Format the string with provided kwargs
    try:
        return template.format(**format_kwargs)
    except KeyError as e:
        logger.error(f"Missing format key {e} for '{key}' in lang '{lang}'")
        return template
    except Exception as e:
        logger.error(f"Error formatting '{key}': {e}")
        return template

async def db_fetchone(query: str, params: tuple = ()) -> Optional[dict]:
    """Execute a query and fetch one row as a dictionary."""
    async with db_pool.execute(query, params) as cursor:
        row = await cursor.fetchone()
        if row and cursor.description:
            return dict(zip([col[0] for col in cursor.description], row))
        return None

async def db_execute(query: str, params: tuple = ()) -> None:
    """Execute a query and commit changes."""
    async with db_pool.execute(query, params) as cursor:
        await db_pool.commit()

async def get_chat_member_mb(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int):
    """Get chat member with type checking."""
    if not isinstance(context.bot, Bot):
        logger.error(f"Invalid bot type: {type(context.bot)} for get_chat_member({chat_id}, {user_id})")
        return None
    try:
        return await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except Exception as e:
        logger.error(f"Error in get_chat_member_mb: {e}")
        return None

async def ban_chat_member_mb(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    until_date: Optional[str] = None,
    revoke_messages: bool = False,
    **kwargs,
) -> bool:
    """Bans a chat member with retry logic."""
    if not isinstance(context.bot, Bot):
        logger.error(f"Invalid bot type: {type(context.bot)} for ban_chat_member({chat_id}, {user_id})")
        return False

    def action_factory(bot_obj: Bot):
        return bot_obj.ban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            until_date=until_date,
            revoke_messages=revoke_messages,
            **kwargs,
        )

    try:
        await _execute_bot_action_mb(context.bot, action_factory, f"ban_chat_member({chat_id},{user_id})")
        return True
    except (Forbidden, BadRequest):
        logger.warning(f"ban_chat_member_mb: Permission or bad request error for chat {chat_id}, user {user_id}")
        return False
    except Exception as e:
        logger.error(f"ban_chat_member_mb: Unhandled exception for chat {chat_id}, user {user_id}: {e}", exc_info=True)
        return False

async def unban_chat_member_mb(bot: Bot, chat_id: int, user_id: int, only_if_banned: bool = False) -> bool:
    """Unban a chat member with type checking."""
    if not isinstance(bot, Bot):
        logger.error(f"Invalid bot type: {type(bot)} for unban_chat_member({chat_id}, {user_id})")
        return False
    try:
        await bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=only_if_banned)
        return True
    except Exception as e:
        logger.error(f"Error in unban_chat_member_mb: {e}")
        return False

async def restrict_chat_member_mb(bot: Bot, chat_id: int, user_id: int, permissions: ChatPermissions, until_date=None) -> bool:
    """Restrict a chat member with type checking."""
    if not isinstance(bot, Bot):
        logger.error(f"Invalid bot type: {type(bot)} for restrict_chat_member({chat_id}, {user_id})")
        return False
    try:
        await bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions=permissions, until_date=until_date)
        return True
    except Exception as e:
        logger.error(f"Error in restrict_chat_member_mb: {e}")
        return False

async def send_message_safe(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, parse_mode=None, reply_to_message_id=None, reply_markup=None, **kwargs) -> None:
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_to_message_id=reply_to_message_id,
            reply_markup=reply_markup,
            **kwargs
        )
    except Exception as e:
        logger.error(f"Error sending message to chat {chat_id}: {e}")

async def get_group_punish_action(chat_id: int) -> str:
    """Get the punishment action for a group (stub)."""
    # Replace with actual implementation
    return "mute"

async def get_group_punish_duration_for_trigger(chat_id: int, trigger_type: str) -> int:
    """Get the punishment duration for a trigger (stub)."""
    # Replace with actual implementation
    return 3600  # 1 hour

async def is_user_exempt_in_group(chat_id: int, user_id: int) -> bool:
    """Check if a user is exempt in a group (stub)."""
    # Replace with actual implementation
    return False

async def log_action_db(context: ContextTypes.DEFAULT_TYPE, action: str, user_id: int, chat_id: int, reason: str, duration_seconds: Optional[int], sender_user_id: int) -> None:
    """Log an action to the database (stub)."""
    # Replace with actual implementation
    logger.info(f"Logging action: {action} on user {user_id} in chat {chat_id} for {reason}")

async def get_bot_username(context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
    """Get the bot's username (stub)."""
    # Replace with actual implementation
    return "@YourBot"

def format_duration(seconds: int) -> str:
    """Format duration in seconds to a human-readable string."""
    if seconds < 60:
        return f"{seconds} seconds"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minutes"
    hours = minutes // 60
    return f"{hours} hours"

async def take_action(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    reasons: List[str],
    sender_trigger_type: Optional[str],
    problematic_mentions_list: List[Tuple[str, int, Optional[str]]],
):
    """
    Performs punitive actions (mute, ban, kick) on users based on detected violations.
    Logs actions to the bot_restrictions table.
    Uses multi-bot enabled API call wrappers.
    Displays punishment messages in English first, followed by Hindi (default) or the group's language if set.
    """
    chat = update.effective_chat
    sender = update.effective_user
    message = update.effective_message

    if not chat or not sender or not message:
        logger.error("take_action called without chat, sender, or message.")
        return

    logger.debug(f"take_action: context.bot type = {type(context.bot)}, bot_id = {getattr(context.bot, 'id', 'unknown')}")

    sender_html_mention = (sender.mention_html()
                          if hasattr(sender, "mention_html") else f"@{sender.username or sender.id}")
    action_taken_on_sender_this_time = False
    actual_action_performed_on_sender: Optional[str] = None
    duration_seconds_for_sender_action: Optional[int] = None
    notified_users_in_group: Set[int] = set()

    if sender_trigger_type:
        is_globally_exempt = sender.id in settings.get("free_users", set())
        is_group_exempt = await is_user_exempt_in_group(chat.id, sender.id)
        if is_globally_exempt or is_group_exempt:
            logger.debug(f"Sender {sender.id} in chat {chat.id} is exempt. Skipping action.")
        else:
            debounce_key = f"punish_notification_{chat.id}_{sender.id}"
            if debounce_key in notification_debounce_cache:
                logger.debug(await get_language_string(
                    context,
                    "ACTION_DEBOUNCED_SENDER",
                    chat_id=chat.id,
                    user_id=sender.id,
                ))
            else:
                notification_debounce_cache[debounce_key] = True

                group_action_on_sender = await get_group_punish_action(chat.id)
                duration_seconds_sender = await get_group_punish_duration_for_trigger(chat.id, sender_trigger_type)
                duration_seconds_for_sender_action = duration_seconds_sender

                row = await db_fetchone("SELECT language_code FROM groups WHERE group_id = ?", (chat.id,))
                group_lang_code = row["language_code"] if row and row["language_code"] else "hindi"

                dialogue_list = await get_language_string(
                    context,
                    "BIO_LINK_DIALOGUES_LIST",
                    chat_id=chat.id,
                    user_id=sender.id,
                )
                dialogue_entry = random.choice(dialogue_list) if isinstance(dialogue_list, list) and dialogue_list else "Please review the rules."
                dialogue_text = dialogue_entry if isinstance(dialogue_entry, str) else dialogue_entry.get("english", str(dialogue_entry))

                reason_parts_display: List[str] = []
                if sender_trigger_type == "profile":
                    reason_parts_display.append(await get_language_string(
                        context,
                        "NEW_USER_PROFILE_VIOLATION_REASON",
                        chat_id=chat.id,
                        user_id=sender.id,
                        field="profile",
                        issue_type=", ".join(reasons),
                    ))
                elif sender_trigger_type == "message":
                    reason_parts_display.append(await get_language_string(
                        context,
                        "MESSAGE_VIOLATION_REASON",
                        chat_id=chat.id,
                        user_id=sender.id,
                        message_issue_type=", ".join(reasons),
                    ))
                elif sender_trigger_type == "mention_profile":
                    logger.warning(f"Sender trigger type 'mention_profile' unexpectedly set for sender {sender.id}.")
                    reason_parts_display.append(f"violation: {', '.join(reasons)}")
                elif sender_trigger_type == "bad_actor":
                    bad_actor_reason_text = await get_language_string(
                        context,
                        "SENDER_IS_BAD_ACTOR_REASON",
                        chat_id=chat.id,
                        user_id=sender.id,
                    )
                    reason_parts_display.append(bad_actor_reason_text)
                else:
                    reason_parts_display.append(f"violation: {', '.join(reasons)}")

                reason_detail_for_sender = "; ".join(reason_parts_display)

                english_message = await get_language_string(
                    context,
                    "PUNISHMENT_MESSAGE_SENDER",
                    lang_code="english",
                    user_mention=sender_html_mention,
                    action_taken=group_action_on_sender.capitalize(),
                    reason_detail=reason_detail_for_sender,
                    dialogue=dialogue_text,
                )

                second_lang_message = await get_language_string(
                    context,
                    "PUNISHMENT_MESSAGE_SENDER",
                    lang_code=group_lang_code,
                    user_mention=sender_html_mention,
                    action_taken=group_action_on_sender.capitalize(),
                    reason_detail=reason_detail_for_sender,
                    dialogue=dialogue_text,
                )

                punishment_msg_sender_display = (english_message if group_lang_code == "english"
                                                else f"{english_message}\n\n{second_lang_message}")

                if group_action_on_sender == "mute" and duration_seconds_sender and duration_seconds_sender > 0:
                    duration_append = await get_language_string(
                        context,
                        "PUNISHMENT_DURATION_APPEND",
                        lang_code="english",
                        duration=format_duration(duration_seconds_sender),
                    )
                    second_lang_duration_append = await get_language_string(
                        context,
                        "PUNISHMENT_DURATION_APPEND",
                        lang_code=group_lang_code,
                        duration=format_duration(duration_seconds_sender),
                    )
                    duration_msg = (duration_append if group_lang_code == "english"
                                   else f"{duration_append}\n\n{second_lang_duration_append}")
                    punishment_msg_sender_display += duration_msg

                bot_can_act = False
                try:
                    bot_member = await get_chat_member_mb(context, chat.id, context.bot.id)
                    if bot_member:
                        has_restrict_permission = getattr(bot_member, "can_restrict_members", False)
                        has_ban_permission = getattr(bot_member, "can_delete_members", False)
                        if group_action_on_sender == "ban" and has_ban_permission:
                            bot_can_act = True
                        elif group_action_on_sender == "kick" and has_ban_permission:
                            bot_can_act = True
                        elif group_action_on_sender == "mute" and has_restrict_permission:
                            bot_can_act = True
                    else:
                        logger.warning(f"Failed to get bot member status for chat {chat.id}: bot_member is None")
                except Exception as e:
                    logger.warning(f"Failed to get bot member status in chat {chat.id}: {e}")
                    bot_can_act = False

                if not bot_can_act:
                    logger.warning(await get_language_string(
                        context,
                        "NO_PERMS_TO_ACT_SENDER",
                        chat_id=chat.id,
                        user_id=sender.id,
                        action=group_action_on_sender,
                    ))
                else:
                    applied_at_iso = datetime.now(timezone.utc).isoformat()
                    expires_at_iso: Optional[str] = None

                    try:
                        if group_action_on_sender == "ban":
                            success = await ban_chat_member_mb(context.bot, chat.id, sender.id, revoke_messages=True)
                            if success:
                                action_taken_on_sender_this_time = True
                                actual_action_performed_on_sender = "ban"
                                await db_execute(
                                    """INSERT OR REPLACE INTO bot_restrictions (user_id, chat_id, restriction_type, applied_at, expires_at, is_active, reason, applied_by_admin_id)
                                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                                    (sender.id, chat.id, "ban", applied_at_iso, None, 1, reason_detail_for_sender[:1000], context.bot.id),
                                )
                                logger.info(f"Bot banned user {sender.id} in chat {chat.id} due to {reason_detail_for_sender[:100]}.")

                        elif group_action_on_sender == "kick":
                            ban_success = await ban_chat_member_mb(context.bot, chat.id, sender.id)
                            if ban_success:
                                await asyncio.sleep(0.5)
                                unban_success = await unban_chat_member_mb(context.bot, chat.id, sender.id, only_if_banned=True)
                                if unban_success:
                                    action_taken_on_sender_this_time = True
                                    actual_action_performed_on_sender = "kick"
                                    logger.info(f"Bot kicked user {sender.id} in chat {chat.id} due to {reason_detail_for_sender[:100]}.")
                                else:
                                    logger.warning(f"Bot banned user {sender.id} in chat {chat.id} but failed to unban after kick attempt.")

                        else:  # Mute
                            until_date_sender = (datetime.now(timezone.utc) + timedelta(seconds=duration_seconds_sender)
                                                if duration_seconds_sender and duration_seconds_sender > 0 else None)
                            if until_date_sender:
                                expires_at_iso = until_date_sender.isoformat()
                            success = await restrict_chat_member_mb(
                                context.bot,
                                chat.id,
                                sender.id,
                                mute_permissions_obj,
                                until_date=until_date_sender,
                            )
                            if success:
                                action_taken_on_sender_this_time = True
                                actual_action_performed_on_sender = "mute"
                                await db_execute(
                                    """INSERT OR REPLACE INTO bot_restrictions (user_id, chat_id, restriction_type, applied_at, expires_at, is_active, reason, applied_by_admin_id)
                                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                                    (sender.id, chat.id, "mute", applied_at_iso, expires_at_iso, 1, reason_detail_for_sender[:1000], context.bot.id),
                                )
                                logger.info(f"Bot muted user {sender.id} in chat {chat.id} for {duration_seconds_sender}s due to {reason_detail_for_sender[:100]}.")

                        if action_taken_on_sender_this_time and actual_action_performed_on_sender:
                            await log_action_db(
                                context,
                                actual_action_performed_on_sender.capitalize(),
                                sender.id,
                                chat.id,
                                reason_detail_for_sender,
                                duration_seconds=duration_seconds_for_sender_action,
                                sender_user_id=context.bot.id,
                            )

                            reply_markup = None
                            if actual_action_performed_on_sender == "mute" and duration_seconds_for_sender_action and duration_seconds_for_sender_action > 0:
                                unmute_me_button_text = await get_language_string(
                                    context,
                                    "UNMUTE_ME_BUTTON_TEXT",
                                    chat_id=chat.id,
                                    user_id=sender.id,
                                )
                                bot_username = (await get_bot_username(context) or "your_bot").lstrip("@")
                                start_payload = f"unmuteme_{chat.id}"
                                button_url = f"https://t.me/{bot_username}?start={start_payload}"
                                reply_markup = InlineKeyboardMarkup(
                                    [[InlineKeyboardButton(unmute_me_button_text, url=button_url)]]
                                )

                            await send_message_safe(
                                context,
                                chat.id,
                                punishment_msg_sender_display,
                                parse_mode=ParseMode.HTML,
                                reply_to_message_id=message.message_id if message else None,
                                reply_markup=reply_markup,
                            )
                            notified_users_in_group.add(sender.id)

                    except Forbidden:
                        logger.error(await get_language_string(
                            context,
                            "NO_PERMS_TO_ACT_SENDER",
                            chat_id=chat.id,
                            user_id=sender.id,
                            action=group_action_on_sender,
                        ))
                    except BadRequest as e:
                        logger.error(await get_language_string(
                            context,
                            "BADREQUEST_TO_ACT_SENDER",
                            chat_id=chat.id,
                            user_id=sender.id,
                            action=group_action_on_sender,
                            e=str(e),
                        ))
                    except Exception as e:
                        logger.error(await get_language_string(
                            context,
                            "ERROR_ACTING_SENDER",
                            chat_id=chat.id,
                            user_id=sender.id,
                            action=group_action_on_sender,
                            e=str(e),
                        ), exc_info=True)

    if problematic_mentions_list:
        mention_action_on_user = "mute"
        duration_seconds_mention = await get_group_punish_duration_for_trigger(chat.id, "mention_profile")

        row = await db_fetchone("SELECT language_code FROM groups WHERE group_id = ?", (chat.id,))
        group_lang_code = row["language_code"] if row and row["language_code"] else "hindi"

        bot_can_restrict = False
        try:
            bot_member = await get_chat_member_mb(context, chat.id, context.bot.id)
            if bot_member:
                bot_can_restrict = getattr(bot_member, "can_restrict_members", False)
        except Exception as e:
            logger.error(f"Failed to get bot member status in {chat.id} for mention actions: {e}")
            bot_can_restrict = False

        if not bot_can_restrict:
            logger.warning(await get_language_string(
                context,
                "NO_PERMS_TO_ACT_MENTION",
                chat_id=chat.id,
                user_id=None,
                username="[any]",
            ))
        else:
            muted_mentioned_display_list: List[str] = []
            applied_at_iso_mention = datetime.now(timezone.utc).isoformat()
            expires_at_iso_mention: Optional[str] = None
            until_date_mention = (datetime.now(timezone.utc) + timedelta(seconds=duration_seconds_mention)
                                 if duration_seconds_mention and duration_seconds_mention > 0 else None)
            if until_date_mention:
                expires_at_iso_mention = until_date_mention.isoformat()

            for p_uname, p_uid, p_issue_type in problematic_mentions_list:
                if p_uid == sender.id and action_taken_on_sender_this_time:
                    logger.debug(f"Skipping action on mentioned user {p_uid} in chat {chat.id} as they are the sender and already actioned.")
                    continue

                is_globally_exempt_mention = p_uid in settings.get("free_users", set())
                is_group_exempt_mention = await is_user_exempt_in_group(chat.id, p_uid)
                if is_globally_exempt_mention or is_group_exempt_mention:
                    logger.debug(f"Mentioned user {p_uid} in chat {chat.id} is exempt. Skipping action.")
                    continue

                mention_debounce_key = f"punish_notification_{chat.id}_{p_uid}_mention"
                if mention_debounce_key in notification_debounce_cache:
                    logger.debug(await get_language_string(
                        context,
                        "ACTION_DEBOUNCED_MENTION",
                        chat_id=chat.id,
                        user_id=p_uid,
                    ))
                    continue
                notification_debounce_cache[mention_debounce_key] = True

                try:
                    success = await restrict_chat_member_mb(
                        context.bot,
                        chat.id,
                        p_uid,
                        mute_permissions_obj,
                        until_date=until_date_mention,
                    )
                    if success:
                        mention_reason = f"Profile issue ({p_issue_type or 'unknown'}) when mentioned by {sender.id} (@{sender.username or sender.id})"
                        await db_execute(
                            """INSERT OR REPLACE INTO bot_restrictions (user_id, chat_id, restriction_type, applied_at, expires_at, is_active, reason, applied_by_admin_id)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (p_uid, chat.id, "mute", applied_at_iso_mention, expires_at_iso_mention, 1, mention_reason[:1000], context.bot.id),
                        )
                        await log_action_db(
                            context,
                            "Mute (Mentioned)",
                            p_uid,
                            chat.id,
                            mention_reason,
                            duration_seconds=duration_seconds_mention,
                            sender_user_id=context.bot.id,
                        )
                        mentioned_user_mention = f"@{p_uname}" if p_uname else f"User ID {p_uid}"
                        muted_mentioned_display_list.append(mentioned_user_mention)
                        logger.info(f"Bot muted mentioned user {p_uid} in chat {chat.id} for {duration_seconds_mention}s due to profile issue.")

                except Forbidden:
                    logger.warning(await get_language_string(
                        context,
                        "NO_PERMS_TO_ACT_MENTION",
                        chat_id=chat.id,
                        user_id=p_uid,
                        username=p_uname or "unknown",
                    ))
                except BadRequest as e:
                    if "user not found" in str(e).lower() or "member not found" in str(e).lower():
                        logger.debug(f"Mentioned user @{p_uname} ({p_uid}) not in group {chat.id}. Cannot mute.")
                    else:
                        logger.warning(await get_language_string(
                            context,
                            "BADREQUEST_TO_ACT_MENTION",
                            chat_id=chat.id,
                            user_id=p_uid,
                            username=p_uname or "unknown",
                            e=str(e),
                        ))
                except Exception as e:
                    logger.error(await get_language_string(
                        context,
                        "ERROR_ACTING_MENTION",
                        chat_id=chat.id,
                        user_id=p_uid,
                        username=p_uname or "unknown",
                        e=str(e),
                    ), exc_info=True)

            if muted_mentioned_display_list:
                muted_list_str = ", ".join(muted_mentioned_display_list)
                english_mention_message = await get_language_string(
                    context,
                    "PUNISHMENT_MESSAGE_MENTIONED",
                    lang_code="english",
                    user_list=muted_list_str,
                    duration=format_duration(duration_seconds_mention),
                )
                second_lang_mention_message = await get_language_string(
                    context,
                    "PUNISHMENT_MESSAGE_MENTIONED",
                    lang_code=group_lang_code,
                    user_list=muted_list_str,
                    duration=format_duration(duration_seconds_mention),
                )
                mention_punishment_msg = (english_mention_message if group_lang_code == "english"
                                         else f"{english_mention_message}\n\n{second_lang_mention_message}")
                await send_message_safe(context, chat.id, mention_punishment_msg, parse_mode=ParseMode.HTML)

                
                

# main.py - Part 12 of 20

# --- Chat Member and Update Handlers ---


async def log_other_admin_actions_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Processes messages in groups that appear to be admin commands from other admins or bots
    and logs them to the database. This helps track actions taken by others.
    Registered for filters.ChatType.GROUPS.
    """
    chat = update.effective_chat
    message = update.effective_message
    sender = update.effective_user

    # Basic checks
    if not chat or not message or not sender or chat.type == TGChat.PRIVATE:
        return  # Only process messages in groups

    # Ignore messages from the bot itself
    if sender.id == context.bot.id:
        logger.debug(f"Ignoring own message {message.message_id} from bot {sender.id} for admin action logging.")
        return

    # We only want to log actions taken by other admins (or bots acting as admins).
    # Check if the sender is an admin in this group.
    # Use _is_user_group_admin_or_creator which uses cached admins (uses _mb)
    is_sender_admin = await _is_user_group_admin_or_creator(context, chat.id, sender.id)

    # Allow logging actions from other bots if they are not explicitly ignored?
    # The primary goal is to track admin actions, so checking if the sender *is* an admin is key.
    # If a bot is an admin, its command messages should be logged if they match patterns.
    # If a non-admin bot sends a message, it's handled by the main handle_message (which ignores bots).
    # So, only proceed if the sender is a recognized admin (user or bot admin).

    if not is_sender_admin:
        logger.debug(
            f"Ignoring message {message.message_id} from non-admin user {sender.id} in chat {chat.id} for admin action logging."
        )
        return  # Only process messages from admins (or super admins, but they are already excluded globally)

    # Ensure the message contains text that could be a command
    command_text = message.text or message.caption
    if not command_text or not command_text.startswith(
            tuple(COMMAND_PATTERNS.get("initiators", {}).get("values", ["/", "!", "."]))):
        # Not a command starting with a recognized initiator
        logger.debug(
            f"Ignoring non-command message {message.message_id} from admin {sender.id} in chat {chat.id} for admin action logging."
        )
        return

    # Attempt to parse the command using the refined parser
    # Pass context to the parser for potential username resolution (uses _mb)
    parsed_data = await parse_admin_command(command_text, context=context)  # Uses parse_admin_command (Part 6 logic)

    # If a relevant action and target were parsed, log it
    if parsed_data.get("action_type") and (parsed_data.get("target_identifier") or parsed_data.get("target_user_id")):
        logger.info(
            f"Detected potential admin action from user {sender.id} in chat {chat.id}: {parsed_data['action_type']} on {parsed_data.get('target_identifier') or parsed_data.get('target_user_id')}"
        )

        # Log the action to the observed_admin_actions table
        # log_action_db signature: context, action_type, target_user_id, chat_id, reason, duration_seconds, sender_user_id

        # Try to resolve the target user ID if only identifier was parsed
        target_user_id_to_log = parsed_data.get("target_user_id")
        if target_user_id_to_log is None and parsed_data.get("target_identifier"):
            if parsed_data["target_identifier"].startswith("@"):
                resolved_id, _ = await is_real_telegram_user_cached(context,
                                                                    parsed_data["target_identifier"])  # Uses _mb
                target_user_id_to_log = resolved_id
            elif parsed_data["target_identifier"].lstrip("-").isdigit():
                try:
                    target_user_id_to_log = int(parsed_data["target_identifier"])
                except ValueError:
                    pass  # Not a valid ID

        if target_user_id_to_log:
            await log_action_db(
                context,  # Pass context for potential future use in log_action_db (e.g., language)
                parsed_data["action_type"].capitalize(),  # e.g., 'Mute', 'Ban'
                target_user_id_to_log,
                chat.id,
                parsed_data.get("reason") or "No reason parsed.",
                parsed_data.get("duration_seconds"),
                sender_user_id=sender.id,  # The admin who sent the message
            )  # Uses log_action_db (Part 2 logic, implemented in Part 11)
        else:
            logger.warning(
                f"Could not resolve target for admin action logging in chat {chat.id}, msg {message.message_id}. Parsed data: {parsed_data}"
            )

from telegram import Update, Bot, User as TGUser, ChatPermissions
from telegram.ext import ContextTypes
from logging import getLogger
import time

logger = getLogger(__name__)

async def _check_new_member_profile_and_act(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: TGUser,
    group_punish_action: str,
    profile_punish_duration: int,
) -> None:
    """Check new member's profile and apply punishment if needed."""
    chat = update.chat_member.chat

    # Validate bot instance
    if not isinstance(context.bot, Bot):
        logger.error(f"Invalid bot instance for chat {chat.id}")
        return

    # Fetch user profile
    user_chat = await get_user_mb(context, user.id)
    if not user_chat:
        logger.warning(f"Could not fetch profile for user {user.id} in chat {chat.id}")
        return

    # Check for links in profile fields (bio, username, name)
    fields_to_check = [
        (user_chat.bio, "bio") if user_chat.bio else None,
        (user_chat.username, "username") if user_chat.username else None,
        (f"{user_chat.first_name or ''} {user_chat.last_name or ''}".strip(), "name"),
    ]

    for text, source_field in [f for f in fields_to_check if f]:
        if not text:
            continue
        has_links, issue_type = await check_for_links_enhanced(context, text, source_field)
        if has_links:
            logger.info(f"Detected {issue_type} in {source_field} for user {user.id} in chat {chat.id}: '{text}'")
            # Apply punishment based on group_punish_action
            if group_punish_action == "restrict" and profile_punish_duration > 0:
                until_date = int(time.time()) + profile_punish_duration
                await restrict_chat_member_mb(
                    context,
                    chat.id,
                    user.id,
                    until_date=until_date,
                    permissions=ChatPermissions(can_send_messages=False),
                )
                logger.info(f"Restricted user {user.id} in chat {chat.id} for {profile_punish_duration}s")
            elif group_punish_action == "ban":
                await ban_chat_member_mb(context, chat.id, user.id)
                logger.info(f"Banned user {user.id} from chat {chat.id}")
            else:
                logger.debug(f"No action taken for user {user.id} in chat {chat.id} due to invalid punish_action")
            return  # Stop after first issue found

    logger.debug(f"User {user.id} profile has no issues in chat {chat.id}")
# Handler for new chat members - This was conceptually in Part 3 logic block
# Needs implementation in a future part.
async def new_chat_members_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles new chat members joining a group."""
    chat = update.effective_chat
    new_members = update.message.new_chat_members

    if not chat or not new_members or chat.type == TGChat.PRIVATE:
        return  # Only process in groups with new members

    logger.info(f"New members joined chat {chat.id} ({chat.title}): {[m.id for m in new_members]}")

    # Get group settings (punish action and duration) using DB helpers (Part 12 logic)
    group_punish_action = await get_group_punish_action(chat.id)
    profile_punish_duration = await get_group_punish_duration_for_trigger(chat.id, "profile")

    for member in new_members:
        if member.is_bot:
            logger.debug(f"Ignoring new bot member {member.id} in chat {chat.id}.")
            continue  # Ignore bots joining

        # Check if user is exempt in this group (Part 12 logic)
        is_globally_exempt = member.id in settings.get("free_users", set())
        is_group_exempt = await is_user_exempt_in_group(chat.id, member.id)
        if is_globally_exempt or is_group_exempt:
            logger.debug(f"New user {member.id} is exempt in chat {chat.id}. Skipping checks.")
            continue

        # Check user profile for issues using cached helper (uses user_has_links_cached which uses _mb)
        # This should be done in the background to not block the handler
        asyncio.create_task(
            _check_new_member_profile_and_act(update, context, member, group_punish_action, profile_punish_duration))

from telegram.ext import ChatMemberHandler
from telegram.constants import ChatMemberStatus

from typing import Set

# Global set to track processed join events (in-memory, consider Redis for persistence)
processed_joins: Set[str] = set()
import asyncio
from telegram.error import RetryAfter, TelegramError

async def rate_limited_api_call(api_call, *args, **kwargs):
    """
    Execute a Telegram API call with rate limit handling.
    
    Args:
        api_call: The Telegram API method to call (e.g., bot.send_message).
        *args: Positional arguments for the API call.
        **kwargs: Keyword arguments for the API call.
    
    Returns:
        The result of the API call.
    
    Raises:
        TelegramError: If the API call fails after retries.
    """
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            return await api_call(*args, **kwargs)
        except RetryAfter as e:
            wait_time = e.retry_after + 1
            print(f"Rate limit hit, waiting {wait_time} seconds...")
            await asyncio.sleep(wait_time)
        except TelegramError as e:
            if attempt == max_attempts - 1:
                raise
            print(f"API call failed: {e}, retrying...")
            await asyncio.sleep(1)
    raise TelegramError("Max retries reached for API call")
    
async def user_chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.chat_member:
        logger.debug("Ignoring update without chat_member")
        return

    chat_member_update = update.chat_member
    chat = chat_member_update.chat
    user = chat_member_update.new_chat_member.user
    old_status = chat_member_update.old_chat_member.status
    new_status = chat_member_update.new_chat_member.status

    if not isinstance(context.bot, Bot):
        logger.error(f"Invalid bot instance for chat {chat.id}")
        return

    # Create a unique key for the join event
    join_key = f"{chat.id}:{user.id}:{int(time.time())}"
    if old_status == ChatMemberStatus.LEFT and new_status == ChatMemberStatus.MEMBER:
        if join_key in processed_joins:
            logger.debug(f"Skipping duplicate join for user {user.id} in chat {chat.id}")
            return
        processed_joins.add(join_key)
        # Clean up old keys (e.g., after 60 seconds)
        asyncio.create_task(cleanup_processed_joins())

    logger.info(
        f"User {user.id} ({user.username}) status changed in chat {chat.id}: {old_status} -> {new_status}"
    )

    if old_status == ChatMemberStatus.LEFT and new_status == ChatMemberStatus.MEMBER:
        if user.is_bot:
            logger.debug(f"Ignoring bot member {user.id} in chat {chat.id}")
            return

        group_punish_action = await get_group_punish_action(chat.id)
        profile_punish_duration = await get_group_punish_duration_for_trigger(chat.id, "profile")

        is_globally_exempt = user.id in settings.get("free_users", set())
        is_group_exempt = await is_user_exempt_in_group(chat.id, user.id)
        if is_globally_exempt or is_group_exempt:
            logger.debug(f"New user {user.id} is exempt in chat {chat.id}. Skipping checks.")
            return

        asyncio.create_task(
            rate_limited_api_call(
                _check_new_member_profile_and_act,
                update, context, user, group_punish_action, profile_punish_duration
            )
        )
    elif new_status == ChatMemberStatus.LEFT:
        logger.info(f"User {user.id} left chat {chat.id}")
    elif new_status == ChatMemberStatus.RESTRICTED:
        logger.info(f"User {user.id} restricted in chat {chat.id}")
        
async def new_chat_members_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles new chat members joining a group."""
    if not update.message or not update.message.new_chat_members:
        logger.debug("Ignoring update without message or new_chat_members")
        return

    chat = update.effective_chat
    new_members = update.message.new_chat_members

    if not chat or chat.type == "private":
        logger.debug(f"Ignoring private chat or missing chat: {chat.id if chat else None}")
        return

    # Validate bot instance
    if not isinstance(context.bot, Bot):
        logger.error(f"Invalid bot instance for chat {chat.id}")
        return

    # Check bot permissions
    if not await check_bot_permissions(context.bot, chat.id):
        logger.warning(f"Bot lacks permissions in chat {chat.id}")
        return

    logger.info(f"New members joined chat {chat.id} ({chat.title}): {[m.id for m in new_members]}")

    # Get group settings
    group_punish_action = await get_group_punish_action(chat.id)
    profile_punish_duration = await get_group_punish_duration_for_trigger(chat.id, "profile")

    for member in new_members:
        if member.is_bot:
            logger.debug(f"Ignoring new bot member {member.id} in chat {chat.id}")
            continue

        # Check for duplicate join
        join_key = f"{chat.id}:{member.id}:{int(time.time())}"
        if join_key in processed_joins:
            logger.debug(f"Skipping duplicate join for user {member.id} in chat {chat.id}")
            continue
        processed_joins.add(join_key)
        asyncio.create_task(cleanup_processed_joins())

        # Check exemptions
        is_globally_exempt = member.id in settings.get("free_users", set())
        is_group_exempt = await is_user_exempt_in_group(chat.id, member.id)
        if is_globally_exempt or is_group_exempt:
            logger.debug(f"New user {member.id} is exempt in chat {chat.id}. Skipping checks.")
            continue

        # Check user profile in the background with rate limiting
        asyncio.create_task(
            rate_limited_api_call(
                _check_new_member_profile_and_act,
                update, context, member, group_punish_action, profile_punish_duration
            )
        )
        
async def cleanup_processed_joins():
    """Remove old join keys after 60 seconds."""
    await asyncio.sleep(60)
    current_time = int(time.time())
    for key in list(processed_joins):
        key_time = int(key.split(":")[-1])
        if current_time - key_time > 60:
            processed_joins.discard(key)
async def pm_unmute_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Handle unmute button press; assumes user clicked "Unmute Me"
    user_id = query.from_user.id
    group_id = int(query.data.split("_")[-1])  # Assuming data format like "unmute_123"
    success = await unmute_user(context, group_id, user_id, query.from_user)
    if success:
        await query.message.reply_text(
            await get_language_string("UNMUTE_ME_SUCCESS_GROUP_CMD", group_id=group_id, group_name="this group")
        )
    else:
        await query.message.reply_text(
            await get_language_string("UNMUTE_ME_FAIL_GROUP_CMD", group_id=group_id, group_name="this group")
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Handle generic button presses (e.g., language selection)
    if query.data.startswith("lang_"):
        lang_code = query.data.split("_")[1]
        await set_group_language(query.message.chat_id, lang_code)
        await query.message.reply_text(f"Language set to {lang_code}")

async def new_members_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        await check_new_member(context, update.message.chat_id, member)

async def left_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Log member leaving (no action needed per main.py)
    logger.info(f"User {update.message.left_chat_member.id} left chat {update.message.chat_id}")

async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle status changes (e.g., admin promotions)
    member = update.chat_member
    if member.new_chat_member.status in ["administrator", "creator"]:
        await update_admin_cache(context, member.chat.id, member.new_chat_member.user.id)

async def check_exemption_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    is_exempt = await is_user_exempt_in_group(chat_id, user_id)
    await update.message.reply_text(
        f"You {'are' if is_exempt else 'are not'} exempt from restrictions in this group."
    )

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        await get_language_string("UNKNOWN_COMMAND_MESSAGE", chat_id=update.effective_chat.id)
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check photo captions for prohibited content
    if update.message.caption:
        await check_message_content(update, context, update.message.caption)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check document captions for prohibited content
    if update.message.caption:
        await check_message_content(update, context, update.message.caption)

async def handle_idle_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Placeholder for idle state handling (no-op per main.py)
    pass

async def handle_misc_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle non-command text messages
    await check_message_content(update, context, update.message.text)

# Helper function to take action on a specific user ID
async def _take_action_on_user(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    target_user_id: int,
    reasons: List[str],
    action_type: str,
    duration_seconds: int,
    trigger_message_id: Optional[int] = None,
):
    """Performs a punitive action on a specific user ID based on parameters."""
    chat = update.effective_chat
    # We need the bot object to perform API calls
    bot = context.bot

    if not chat or not bot:
        logger.error("_take_action_on_user called without chat or bot.")
        return

    target_user_mention = f"User ID {target_user_id}"  # Fallback mention
    try:
        # Try to fetch user info to get mention_html using get_chat_mb (_mb)
        target_user_chat = await get_chat_mb(context.bot, target_user_id)  # Use _mb
        if target_user_chat and hasattr(target_user_chat, "mention_html"):
            target_user_mention = target_user_chat.mention_html()
        elif target_user_chat and target_user_chat.username:
            target_user_mention = f"@{target_user_chat.username}"
        elif target_user_chat and target_user_chat.first_name:
            target_user_mention = target_user_chat.first_name
    except Exception:
        logger.debug(f"Could not fetch target user info {target_user_id} for mention in _take_action_on_user.")

    applied_at_iso = datetime.now(timezone.utc).isoformat()
    expires_at_iso: Optional[str] = None  # ISO format for DB

    # Check bot's permissions before attempting action using get_chat_member_mb (_mb)
    bot_can_act = False
    required_permission = ("can_restrict_members" if action_type == "mute" else "can_ban_members")
    try:
        bot_member = await get_chat_member_mb(context.bot, chat.id, context.bot.id)  # Use _mb version
        if bot_member and (bot_member.status == ChatMemberStatus.OWNER or
                           getattr(bot_member, required_permission, False)):
            bot_can_act = True
    except Exception:  # get_chat_member_mb might fail
        logger.warning(f"Failed to get bot member status in chat {chat.id} for action permission check.")
        bot_can_act = False

    if not bot_can_act:
        logger.warning(await get_language_string(
            context,
            "NO_PERMS_TO_ACT_SENDER",
            chat_id=chat.id,
            user_id=target_user_id,
            action=action_type,
        ))
        # Optionally notify admin about lack of permissions (using send_message_safe)
        # await send_message_safe(context, chat.id, await get_language_string(context, 'NOTIFY_ADMIN_NO_PERMS', ...))
        return  # Cannot take action if no perms

    reason_detail = "; ".join(reasons)  # Combine reasons into a single string
    action_successful = False

    try:
        if action_type == "ban":
            # Use ban_chat_member_mb wrapper
            success = await ban_chat_member_mb(bot, chat.id, target_user_id,
                                               revoke_messages=True)  # Use _mb, revoke messages?
            if success:
                action_successful = True
                # Log to bot_restrictions table
                await db_execute(
                    """INSERT OR REPLACE INTO bot_restrictions (user_id, chat_id, restriction_type, applied_at, expires_at, is_active, reason, applied_by_admin_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(user_id, chat_id, restriction_type, is_active) WHERE is_active = 1 DO UPDATE SET
                       applied_at = excluded.applied_at, expires_at = excluded.expires_at, reason = excluded.reason, applied_by_admin_id = excluded.applied_by_admin_id""",
                    (
                        target_user_id,
                        chat.id,
                        "ban",
                        applied_at_iso,
                        None,
                        1,
                        reason_detail[:1000],
                        context.bot.id,
                    ),  # reason limited, applied by bot
                )
                logger.info(f"Bot banned user {target_user_id} in chat {chat.id} due to {reason_detail[:100]}.")

        elif action_type == "kick":
            # Kick is ban then unban
            # Use ban_chat_member_mb and unban_chat_member_mb wrappers
            ban_success = await ban_chat_member_mb(bot, chat.id, target_user_id)  # Use _mb
            if ban_success:
                await asyncio.sleep(0.5)  # Small delay between ban and unban
                unban_success = await unban_chat_member_mb(bot, chat.id, target_user_id, only_if_banned=True)  # Use _mb
                if unban_success:
                    action_successful = True
                    # Kicks are not persistent restrictions logged in bot_restrictions table
                    logger.info(f"Bot kicked user {target_user_id} in chat {chat.id} due to {reason_detail[:100]}.")
                else:
                    logger.warning(
                        f"Bot banned user {target_user_id} in chat {chat.id} but failed to unban after kick attempt.")
            else:
                logger.warning(f"Bot failed to ban user {target_user_id} in chat {chat.id} during kick attempt.")

        elif action_type == "mute":  # Mute
            until_date_target: Optional[datetime] = None
            if duration_seconds > 0:
                until_date_target = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
                expires_at_iso = until_date_target.isoformat()

            # mute_permissions_obj is defined globally now (Part 1)
            # Use restrict_chat_member_mb wrapper
            success = await restrict_chat_member_mb(
                bot,
                chat.id,
                target_user_id,
                mute_permissions_obj,
                until_date=until_date_target,
            )  # Use _mb, use mute_permissions_obj
            if success:
                action_successful = True
                # Log to bot_restrictions table
                await db_execute(
                    """INSERT OR REPLACE INTO bot_restrictions (user_id, chat_id, restriction_type, applied_at, expires_at, is_active, reason, applied_by_admin_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(user_id, chat_id, restriction_type, is_active) WHERE is_active = 1 DO UPDATE SET
                       applied_at = excluded.applied_at, expires_at = excluded.expires_at, reason = excluded.reason, applied_by_admin_id = excluded.applied_by_admin_id""",
                    (
                        target_user_id,
                        chat.id,
                        "mute",
                        applied_at_iso,
                        expires_at_iso,
                        1,
                        reason_detail[:1000],
                        context.bot.id,
                    ),
                )
                logger.info(
                    f"Bot muted user {target_user_id} in chat {chat.id} for {duration_seconds}s due to {reason_detail[:100]}."
                )

        else:
            logger.error(f"Unknown action type '{action_type}' provided to _take_action_on_user.")
            return  # Unknown action type

        # Send punishment message in group if action was taken successfully
        if action_successful:
            # Log bot's own action to observed_admin_actions table
            await log_action_db(
                context,
                action_type.capitalize(),
                target_user_id,
                chat.id,
                reason_detail,
                duration_seconds=duration_seconds if action_type == "mute" else None,
                sender_user_id=context.bot.id,
            )  # Uses log_action_db (Part 2 logic), sender is bot

            # Construct and send the public punishment message
            # Use the language of the chat
            # Need a pattern for action taken on a user (re-use sender pattern or create new?)
            # Let's re-use PUNISHMENT_MESSAGE_SENDER_ENGLISH and format with target user info.
            punishment_msg_display = await get_language_string(
                context,
                "PUNISHMENT_MESSAGE_SENDER_ENGLISH",  # Re-using pattern, format args will make it specific
                chat_id=chat.id,
                user_id=target_user_id,  # Pass chat/user IDs for lang context
                user_mention=target_user_mention,
                action_taken=action_type.capitalize(),
                reason_detail=reason_detail,
                dialogue="",
            )  # No dialogue needed here

            # Add duration to message if temporary mute
            if action_type == "mute" and duration_seconds > 0:
                # Need a pattern like " for {duration}."
                punishment_msg_display += await get_language_string(
                    context,
                    "PUNISHMENT_DURATION_APPEND",
                    chat_id=chat.id,
                    user_id=target_user_id,
                    duration=format_duration(duration_seconds),
                )  # Uses format_duration (Part 12)

            # Include "Unmute Me" button for temporary mutes applied by *this bot instance*
            reply_markup = None
            if action_type == "mute" and duration_seconds > 0:
                # Button directs to PM with bot, including group ID in start payload
                unmute_me_button_text = await get_language_string(
                    context,
                    "UNMUTE_ME_BUTTON_TEXT",
                    chat_id=chat.id,
                    user_id=target_user_id,
                )  # Need pattern like "Unmute Me"
                bot_username = (await get_bot_username(context) or "your_bot")  # Uses get_chat_mb (_mb)
                start_payload = f"unmuteme_{chat.id}"
                button_url = f"https://t.me/{bot_username}?start={start_payload}"
                reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(unmute_me_button_text, url=button_url)]])

            # Send message, replying to the join message if available (using send_message_safe which uses _mb)
            await send_message_safe(
                context,
                chat.id,
                punishment_msg_display,
                parse_mode=ParseMode.HTML,
                reply_to_message_id=trigger_message_id,  # Reply to the join message
                reply_markup=reply_markup,
            )

    except Forbidden:
        logger.error(await get_language_string(
            context,
            "NO_PERMS_TO_ACT_SENDER",
            chat_id=chat.id,
            user_id=target_user_id,
            action=action_type,
        ))  # Use language string with chat/user context
    except BadRequest as e:
        logger.error(await get_language_string(
            context,
            "BADREQUEST_TO_ACT_SENDER",
            chat_id=chat.id,
            user_id=target_user_id,
            action=action_type,
            e=e,
        ))  # Use language string with chat/user context
    except Exception as e:
        logger.error(
            await get_language_string(
                context,
                "ERROR_ACTING_SENDER",
                chat_id=chat.id,
                user_id=target_user_id,
                action=action_type,
                e=e,
            ),
            exc_info=True,
        )  # Use language string with chat/user context
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


    
from database_ops import init_db, close_db_pool, db_execute, db_fetchone, db_fetchall

# Main async function
async def main_async():
    global TOKEN, DATABASE_NAME, MAINTENANCE_MODE
    global DEFAULT_PUNISH_ACTION, DEFAULT_PUNISH_DURATION_PROFILE_SECONDS
    global DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS, DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS
    global BOT_TOKENS, applications, bot_instances_cache
    
    setup_logging()
    await load_config()
    await init_db()

    if not TOKEN:
        logger.critical(await get_language_string(None, "TOKEN_NOT_LOADED_MESSAGE", user_id=0))
        return
    

    

    default_punish_durations = {
        "profile": DEFAULT_PUNISH_DURATION_PROFILE_SECONDS,
        "message": DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS,
        "mention_profile": DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS,
    }

    warnings.filterwarnings("ignore", category=DeprecationWarning, module="asyncio")

    try:
        await init_db(
            DATABASE_NAME,
            DEFAULT_PUNISH_ACTION,
            default_punish_durations,
            settings.get("default_lang", "english"),
        )
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}")
        return

    MAINTENANCE_MODE = await get_feature_state("maintenance_mode_active", default=False)
    logger.info(f"Maintenance mode initially set to: {MAINTENANCE_MODE}")

    applications.clear()
    bot_instances_cache.clear()

    if not BOT_TOKENS:
        logger.critical("No bot tokens configured. Cannot start.")
        await close_db_pool()
        return

    logger.info(f"Configured with {len(BOT_TOKENS)} bot tokens.")

    primary_application = None
    primary_token = BOT_TOKENS[0]

    try:
        logger.info("Building primary application...")
        primary_application = Application.builder().token(primary_token).build()
        applications.append(primary_application)
        bot_instances_cache[primary_token] = primary_application.bot
        await primary_application.bot.initialize()
        logger.info(
            f"Primary application built for token ...{primary_token[-6:]} (Bot ID: {primary_application.bot.id})"
        )

        for token in BOT_TOKENS[1:]:
            try:
                logger.info(f"Building secondary bot for token ...{token[-6:]}")
                secondary_bot = Application.builder().token(token).build().bot
                bot_instances_cache[token] = secondary_bot
                await secondary_bot.initialize()
                logger.info(f"Secondary bot instance built for token ...{token[-6:]} (Bot ID: {secondary_bot.id})")
            except InvalidToken:
                logger.error(f"Invalid token provided for secondary bot ...{token[-6:]}. Skipping.")
                continue
            except Exception as e:
                logger.error(f"Failed to build secondary bot for token ...{token[-6:]}: {e}")
                continue
    except InvalidToken:
        logger.critical(f"Invalid token for primary bot ...{primary_token[-6:]}. Cannot start.")
        await close_db_pool()
        return
    except Exception as e:
        logger.critical(f"Failed to build Primary Application for token ...{primary_token[-6:]}: {e}")
        await close_db_pool()
        return

    if not primary_application:
        logger.critical("Primary application was not built. Cannot start.")
        await close_db_pool()
        return

    application = primary_application
    application.start_time_epoch = time.time()

    logger.info("Adding command handlers...")
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("unmuteme", unmute_me_command))
    application.add_handler(CommandHandler("reload", reload_command, filters=filters.ChatType.GROUPS))
    application.add_handler(CommandHandler("gmute", gmute_command))
    application.add_handler(CommandHandler("gban", gban_command))
    application.add_handler(CommandHandler("ungmute", ungmute_command))
    application.add_handler(CommandHandler("ungban", ungban_command))
    application.add_handler(CommandHandler("bcastself", bcastself_command))
    application.add_handler(CommandHandler("bcastselfuser", bcastselfuser_command))
    application.add_handler(CommandHandler("bcastselfgroup", bcastselfgroup_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("lang", lang_command))
    application.add_handler(CommandHandler("maintenance", maintenance_command))
    application.add_handler(CommandHandler("checkexempt", check_exemption_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("unmuteall", unmuteall_command))
    application.add_handler(CommandHandler("gunmuteall", gunmuteall_command))
    application.add_handler(CommandHandler("unbanall", unbanall_command))
    application.add_handler(CommandHandler("gunbanall", gunbanall_command))
    application.add_handler(CommandHandler("cancel", cancel_command))

    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(CallbackQueryHandler(pm_unmute_callback_handler, pattern=r"^pmunmute_attempt_\d+$"))
    application.add_handler(CallbackQueryHandler(handle_show_pm_help_callback, pattern="^show_pm_help$"))
    application.add_handler(CallbackQueryHandler(handle_show_group_help_callback, pattern="^show_group_help$"))
    application.add_handler(CallbackQueryHandler(handle_unmute_me_button_all, pattern="^unmute_me_all_bot_mutes$"))
    application.add_handler(CallbackQueryHandler(set_language_callback, pattern=f"^{LANG_CALLBACK_PREFIX}.*"))

    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND) & filters.ChatType.GROUPS, handle_message))
    application.add_handler(MessageHandler(filters.CAPTION & (~filters.COMMAND) & filters.ChatType.GROUPS, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.FORWARDED & filters.ChatType.PRIVATE & filters.User(user_id=AUTHORIZED_USERS) & ~filters.COMMAND, handle_forwarded_channel_message))
    application.add_handler(MessageHandler(filters.COMMAND & filters.ChatType.GROUPS, log_other_admin_actions_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_members_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, left_member_handler))
    application.add_handler(MessageHandler(filters.ALL, handle_idle_state), group=99)
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    application.add_handler(MessageHandler(filters.ALL, handle_misc_messages))

    application.add_handler(ChatMemberHandler(my_chat_member_handler, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(ChatMemberHandler(user_chat_member_handler, ChatMemberHandler.CHAT_MEMBER))
    application.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.CHAT_MEMBER))

    application.add_error_handler(error_handler)

    if application.job_queue:
        logger.info("JobQueue initialized on primary application.")
        cache_cleanup_interval_s = CACHE_TTL_SECONDS * 2 if CACHE_TTL_SECONDS > 0 else 3600
        application.job_queue.run_repeating(
            cleanup_caches_job,
            interval=cache_cleanup_interval_s,
            first=10,
            name="cache_cleanup_job",
        )
        logger.info(await get_language_string(None, "CACHE_CLEANUP_JOB_SCHEDULED_MESSAGE", user_id=0, interval=format_duration(cache_cleanup_interval_s)))

        restriction_cleanup_interval_s = 1800
        application.job_queue.run_repeating(
            deactivate_expired_restrictions_job,
            interval=restriction_cleanup_interval_s,
            first=20,
            name="expired_restrictions_job",
        )
        logger.info(f"Expired restrictions cleanup job scheduled every {format_duration(restriction_cleanup_interval_s)}.")

        db_check_interval_s = 86400
        application.job_queue.run_repeating(
            check_db_size_and_dump,
            interval=db_check_interval_s,
            first=300,
            name="db_size_check_job",
        )
        logger.info(f"Database size check job scheduled every {format_duration(db_check_interval_s)}.")

        await load_and_schedule_timed_broadcasts(application)
    else:
        logger.warning(await get_language_string(None, "JOBQUEUE_NOT_AVAILABLE_MESSAGE", user_id=0))

    logger.info(await get_language_string(None, "BOT_AWAKENS_MESSAGE", user_id=0, TG_VER=TG_VER))

    try:
        logger.info("Starting polling...")
        await application.run_polling(allowed_updates=Update.ALL_TYPES, timeout=60, drop_pending_updates=True)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Received shutdown signal (SIGINT), initiating graceful shutdown...")
    except InvalidToken as e:
        logger.critical(f"Invalid token: {e}")
    except NetworkError as e:
        logger.error(f"Network error during polling: {e}")
    except asyncio.CancelledError:
        logger.info("Polling cancelled, initiating graceful shutdown...")
    except Exception as e:
        logger.error(f"Unexpected error during polling: {e}")
    finally:
        logger.info("Shutting down bot gracefully...")
        try:
            if application.running:
                await asyncio.wait_for(application.stop(), timeout=10)
            if application.updater and application.updater.running:
                await asyncio.wait_for(application.updater.stop(), timeout=5)
            await asyncio.wait_for(application.shutdown(), timeout=10)

            for app in applications[:]:
                if app != application:
                    try:
                        if app.running:
                            await asyncio.wait_for(app.stop(), timeout=10)
                        if app.updater and app.updater.running:
                            await asyncio.wait_for(app.updater.stop(), timeout=5)
                        await asyncio.wait_for(app.shutdown(), timeout=10)
                    except Exception as e:
                        logger.error(f"Error shutting down secondary app: {e}")

            try:
                await asyncio.wait_for(close_db_pool(), timeout=5)
            except Exception as e:
                logger.error(f"Error closing database pool: {e}")

            loop = asyncio.get_running_loop()
            tasks = [task for task in asyncio.all_tasks(loop) if task is not asyncio.current_task()]
            for task in tasks:
                task.cancel()
            if tasks:
                try:
                    await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=10)
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"Error cancelling tasks: {e}")

            logger.info(await get_language_string(None, "BOT_RESTS_MESSAGE", user_id=0))
        except asyncio.TimeoutError:
            logger.error("Shutdown timed out, forcing exit...")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        finally:
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                loop.stop()
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()

if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user via SIGINT.")
    except Exception as e:
        logger.error(f"Error running bot: {e}")