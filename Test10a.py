# main.py.  new code not detecting links in bio 
import random
import logging
import asyncio
import os
import functools  # For decorators
from datetime import datetime, timezone, timedelta
import re
import time
import configparser
import aiosqlite
from cachetools import TTLCache
import nest_asyncio # Applied in main
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatPermissions,
    ChatMember,
    User as TGUser,
    Chat as TGChat,
    Message as TGMessage,
    MessageEntity, # For checking command entities
    __version__ as TG_VER,
)
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.error import BadRequest, Forbidden, InvalidToken, RetryAfter, TimedOut, NetworkError
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ChatMemberHandler, filters, ContextTypes, JobQueue
)
from telegram.request import HTTPXRequest
from typing import Dict, Optional, Tuple, List, Any, Union
import telegram
import warnings

# Initialize logger at the top, immediately after imports
# This ensures the logger is available for logging startup messages or errors.
logger = logging.getLogger(__name__)

# --- Global Variables Definition (ensure these are at the top, with initial defaults) ---

# Define global logging variables with default values.
# These will be overwritten by values from config.ini in load_config().
LOG_FILE_PATH = "bards_sentinel.log"
LOG_LEVEL = "INFO" # Default log level before config is loaded

# Add a global variable to store specific logger levels from config
specific_logger_levels: Dict[str, str] = {}

# --- Other Global Configuration Variables (Defaults) ---
CONFIG_FILE_NAME = "config.ini"
TOKEN: Optional[str] = None
DATABASE_NAME = "bards_sentinel_async.db"
DEFAULT_PUNISH_ACTION = "mute"
DEFAULT_PUNISH_DURATION_PROFILE_SECONDS = 0
DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS = 3600 # 1 hour
DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS = 0
# Global temporary cache for message processing debounce
message_processing_debounce_cache = TTLCache(maxsize=1000, ttl=10) # 10 seconds should be enough

AUTHORIZED_USERS: List[int] = []  # Super admins
CACHE_TTL_MINUTES = 30
CACHE_MAXSIZE = 1024
CACHE_TTL_SECONDS = CACHE_TTL_MINUTES * 60
BROADCAST_SLEEP_INTERVAL = 0.2 # Seconds to sleep between broadcast messages
MAX_COMMAND_ARGS_SPACES = 2 # Max spaces allowed for a message to be considered a command

# Global variables for bad actor expiry duration (using duration string)
BAD_ACTOR_EXPIRY_DURATION_STR: str = "30d" # Default string value
BAD_ACTOR_EXPIRY_SECONDS: int = 0 # Will be parsed from string, 0 means permanent

# Global variable for unmute attempt rate limit duration
UNMUTE_RATE_LIMIT_DURATION_STR: str = "3h" # Default string value for unmute rate limit
UNMUTE_RATE_LIMIT_SECONDS: int = 0 # Will be parsed from string, 0 means no limit

# Other global variables that will be initialized later or manage state
db_pool: Optional[aiosqlite.Connection] = None
SHUTTING_DOWN = False # Global flag to prevent DB operations during shutdown
settings: Dict[str, any] = {
    "free_users": set(),
    "channel_id": None,
    "channel_invite_link": None,
    "active_timed_broadcasts": {}, # Stores job names for timed broadcasts
}
bot_username_cache: Optional[str] = None
MAINTENANCE_MODE = False
user_profile_cache: Optional[TTLCache] = None
username_to_id_cache: Optional[TTLCache] = None
notification_debounce_cache = TTLCache(maxsize=1024, ttl=30) # Debounce for punishment notifications
unmute_attempt_cache = TTLCache(maxsize=1024, ttl=60) # Debounce for "Unmute Me" button clicks


# Import patterns and related constants from the new file
# This try...except block runs AFTER initial global variables (like LOG_LEVEL) are defined.
try:
    import patterns
    # Add a required patterns list for explicit checks if needed
    REQUIRED_PATTERNS = [
        'MESSAGE_VIOLATION_REASON', 'SENDER_IS_BAD_ACTOR_REASON',
        'BIO_LINK_DIALOGUES_LIST', 'PUNISHMENT_MESSAGE_SENDER_ENGLISH',
        'PUNISHMENT_MESSAGE_SENDER_HINDI', 'PUNISHMENT_MESSAGE_MENTIONED_USERS',
        'MIN_USERNAME_LENGTH', 'WHITELIST_PATTERNS', 'COMBINED_FORBIDDEN_PATTERN',
        'FORBIDDEN_WORDS', 'MAINTENANCE_MODE_MESSAGE', 'FEATURE_DISABLED_MESSAGE',
        'START_MESSAGE_PRIVATE_BASE', 'START_MESSAGE_ADMIN_CONFIG',
        'START_MESSAGE_CHANNEL_VERIFY_INFO', 'START_MESSAGE_HELP_PROMPT',
        'HELP_BUTTON_TEXT', 'ADD_BOT_TO_GROUP_BUTTON_TEXT',
        'JOIN_VERIFICATION_CHANNEL_BUTTON_TEXT', 'VERIFY_JOIN_BUTTON_TEXT',
        'UNMUTE_ME_BUTTON_TEXT', 'ADMIN_APPROVE_BUTTON_TEXT',
        'PROVE_ADMIN_BUTTON_TEXT', 'PUNISH_ACTION_MUTE_BUTTON',
        'PUNISH_ACTION_KICK_BUTTON', 'PUNISH_ACTION_BAN_BUTTON',
        'PUNISH_BATCH_OPERATIONS_BUTTON', 'PUNISH_BATCH_KICK_MUTED_BUTTON',
        'PUNISH_BATCH_BAN_MUTED_BUTTON', 'BACK_BUTTON_TEXT',
        'DURATION_30M_BUTTON', 'DURATION_1H_BUTTON', 'DURATION_1D_BUTTON',
        'DURATION_PERMANENT_BUTTON', 'DURATION_CUSTOM_BUTTON',
        'COMMAND_GROUP_ONLY_MESSAGE', 'ADMIN_ONLY_COMMAND_MESSAGE',
        'SUPER_ADMIN_ONLY_COMMAND_MESSAGE', 'SET_PUNISH_PROMPT',
        'SET_PUNISH_INVALID_ACTION', 'SET_PUNISH_SUCCESS',
        'SET_DURATION_ALL_PROMPT', 'INVALID_DURATION_FORMAT_MESSAGE',
        'SET_DURATION_ALL_SUCCESS', 'SET_DURATION_PROFILE_PROMPT',
        'SET_DURATION_MESSAGE_PROMPT', 'SET_DURATION_MENTION_PROMPT',
        'SET_DURATION_GENERIC_PROMPT', 'SET_DURATION_PROFILE_SUCCESS',
        'SET_DURATION_MESSAGE_SUCCESS', 'SET_DURATION_MENTION_SUCCESS',
        'SET_DURATION_GENERIC_SUCCESS', 'FREEPUNISH_USAGE_MESSAGE',
        'USER_NOT_FOUND_MESSAGE', 'INVALID_USER_ID_MESSAGE',
        'FREEPUNISH_SUCCESS_MESSAGE', 'UNFREEPUNISH_USAGE_MESSAGE',
        'UNFREEPUNISH_SUCCESS_MESSAGE', 'GFREEPUNISH_USAGE_MESSAGE',
        'GFREEPUNISH_SUCCESS_MESSAGE', 'GUNFREEPUNISH_USAGE_MESSAGE',
        'GUNFREEPUNISH_SUCCESS_MESSAGE', 'GUNFREEPUNISH_NOT_IMMUNE_MESSAGE',
        'CLEAR_CACHE_SUCCESS_MESSAGE', 'CHECKBIO_USAGE_MESSAGE',
        'CHECKBIO_RESULT_HEADER', 'BIO_IS_BLANK_MESSAGE',
        'CHECKBIO_RESULT_PROBLEM_DETAILS', 'CHECKBIO_ERROR_MESSAGE',
        'SET_CHANNEL_PROMPT', 'SET_CHANNEL_CLEARED_MESSAGE',
        'SET_CHANNEL_NOT_A_CHANNEL_ERROR', 'SET_CHANNEL_BOT_NOT_ADMIN_ERROR',
        'SET_CHANNEL_SUCCESS_MESSAGE', 'SET_CHANNEL_INVITE_LINK_APPEND',
        'SET_CHANNEL_NO_INVITE_LINK_APPEND', 'SET_CHANNEL_BADREQUEST_ERROR',
        'SET_CHANNEL_FORBIDDEN_ERROR', 'SET_CHANNEL_UNEXPECTED_ERROR',
        'SET_CHANNEL_FORWARD_NOT_CHANNEL_ERROR', 'STATS_COMMAND_MESSAGE',
        'DISABLE_COMMAND_USAGE_MESSAGE', 'DISABLE_COMMAND_CRITICAL_ERROR',
        'DISABLE_COMMAND_SUCCESS_MESSAGE', 'ENABLE_COMMAND_USAGE_MESSAGE',
        'ENABLE_COMMAND_SUCCESS_MESSAGE', 'MAINTENANCE_COMMAND_USAGE_MESSAGE',
        'MAINTENANCE_COMMAND_SUCCESS_MESSAGE', 'BROADCAST_USAGE_MESSAGE',
        'BROADCAST_NO_MESSAGE_ERROR', 'BROADCAST_STARTED_MESSAGE',
        'BROADCAST_COMPLETE_MESSAGE', 'BCASTALL_USAGE_MESSAGE',
        'BCASTALL_STARTED_MESSAGE', 'BCASTALL_COMPLETE_MESSAGE',
        'BCASTSELF_USAGE_MESSAGE', 'BCASTSELF_MESSAGE_TEMPLATE',
        'BCASTSELF_STARTED_MESSAGE', 'BCASTSELF_COMPLETE_MESSAGE',
        'STOP_BROADCAST_USAGE', 'STOP_BROADCAST_NOT_FOUND', 'STOP_BROADCAST_SUCCESS',
        'UNMUTEALL_USAGE_MESSAGE', 'UNMUTEALL_INVALID_GROUP_ID',
        'UNMUTEALL_STARTED_MESSAGE', 'UNMUTEALL_COMPLETE_MESSAGE',
        'GUNMUTEALL_STARTED_MESSAGE', 'GUNMUTEALL_NO_DATA_MESSAGE',
        'GUNMUTEALL_COMPLETE_MESSAGE', 'ADMIN_ONLY_ACTION_ERROR',
        'VERIFY_NO_CHANNEL_SET_ERROR', 'VERIFY_SUCCESS_MESSAGE',
        'VERIFY_PLEASE_JOIN_CHANNEL_MESSAGE', 'UNMUTE_CANNOT_UNMUTE_OTHERS_ERROR',
        'UNMUTE_ATTEMPT_DEBOUNCE_ERROR', 'UNMUTE_SUBSCRIPTION_REQUIRED_MESSAGE_GROUP',
        'UNMUTE_PROFILE_STILL_HAS_ISSUES_ERROR', 'UNMUTE_CHECK_PM_FOR_ISSUES_MESSAGE_GROUP',
        'UNMUTE_SUCCESS_MESSAGE_GROUP', 'UNMUTE_BOT_NO_PERMISSION_ERROR_GROUP',
        'UNMUTE_BAD_REQUEST_ERROR_GROUP', 'APPROVE_USER_SUCCESS_MESSAGE_GROUP',
        'APPROVE_USER_UNMUTE_FORBIDDEN_ERROR_GROUP', 'APPROVE_USER_UNMUTE_BADREQUEST_ERROR_GROUP',
        'PUNISH_BATCH_MENU_PROMPT', 'PROVE_ADMIN_SUCCESS', 'PROVE_ADMIN_FAILURE',
        'NEW_USER_PROFILE_VIOLATION_REASON', 'ERROR_HANDLER_EXCEPTION',
        'ERROR_HANDLER_INVALID_TOKEN', 'ERROR_HANDLER_FORBIDDEN',
        'ERROR_HANDLER_FORBIDDEN_IN_GROUP_REMOVED', 'CONFIG_NOT_FOUND_MESSAGE',
        'CONFIG_TEMPLATE_CREATED_MESSAGE', 'CONFIG_TOKEN_NOT_SET_MESSAGE',
        'CONFIG_LOAD_SUCCESS_MESSAGE', 'NO_AUTHORIZED_USERS_WARNING',
        'UNKNOWN_TEXT', 'PERMANENT_TEXT', 'NOT_APPLICABLE',
        'ON_TEXT', 'OFF_TEXT', 'ENABLED_TEXT', 'DISABLED_TEXT',
        'DURATION_CUSTOM_PROMPT_CB', 'INVALID_DURATION_FROM_BUTTON_ERROR',
        'MESSAGE_PROCESSING_SKIPPED_MAINTENANCE', 'MESSAGE_PROCESSING_SKIPPED_FEATURE_OFF',
        'USER_EXEMPT_SKIP_MESSAGE', 'ACTION_DEBOUNCED_SENDER', 'NO_PERMS_TO_ACT_SENDER',
        'BADREQUEST_TO_ACT_SENDER', 'ERROR_ACTING_SENDER', 'ACTION_DEBOUNCED_MENTION',
        'NO_PERMS_TO_ACT_MENTION', 'BADREQUEST_TO_ACT_MENTION', 'ERROR_ACTING_MENTION',
        'MENTIONED_USER_PROFILE_VIOLATION_REASON', 'BOT_ADDED_TO_GROUP_WELCOME_MESSAGE',
        'FORBIDDEN_IN_GROUP_MESSAGE_HANDLER', 'ERROR_IN_GROUP_MESSAGE_HANDLER',
        'UNMUTE_VIA_PM_BUTTON_TEXT', 'ADDITIONAL_MENTIONS_MUTED_LOG',
        'VERIFICATION_STATUS_VERIFIED', 'VERIFICATION_STATUS_NOT_VERIFIED_JOIN',
        'VERIFICATION_STATUS_NOT_VERIFIED_CLICK_VERIFY', 'HELP_COMMAND_TEXT_PRIVATE',
        'HELP_COMMAND_TEXT_GROUP', 'START_MESSAGE_GROUP', 'ALL_TYPES_TEXT',
        'CACHE_CLEANUP_JOB_SCHEDULED_MESSAGE', 'JOBQUEUE_NOT_AVAILABLE_MESSAGE',
        'BOT_AWAKENS_MESSAGE', 'BOT_RESTS_MESSAGE', 'TOKEN_NOT_LOADED_MESSAGE'


    ]
    for attr in REQUIRED_PATTERNS:
        if not hasattr(patterns, attr):
            logger.error(f"Missing required attribute in patterns.py: {attr}. Using fallback or dummy.")
            # Define a fallback or raise an error if crucial patterns are missing
            # Add default dummy values for missing patterns to prevent NameError later
            if attr == 'BIO_LINK_DIALOGUES_LIST': setattr(patterns, attr, [{"english": "Content violates rules.", "hindi": ""}])
            elif attr == 'SENDER_IS_BAD_ACTOR_REASON': setattr(patterns, attr, {"english": "Known bad actor."})
            elif attr == 'WHITELIST_PATTERNS': setattr(patterns, attr, [])
            elif attr == 'COMBINED_FORBIDDEN_PATTERN': setattr(patterns, attr, r"a^") # Matches nothing
            elif attr == 'FORBIDDEN_WORDS': setattr(patterns, attr, [])
            else: setattr(patterns, attr, f"Missing Pattern: {attr}") # Define a generic dummy fallback for strings

except ImportError:
    logger.critical("Could not import patterns.py. Make sure it exists in the same directory or set up environment correctly.")
    # Define essential fallback patterns if patterns.py is completely missing
    class FallbackPatterns:
        # Define ALL required patterns here with simple defaults to prevent NameErrors
        MESSAGE_VIOLATION_REASON = "Message contains forbidden content: {message_issue_type}"
        SENDER_IS_BAD_ACTOR_REASON = {"english": "Known bad actor.", "hindi": ""} # Ensure language keys match usage
        BIO_LINK_DIALOGUES_LIST = [{"english": "Content violates rules.", "hindi": ""}]
        PUNISHMENT_MESSAGE_SENDER_ENGLISH = "<b>{user_mention}</b> has been {action_taken} due to {reason_detail}. {dialogue_english}"
        PUNISHMENT_MESSAGE_SENDER_HINDI = "{dialogue_hindi}"
        PUNISHMENT_MESSAGE_MENTIONED_USERS = "Sender {sender_mention} mentioned users with problematic profiles ({muted_users_list}). Those users were muted for {mute_duration}."
        MIN_USERNAME_LENGTH = 5
        WHITELIST_PATTERNS = []
        COMBINED_FORBIDDEN_PATTERN = r"a^" # Pattern that matches nothing
        FORBIDDEN_WORDS = []
        MAINTENANCE_MODE_MESSAGE = "🤖 Bot is currently under maintenance. Please try again later."
        FEATURE_DISABLED_MESSAGE = "❌ Feature '{command_name}' is currently disabled."
        # Add the logging pattern here in the fallback as well
        LOGGING_SETUP_MESSAGE = 'Logging setup complete with level {log_level} to {log_file_path}.'
        # Add other required patterns fallbacks... ensure all in REQUIRED_PATTERNS are here
        START_MESSAGE_PRIVATE_BASE = "👋 Welcome to the Bard's Sentinel Bot!"
        START_MESSAGE_ADMIN_CONFIG = "This bot helps manage group content and member profiles."
        START_MESSAGE_CHANNEL_VERIFY_INFO = "" # Default empty if not used
        START_MESSAGE_HELP_PROMPT = "Type /help to see available commands."
        HELP_BUTTON_TEXT = "❓ Help"
        ADD_BOT_TO_GROUP_BUTTON_TEXT = "➕ Add {bot_username} to a Group"
        JOIN_VERIFICATION_CHANNEL_BUTTON_TEXT = "✅ Join Verification Channel"
        VERIFY_JOIN_BUTTON_TEXT = "🔄 Verify Join"
        UNMUTE_ME_BUTTON_TEXT = "🔓 Unmute Me"
        ADMIN_APPROVE_BUTTON_TEXT = "👍 Admin Approve"
        PROVE_ADMIN_BUTTON_TEXT = "✅ Prove Admin Status"
        PUNISH_ACTION_MUTE_BUTTON = "🔇 Mute"
        PUNISH_ACTION_KICK_BUTTON = "👢 Kick"
        PUNISH_ACTION_BAN_BUTTON = "🔨 Ban"
        PUNISH_BATCH_OPERATIONS_BUTTON = "⚙️ Batch Ops"
        PUNISH_BATCH_KICK_MUTED_BUTTON = "👢 Kick All Muted"
        PUNISH_BATCH_BAN_MUTED_BUTTON = "🔨 Ban All Muted"
        BACK_BUTTON_TEXT = "◀️ Back"
        DURATION_30M_BUTTON = "30m"
        DURATION_1H_BUTTON = "1h"
        DURATION_1D_BUTTON = "1d"
        DURATION_PERMANENT_BUTTON = "Permanent"
        DURATION_CUSTOM_BUTTON = "✏️ Custom"
        COMMAND_GROUP_ONLY_MESSAGE = "This command can only be used in groups."
        ADMIN_ONLY_COMMAND_MESSAGE = "This command can only be used by group administrators."
        SUPER_ADMIN_ONLY_COMMAND_MESSAGE = "👑 This command is for super administrators only."
        SET_PUNISH_PROMPT = "Current punishment action is {current_action}. Choose a new one:"
        SET_PUNISH_INVALID_ACTION = "Invalid action '{action}'. Choose from mute, kick, or ban."
        SET_PUNISH_SUCCESS = "Punishment action set to {action}."
        SET_DURATION_ALL_PROMPT = "Set default punishment duration for all violation types. Current profile duration: {current_profile_duration}."
        INVALID_DURATION_FORMAT_MESSAGE = "Invalid duration format '{duration_str}'. Use formats like 30m, 1h, 1d, 0 (permanent)."
        SET_DURATION_ALL_SUCCESS = "Default punishment duration set to {duration_formatted} for all violation types."
        SET_DURATION_PROFILE_PROMPT = "Set punishment duration for profile violations. Current: {current_duration}."
        SET_DURATION_MESSAGE_PROMPT = "Set punishment duration for message violations. Current: {current_duration}."
        SET_DURATION_MENTION_PROMPT = "Set punishment duration for mentioning users with profile violations. Current: {current_duration}."
        SET_DURATION_GENERIC_PROMPT = "Set punishment duration for {trigger_type}. Current: {current_duration}."
        SET_DURATION_PROFILE_SUCCESS = "Punishment duration for profile violations set to {duration_formatted}."
        SET_DURATION_MESSAGE_SUCCESS = "Punishment duration for message violations set to {duration_formatted}."
        SET_DURATION_MENTION_SUCCESS = "Punishment duration for mentioned user profile violations set to {duration_formatted}."
        SET_DURATION_GENERIC_SUCCESS = "Punishment duration for {trigger_type} set to {duration_formatted}."
        FREEPUNISH_USAGE_MESSAGE = "🔒 Usage: <code>/freepunish [user_id or reply]</code> - Exempt a user from automated punishments in this group."
        USER_NOT_FOUND_MESSAGE = "User '{identifier}' not found or could not be resolved."
        INVALID_USER_ID_MESSAGE = "Invalid user ID. Please provide a numeric ID or a valid @username."
        FREEPUNISH_SUCCESS_MESSAGE = "✅ User {user_id} is now exempted from automated punishments in this group."
        UNFREEPUNISH_USAGE_MESSAGE = "🔓 Usage: <code>/unfreepunish [user_id or reply]</code> - Remove a user's exemption from automated punishments in this group."
        UNFREEPUNISH_SUCCESS_MESSAGE = "✅ User {user_id}'s exemption from automated punishments in this group has been removed."
        GFREEPUNISH_USAGE_MESSAGE = "👑 Usage: <code>/gfreepunish [user_id or @username]</code> - Grant a user global immunity from punishments."
        GFREEPUNISH_SUCCESS_MESSAGE = "👑 ✅ User {user_id} has been granted global immunity from punishments."
        GUNFREEPUNISH_USAGE_MESSAGE = "👑 🔓 Usage: <code>/gunfreepunish [user_id or @username]</code> - Remove a user's global immunity."
        GUNFREEPUNISH_SUCCESS_MESSAGE = "👑 ✅ User {user_id}'s global immunity has been removed."
        GUNFREEPUNISH_NOT_IMMUNE_MESSAGE = "👑 ℹ️ User {user_id} is not currently globally immune."
        CLEAR_CACHE_SUCCESS_MESSAGE = "🧠 Cache cleared. Profile entries: {profile_cache_count}, Username entries: {username_cache_count}."
        CHECKBIO_USAGE_MESSAGE = "🔍 Usage: <code>/checkbio [user_id or reply]</code> - Check a user's Telegram profile fields for forbidden content."
        CHECKBIO_RESULT_HEADER = "🔍 Profile check for {user_id} (@{username}):"
        BIO_IS_BLANK_MESSAGE = "<i>Bio is blank.</i>"
        CHECKBIO_RESULT_PROBLEM_DETAILS = "\n  - Issue in <b>{field}</b> ({issue_type})"
        CHECKBIO_ERROR_MESSAGE = "❌ Error checking bio for user {user_id}: {error}"
        SET_CHANNEL_PROMPT = "➡️ Forward a message from the verification channel, or reply with its ID/username to set it."
        SET_CHANNEL_CLEARED_MESSAGE = "✅ Verification channel requirement cleared."
        SET_CHANNEL_NOT_A_CHANNEL_ERROR = "❌ '{identifier}' is not a valid channel ID/username or could not be accessed. (Type: {type})"
        SET_CHANNEL_BOT_NOT_ADMIN_ERROR = "❌ I need to be an administrator in the channel to check members."
        SET_CHANNEL_SUCCESS_MESSAGE = "✅ Verification channel set to <b>{channel_title}</b> (ID: <code>{channel_id}</code>)."
        SET_CHANNEL_INVITE_LINK_APPEND = "\n🔗 Invite Link: {invite_link}"
        SET_CHANNEL_NO_INVITE_LINK_APPEND = "\n🔗 Could not get invite link."
        SET_CHANNEL_BADREQUEST_ERROR = "❌ Failed to access channel '{identifier}' due to a Telegram error: {error}"
        SET_CHANNEL_FORBIDDEN_ERROR = "❌ Access to channel '{identifier}' is forbidden: {error}"
        SET_CHANNEL_UNEXPECTED_ERROR = "❌ An unexpected error occurred while setting the channel: {error}"
        SET_CHANNEL_FORWARD_NOT_CHANNEL_ERROR = "❌ The forwarded message was not from a channel."
        STATS_COMMAND_MESSAGE = """📊 Bot Stats:
Groups: <code>{groups_count}</code>
Total Users Interacted: <code>{total_users_count}</code>
Users Started PM: <code>{started_users_count}</code>
Bad Actors (Known): <code>{bad_actors_count}</code>
Verification Channel: <code>{verification_channel_id}</code>
Maintenance Mode: <b>{maintenance_mode_status}</b>
Cache Sizes: Profile={profile_cache_size}, Username={username_cache_size}
Uptime: <code>{uptime_formatted}</code>
PTB Version: <code>{ptb_version}</code>"""
        DISABLE_COMMAND_USAGE_MESSAGE = "👑 Usage: <code>/disable [feature_name]</code> - Disable a bot feature."
        DISABLE_COMMAND_CRITICAL_ERROR = "🚫 Cannot disable the critical feature '{feature_name}'."
        DISABLE_COMMAND_SUCCESS_MESSAGE = "✅ Feature '{feature_name}' disabled."
        ENABLE_COMMAND_USAGE_MESSAGE = "👑 Usage: <code>/enable [feature_name]</code> - Enable a bot feature."
        ENABLE_COMMAND_SUCCESS_MESSAGE = "✅ Feature '{feature_name}' enabled."
        MAINTENANCE_COMMAND_USAGE_MESSAGE = "👑 Usage: <code>/maintenance [on|off]</code> - Turn maintenance mode ON or OFF. Current: <b>{current_state}</b>"
        MAINTENANCE_COMMAND_SUCCESS_MESSAGE = "✅ Maintenance mode {state}. The bot {action}."
        BROADCAST_USAGE_MESSAGE = "👑 Usage: <code>/broadcast [interval|target_id] &lt;message&gt;</code> - Send a message to all groups (or a specific one). Interval for repeating (e.g., 1h, 1d)."
        BROADCAST_NO_MESSAGE_ERROR = "❌ Please provide a message to broadcast."
        BROADCAST_STARTED_MESSAGE = "✉️ Broadcast started to all groups... (Format: {format})"
        BROADCAST_COMPLETE_MESSAGE = "✅ Broadcast complete. Sent: {sent_count}, Failed: {failed_count}."
        BCASTALL_USAGE_MESSAGE = "👑 Usage: <code>/bcastall [interval] &lt;message&gt;</code> - Send a message to all groups AND all users who started the bot. Interval for repeating."
        BCASTALL_STARTED_MESSAGE = "✉️ Universal broadcast started to all groups and users..."
        BCASTALL_COMPLETE_MESSAGE = "✅ Universal broadcast complete. Groups Sent: {sent_groups}, Groups Failed: {failed_groups}, Users Sent: {sent_users}, Users Failed: {failed_users}."
        BCASTSELF_USAGE_MESSAGE = "👑 Usage: <code>/bcastself [interval]</code> - Send a self-promotion message to all users who started the bot. Interval for repeating."
        BCASTSELF_MESSAGE_TEMPLATE = "🤖 Hello! Consider adding Bard's Sentinel to your groups to help moderate: t.me/{bot_username}?startgroup=true"
        BCASTSELF_STARTED_MESSAGE = "✉️ Self-promotion broadcast started to all users..."
        BCASTSELF_COMPLETE_MESSAGE = "✅ Self-promotion broadcast complete. Sent: {sent_count}, Failed: {failed_count}."
        STOP_BROADCAST_USAGE = "👑 Usage: <code>/stopbroadcast &lt;job_name&gt;</code> - Stop a timed broadcast job."
        STOP_BROADCAST_NOT_FOUND = "❌ Timed broadcast job '<code>{job_name}</code>' not found."
        STOP_BROADCAST_SUCCESS = "✅ Timed broadcast job '<code>{job_name}</code>' stopped."
        UNMUTEALL_USAGE_MESSAGE = "👑 Usage: <code>/unmuteall &lt;group_id&gt;</code> - Attempt to unmute all known users in a specific group."
        UNMUTEALL_INVALID_GROUP_ID = "❌ Invalid group ID. Please provide a negative group chat ID (e.g., <code>-1001234567890</code>)."
        UNMUTEALL_STARTED_MESSAGE = "🔓 Unmute All started for group <code>{group_id}</code>..."
        UNMUTEALL_COMPLETE_MESSAGE = "✅ Unmute All for group <code>{group_id}</code> complete. Unmuted: {unmuted_count}, Failed: {failed_count} (Including not in group)."
        GUNMUTEALL_STARTED_MESSAGE = "👑 🔓 Global Unmute All started for all known groups..."
        GUNMUTEALL_NO_DATA_MESSAGE = "ℹ️ No group or user data found in the database to perform global unmute all."
        GUNMUTEALL_COMPLETE_MESSAGE = "👑 ✅ Global Unmute All complete across {groups_count} groups ({users_per_group_approx} users checked per group approx). Total successful unmute operations: {total_unmuted_ops}, Total failed attempts: {total_failed_ops}."
        ADMIN_ONLY_ACTION_ERROR = "🚫 This action can only be performed by group administrators."
        VERIFY_NO_CHANNEL_SET_ERROR = "❌ Verification channel is not set."
        VERIFY_SUCCESS_MESSAGE = "✅ You are verified."
        VERIFY_PLEASE_JOIN_CHANNEL_MESSAGE = "⚠️ To get unmuted, please join the verification channel first: {channel_link}"
        UNMUTE_CANNOT_UNMUTE_OTHERS_ERROR = "🚫 You can only use this button to attempt to unmute yourself."
        UNMUTE_ATTEMPT_DEBOUNCE_ERROR = "⏳ Please wait a moment before trying to unmute again."
        UNMUTE_SUBSCRIPTION_REQUIRED_MESSAGE_GROUP = "⚠️ Verification required. Please check your PM with the bot to complete the verification process."
        UNMUTE_PROFILE_STILL_HAS_ISSUES_ERROR = "🚫 Your profile still contains issues ({field}). Please fix them first to be unmuted."
        UNMUTE_CHECK_PM_FOR_ISSUES_MESSAGE_GROUP = "🚫 Profile issues detected. Please check your PM with the bot for details and instructions."
        UNMUTE_SUCCESS_MESSAGE_GROUP = "✅ {user_mention} has been unmuted."
        UNMUTE_BOT_NO_PERMISSION_ERROR_GROUP = "❌ I do not have the necessary permissions ('Restrict Members') to unmute users in this group."
        UNMUTE_BAD_REQUEST_ERROR_GROUP = "❌ An error occurred while trying to unmute. The user may not be in the group or already unmuted."
        APPROVE_USER_SUCCESS_MESSAGE_GROUP = "✅ {approved_user_mention} has been approved and exempted from punishments in this group by {admin_mention}."
        APPROVE_USER_UNMUTE_FORBIDDEN_ERROR_GROUP = "❌ Approved user is exempted, but I do not have permissions to unmute them."
        APPROVE_USER_UNMUTE_BADREQUEST_ERROR_GROUP = "❌ An error occurred during approval/unmuting. The user may not be in the group or already unmuted."
        PUNISH_BATCH_MENU_PROMPT = "Choose a batch operation for muted users:"
        PROVE_ADMIN_SUCCESS = "✅ {user_mention} proved admin status."
        PROVE_ADMIN_FAILURE = "❌ You are not an administrator in this group."
        NEW_USER_PROFILE_VIOLATION_REASON = "New user profile issue ({issue_type} in {field})"
        ERROR_HANDLER_EXCEPTION = "❌ An error occurred: {error}"
        ERROR_HANDLER_INVALID_TOKEN = "❌ Bot token is invalid. Please check your config.ini file. Exiting."
        ERROR_HANDLER_FORBIDDEN = "❌ Forbidden error: {error}"
        ERROR_HANDLER_FORBIDDEN_IN_GROUP_REMOVED = "❌ Forbidden in group {chat_id}. Bot likely removed or blocked. Group data removed from DB."
        UNMUTE_VIA_PM_BUTTON_TEXT = "✍️ Unmute via Bot PM"
        ADDITIONAL_MENTIONS_MUTED_LOG = "ℹ️ In chat {chat_id}, sender {sender_mention} mentioned users with profile issues. The mentioned users were muted: {user_list}"
        # Other necessary fallback patterns as needed
        CONFIG_NOT_FOUND_MESSAGE = "❌ config.ini not found at {config_file_name}. Creating a template config file."
        CONFIG_TEMPLATE_CREATED_MESSAGE = "✅ config.ini template created at {config_file_name}. Please edit it with your bot token and settings."
        CONFIG_TOKEN_NOT_SET_MESSAGE = "❌ Bot Token not set in {config_file_name}. Please edit the config file. Exiting."
        CONFIG_LOAD_SUCCESS_MESSAGE = "✅ Configuration loaded successfully."
        NO_AUTHORIZED_USERS_WARNING = "⚠️ Warning: No authorized users configured in config.ini. Some commands may be limited."
        UNKNOWN_TEXT = "Unknown"
        PERMANENT_TEXT = "Permanent"
        NOT_APPLICABLE = "N/A"
        ON_TEXT = "ON"
        OFF_TEXT = "OFF"
        ENABLED_TEXT = "enabled"
        DISABLED_TEXT = "disabled"
        DURATION_CUSTOM_PROMPT_CB = "Please reply to this message with the desired duration for {scope_type} (e.g., 30m, 1h, 1d, 0 for permanent). Example: <code>/{command_name} 1d</code>"
        INVALID_DURATION_FROM_BUTTON_ERROR = "❌ Invalid duration value provided by button."
        MESSAGE_PROCESSING_SKIPPED_MAINTENANCE = "Message processing skipped due to maintenance mode."
        MESSAGE_PROCESSING_SKIPPED_FEATURE_OFF = "Message processing skipped as feature is disabled."
        USER_EXEMPT_SKIP_MESSAGE = "User {user_id} in chat {chat_id} is exempt (Global: {is_globally_exempt}, Group: {is_group_exempt}). Skipping message checks."
        ACTION_DEBOUNCED_SENDER = "Action for sender {user_id} in chat {chat_id} debounced."
        NO_PERMS_TO_ACT_SENDER = "Bot lacks permissions to {action} sender {user_id} in chat {chat_id}."
        BADREQUEST_TO_ACT_SENDER = "BadRequest attempting to {action} sender {user_id} in chat {chat_id}: {e}"
        ERROR_ACTING_SENDER = "Error attempting to {action} sender {user_id}: {e}"
        ACTION_DEBOUNCED_MENTION = "Action for mentioned user {user_id} in chat {chat_id} debounced."
        NO_PERMS_TO_ACT_MENTION = "Bot lacks permissions to act on mentioned user @{username} ({user_id}) in chat {chat_id}."
        BADREQUEST_TO_ACT_MENTION = "BadRequest attempting to act on mentioned user @{username} ({user_id}) in chat {chat_id}: {e}"
        ERROR_ACTING_MENTION = "Error attempting to act on mentioned user @{username} ({user_id}): {e}"
        BOT_ADDED_TO_GROUP_WELCOME_MESSAGE = "🤖 Hello! Bard's Sentinel ({bot_name}) is now active in this group."
        FORBIDDEN_IN_GROUP_MESSAGE_HANDLER = "Forbidden error in handle_message for group {chat_id}: {e}"
        ERROR_IN_GROUP_MESSAGE_HANDLER = "Error in handle_message for group {chat_id}, user {user_id}: {e}"
        VERIFICATION_STATUS_VERIFIED = "✅ You are verified."
        VERIFICATION_STATUS_NOT_VERIFIED_JOIN = "⚠️ You need to join the verification channel to use all features. Please join: {channel_link}"
        VERIFICATION_STATUS_NOT_VERIFIED_CLICK_VERIFY = "⚠️ You need to verify your channel join status to use all features. Click the button below after joining."
        HELP_COMMAND_TEXT_PRIVATE = """🤖 Bard's Sentinel Help (Private Chat)

This bot helps moderate groups by checking user profiles and messages for forbidden content like external links.

Available commands:
/start - See welcome message and verification status.
/help - Show this help message.

For group admins (use these commands in the group):
/setpunish - Configure punishment action (Mute, Kick, Ban).
/setduration - Set punishment duration for all violation types.
/setdurationprofile - Set duration for profile violations.
/setdurationmessage - Set duration for message violations.
/setdurationmention - Set duration for mentioned user profile violations.
/freepunish [user_id or reply] - Exempt a user from punishment in this group.
/unfreepunish [user_id or reply] - Remove exemption.

Super Admin Commands (use these in any chat):
/gfreepunish [user_id or @username] - Grant global immunity.
/gunfreepunish [user_id or @username] - Remove global immunity.
/clearcache - Clear bot caches.
/checkbio [user_id or reply] - Check a user's profile for issues.
/setchannel [ID/username|clear] - Set or clear the verification channel.
/stats - Show bot statistics.
/disable [feature_name] - Disable a feature.
/enable [feature_name] - Enable a feature.
/maintenance [on|off] - Turn maintenance mode on or off.
/unmuteall [group_id] - Attempt to unmute all known users in a specific group.
/gunmuteall - Attempt to unmute all known users in all known groups.
/broadcast [interval|target_id] &lt;message&gt; - Send a message to all groups or a specific one.
/bcastall [interval] &lt;message&gt; - Send a message to all groups and users who started PM.
/bcastself [interval] - Send a self-promotion message to users who started PM.
/stopbroadcast &lt;job_name&gt; - Stop a timed broadcast job.

Contact admin for help: @your_admin_username (replace with actual username)
"""
        HELP_COMMAND_TEXT_GROUP = """🤖 Bard's Sentinel Help (Group)

This bot helps moderate group content and member profiles.

Commands available in groups:
/start@{bot_username} - See a brief welcome message.
/help@{bot_username} - Show this help message.

For group admins:
/setpunish - Configure punishment action (Mute, Kick, Ban).
/setduration - Set punishment duration for all violation types.
/setdurationprofile - Set duration for profile violations.
/setdurationmessage - Set duration for message violations.
/setdurationmention - Set duration for mentioned user profile violations.
/freepunish [user_id or reply] - Exempt a user from punishment in this group.
/unfreepunish [user_id or reply] - Remove exemption.

Super Admin Commands (can be used here or in private chat):
/gfreepunish, /gunfreepunish, /clearcache, /checkbio, /setchannel, /stats, /disable, /enable, /maintenance, /unmuteall, /gunmuteall, /broadcast, /bcastall, /bcastself, /stopbroadcast.

Add bot to another group: t.me/{bot_username}?startgroup=true

Contact admin for help: @your_admin_username (replace with actual username)
"""
        START_MESSAGE_GROUP = "🤖 Bard's Sentinel ({bot_username}) is active here. Type /help@{bot_username} for commands."
        ALL_TYPES_TEXT = "all types"
        CACHE_CLEANUP_JOB_SCHEDULED_MESSAGE = "🧠 Cache cleanup scheduled every {interval}."
        JOBQUEUE_NOT_AVAILABLE_MESSAGE = "⚠️ JobQueue not available. Scheduled tasks (like cache cleanup) will not run."
        BOT_AWAKENS_MESSAGE = "🤖 Bard's Sentinel awakens! (PTB v{TG_VER})"
        BOT_RESTS_MESSAGE = "🤖 Bard's Sentinel rests. Farewell!"
        TOKEN_NOT_LOADED_MESSAGE = "❌ Bot token not loaded."


    patterns = FallbackPatterns()
    logger.warning("Using fallback patterns as patterns.py could not be imported or is incomplete.")


# --- Define the logging setup message pattern globally ---
# This uses getattr with the patterns object (or fallback) to define the global pattern string.
# This must be defined AFTER the 'patterns' object is created by the try/except block.
LOGGING_SETUP_MESSAGE_PATTERN = getattr(patterns, 'LOGGING_SETUP_MESSAGE', 'Logging setup complete with level {log_level} to {log_file_path}.')
# --- End Definition ---


# --- Function Definitions (ensure these are after global variable definitions) ---

def setup_logging():
    """Sets up the logging configuration based on global LOG_LEVEL and LOG_FILE_PATH."""
    # This function now correctly accesses the global LOG_LEVEL, LOG_FILE_PATH, and LOGGING_SETUP_MESSAGE_PATTERN.
    log_level_enum = getattr(logging, LOG_LEVEL.upper(), logging.INFO) # Default to INFO if level string is invalid

    # Apply the basic configuration
    logging.basicConfig(
        level=log_level_enum,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE_PATH, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    # Now, apply specific logger levels loaded from config
    # This part is moved to main() to ensure it's called AFTER load_config() updates specific_logger_levels

    # Use the global LOGGING_SETUP_MESSAGE_PATTERN defined above
    logger.info(LOGGING_SETUP_MESSAGE_PATTERN.format(log_level=LOG_LEVEL, log_file_path=LOG_FILE_PATH))


def parse_duration(duration_str: str) -> Optional[int]:
    """
    Parses a duration string (e.g., "30m", "1h", "7d", "0") into seconds.
    Returns None if parsing fails or if duration_str is "0" (for permanent).
    """
    if not isinstance(duration_str, str):
        return None
    duration_str = duration_str.strip().lower()

    if duration_str == "0":
        return 0 # 0 seconds indicates permanent

    match = re.fullmatch(r'(\d+)([smhd])', duration_str)
    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    if unit == 's':
        return value
    elif unit == 'm':
        return value * 60
    elif unit == 'h':
        return value * 3600
    elif unit == 'd':
        return value * 86400
    return None

def format_duration(seconds: int) -> str:
    """
    Formats a duration in seconds into a human-readable string (e.g., "1h 30m").
    Returns "Permanent" if seconds is 0.
    """
    if seconds == 0:
        return getattr(patterns, 'PERMANENT_TEXT', 'Permanent')

    parts = []
    days = seconds // 86400
    if days > 0:
        parts.append(f"{days}d")
        seconds %= 86400
    hours = seconds // 3600
    if hours > 0:
        parts.append(f"{hours}h")
        seconds %= 3600
    minutes = seconds // 60
    if minutes > 0:
        parts.append(f"{minutes}m")
        seconds %= 60
    if seconds > 0:
        parts.append(f"{seconds}s")

    if not parts:
        return "0s" # Should not happen for > 0 seconds, but as a fallback
    return " ".join(parts)


def load_config():
    """Loads configuration from config.ini and updates global variables."""
    global TOKEN, DATABASE_NAME, DEFAULT_PUNISH_ACTION
    global DEFAULT_PUNISH_DURATION_PROFILE_SECONDS, DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS, DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS
    global AUTHORIZED_USERS, CACHE_TTL_MINUTES, CACHE_MAXSIZE, CACHE_TTL_SECONDS
    global LOG_FILE_PATH, LOG_LEVEL, BROADCAST_SLEEP_INTERVAL
    global user_profile_cache, username_to_id_cache
    global MAX_COMMAND_ARGS_SPACES
    global specific_logger_levels
    global BAD_ACTOR_EXPIRY_DURATION_STR, BAD_ACTOR_EXPIRY_SECONDS
    global UNMUTE_RATE_LIMIT_DURATION_STR, UNMUTE_RATE_LIMIT_SECONDS

    config = configparser.ConfigParser()
    if not os.path.exists(CONFIG_FILE_NAME):
        # --- Create config template ---
        logger.critical(getattr(patterns, 'CONFIG_NOT_FOUND_MESSAGE', 'config.ini not found at {config_file_name}. Creating template...').format(config_file_name=CONFIG_FILE_NAME))
        config['Bot'] = {
            'Token': 'YOUR_BOT_TOKEN_HERE',
            'DatabaseName': 'bards_sentinel_async.db',
            'DefaultPunishAction': 'mute',
            'DefaultPunishDurationProfileSeconds': str(DEFAULT_PUNISH_DURATION_PROFILE_SECONDS),
            'DefaultPunishDurationMessageSeconds': str(DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS),
            'DefaultPunishDurationMentionProfileSeconds': str(DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS),
            'MinUsernameLength': str(getattr(patterns, 'MIN_USERNAME_LENGTH', 5)),
            'BadActorExpiryDuration': BAD_ACTOR_EXPIRY_DURATION_STR, # Use the default string value
            'LogFilePath': LOG_FILE_PATH,
            'LogLevel': LOG_LEVEL,
            'BroadcastSleepInterval': str(BROADCAST_SLEEP_INTERVAL),
            'MaxCommandArgsSpaces': str(MAX_COMMAND_ARGS_SPACES),
            'UnmuteRateLimitDuration': UNMUTE_RATE_LIMIT_DURATION_STR # <-- ADDED
        }
        config['Admin'] = {'AuthorizedUsers': ''}
        config['Cache'] = {'TTLMinutes': str(CACHE_TTL_MINUTES), 'MaxSize': str(CACHE_MAXSIZE)}
        config['Channel'] = {'ChannelId': '', 'ChannelInviteLink': ''}
        config['Logging.Levels'] = {
            'httpx': 'WARNING',
        }
        with open(CONFIG_FILE_NAME, 'w') as configfile: config.write(configfile)
        logger.info(getattr(patterns, 'CONFIG_TEMPLATE_CREATED_MESSAGE', 'config.ini template created at {config_file_name}. Please edit it.').format(config_file_name=CONFIG_FILE_NAME))
        os._exit(1)

    # --- Read config file ---
    config.read(CONFIG_FILE_NAME)
    try:
        TOKEN = config.get('Bot', 'Token')
        if TOKEN == 'YOUR_BOT_TOKEN_HERE' or not TOKEN:
            logger.critical(getattr(patterns, 'CONFIG_TOKEN_NOT_SET_MESSAGE', 'Bot Token not set in {config_file_name}. Exiting.').format(config_file_name=CONFIG_FILE_NAME)); os._exit(1)

        DATABASE_NAME = config.get('Bot', 'DatabaseName', fallback=DATABASE_NAME)
        DEFAULT_PUNISH_ACTION = config.get('Bot', 'DefaultPunishAction', fallback=DEFAULT_PUNISH_ACTION).lower()
        if DEFAULT_PUNISH_ACTION not in ["mute", "kick", "ban"]:
             logger.warning(f"Invalid DefaultPunishAction '{DEFAULT_PUNISH_ACTION}' in config. Falling back to 'mute'.")
             DEFAULT_PUNISH_ACTION = "mute"

        DEFAULT_PUNISH_DURATION_PROFILE_SECONDS = config.getint('Bot', 'DefaultPunishDurationProfileSeconds', fallback=DEFAULT_PUNISH_DURATION_PROFILE_SECONDS)
        DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS = config.getint('Bot', 'DefaultPunishDurationMessageSeconds', fallback=DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS)
        DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS = config.getint('Bot', 'DefaultPunishDurationMentionProfileSeconds', fallback=DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS)
        BROADCAST_SLEEP_INTERVAL = config.getfloat('Bot', 'BroadcastSleepInterval', fallback=BROADCAST_SLEEP_INTERVAL)

        # Read expiry as duration string and parse
        BAD_ACTOR_EXPIRY_DURATION_STR = config.get('Bot', 'BadActorExpiryDuration', fallback=BAD_ACTOR_EXPIRY_DURATION_STR)
        parsed_seconds = parse_duration(BAD_ACTOR_EXPIRY_DURATION_STR)
        if parsed_seconds is None:
            logger.warning(f"Invalid BadActorExpiryDuration format '{BAD_ACTOR_EXPIRY_DURATION_STR}' in config. Falling back to permanent (0 seconds).")
            BAD_ACTOR_EXPIRY_SECONDS = 0
        else:
            BAD_ACTOR_EXPIRY_SECONDS = parsed_seconds
        logger.info(f"Bad Actor expiry set to {format_duration(BAD_ACTOR_EXPIRY_SECONDS)} ({BAD_ACTOR_EXPIRY_SECONDS} seconds).")

        patterns.MIN_USERNAME_LENGTH = config.getint('Bot', 'MinUsernameLength', fallback=getattr(patterns, 'MIN_USERNAME_LENGTH', 5))
        MAX_COMMAND_ARGS_SPACES = config.getint('Bot', 'MaxCommandArgsSpaces', fallback=MAX_COMMAND_ARGS_SPACES)

        # Load and parse Unmute Rate Limit Duration
        UNMUTE_RATE_LIMIT_DURATION_STR = config.get('Bot', 'UnmuteRateLimitDuration', fallback=UNMUTE_RATE_LIMIT_DURATION_STR)
        parsed_unmute_seconds = parse_duration(UNMUTE_RATE_LIMIT_DURATION_STR)
        if parsed_unmute_seconds is None:
            logger.warning(f"Invalid UnmuteRateLimitDuration format '{UNMUTE_RATE_LIMIT_DURATION_STR}' in config. Falling back to no limit (0 seconds).")
            UNMUTE_RATE_LIMIT_SECONDS = 0
        else:
            UNMUTE_RATE_LIMIT_SECONDS = parsed_unmute_seconds
        logger.info(f"Unmute attempt rate limit set to {format_duration(UNMUTE_RATE_LIMIT_SECONDS)} ({UNMUTE_RATE_LIMIT_SECONDS} seconds).")


        LOG_FILE_PATH = config.get('Bot', 'LogFilePath', fallback=LOG_FILE_PATH)
        LOG_LEVEL = config.get('Bot', 'LogLevel', fallback=LOG_LEVEL).upper()

        auth_users_str = config.get('Admin', 'AuthorizedUsers', fallback='')
        AUTHORIZED_USERS = [int(uid.strip()) for uid in auth_users_str.split(',') if uid.strip().isdigit()]
        fallback_admin = os.getenv("BOT_SUPER_ADMIN_ID")
        if fallback_admin and fallback_admin.isdigit() and int(fallback_admin) not in AUTHORIZED_USERS:
            AUTHORIZED_USERS.append(int(fallback_admin))
            logger.info(f"Loaded fallback super admin ID {fallback_admin} from environment variable.")


        CACHE_TTL_MINUTES = config.getint('Cache', 'TTLMinutes', fallback=CACHE_TTL_MINUTES)
        CACHE_MAXSIZE = config.getint('Cache', 'MaxSize', fallback=CACHE_MAXSIZE)
        CACHE_TTL_SECONDS = CACHE_TTL_MINUTES * 60

        settings["channel_id"] = config.get('Channel', 'ChannelId', fallback=None)
        if settings["channel_id"] and isinstance(settings["channel_id"], str) and settings["channel_id"].strip().lstrip('-').isdigit():
             settings["channel_id"] = int(settings["channel_id"])
        else: settings["channel_id"] = None

        settings["channel_invite_link"] = config.get('Channel', 'ChannelInviteLink', fallback=None)
        if settings["channel_invite_link"] and settings["channel_invite_link"].strip() == '': settings["channel_invite_link"] = None

        specific_logger_levels.clear()
        if 'Logging.Levels' in config:
            for logger_name, level_str in config['Logging.Levels'].items():
                specific_logger_levels[logger_name.strip()] = level_str.strip().upper()

        user_profile_cache = TTLCache(maxsize=CACHE_MAXSIZE, ttl=CACHE_TTL_SECONDS)
        username_to_id_cache = TTLCache(maxsize=CACHE_MAXSIZE, ttl=CACHE_TTL_SECONDS)

        logger.info(getattr(patterns, 'CONFIG_LOAD_SUCCESS_MESSAGE', 'Configuration loaded successfully.'))
        if not AUTHORIZED_USERS:
            logger.warning(getattr(patterns, 'NO_AUTHORIZED_USERS_WARNING', 'No authorized users configured. Bot commands may be limited.'))
    except Exception as e:
        logger.critical(getattr(patterns, 'CONFIG_LOAD_ERROR_MESSAGE', 'Error loading or parsing config.ini: {e}').format(config_file_name=CONFIG_FILE_NAME, e=e), exc_info=True); os._exit(1)



async def init_db(db_path: str) -> None:
    global db_pool, MAINTENANCE_MODE
    try:
        if not db_path or not db_path.endswith('.db'):
            logger.error(f"Invalid database path: {db_path}. Must be a valid .db file.")
            raise ValueError("Database path must be a non-empty string ending with .db")

        if db_pool is not None:
            logger.warning("Database pool already initialized. Skipping reinitialization.")
            return

        db_dir = os.path.dirname(db_path) or "."
        if not os.access(db_dir, os.W_OK):
            logger.error(f"Cannot write to directory: {db_dir}")
            raise PermissionError(f"Write permission denied for {db_dir}")
        if os.path.exists(db_path) and not os.access(db_path, os.W_OK):
            logger.error(f"Cannot write to database file: {db_path}")
            raise PermissionError(f"Write permission denied for {db_path}")

        async def connect_db() -> aiosqlite.Connection:
            retries = 3
            for attempt in range(1, retries + 1):
                try:
                    conn = await aiosqlite.connect(
                        db_path,
                        timeout=60.0,
                        check_same_thread=False
                    )
                    conn.row_factory = aiosqlite.Row
                    logger.info(f"Database connection established at {db_path}")
                    return conn
                except aiosqlite.OperationalError as e:
                    if "database is locked" in str(e) and attempt < retries:
                        logger.warning(f"Database locked, retrying {attempt}/{retries} after {1.0 * attempt}s...")
                        await asyncio.sleep(1.0 * attempt)
                        continue
                    logger.error(f"Failed to connect to database at {db_path}: {e}", exc_info=True)
                    raise
                except Exception as e:
                    logger.error(f"Unexpected error connecting to database at {db_path}: {e}", exc_info=True)
                    raise

        db_pool = await connect_db()

        # is_connection_open now takes `conn` as an argument
        async def is_connection_open(conn: aiosqlite.Connection) -> bool:
            try:
                cursor = await conn.cursor()
                await cursor.execute("SELECT 1")
                await cursor.close()
                return True
            except (aiosqlite.ProgrammingError, ValueError, AttributeError):
                return False

        # execute_schema now takes `conn` (the db_pool) as an argument
        async def execute_schema(conn: aiosqlite.Connection, cursor: aiosqlite.Cursor, query: str, params: tuple = ()) -> None:
            # It's generally better not to try to re-establish the connection *within* execute_schema
            # if it's already failed. The caller (init_db) should handle connection robustness.
            # If the connection fails here, it implies a deeper issue or improper pool management.
            if not await is_connection_open(conn):
                logger.error("Database connection closed or invalid before executing schema. This indicates a critical issue.")
                raise ConnectionError("Database connection is not open or valid.")

            try:
                logger.debug(f"Executing query: {query[:100].replace(chr(10), ' ')}...") # Log first 100 chars, remove newlines
                await cursor.execute(query, params)
                await conn.commit() # Commit on the passed connection
                logger.debug(f"Query executed successfully.")
            except aiosqlite.OperationalError as e:
                logger.error(f"Schema execution failed: {e}. Query: {query}", exc_info=True)
                raise
            except (aiosqlite.ProgrammingError, ValueError) as e:
                logger.error(f"Connection error or programming error in schema execution: {e}. Query: {query}", exc_info=True)
                raise
            except Exception as e:
                logger.error(f"Unexpected error in schema execution: {e}. Query: {query}", exc_info=True)
                raise

        cursor = await db_pool.cursor()
        try:
            # Username lowercase migration (run first)
            try:
                await cursor.execute("SELECT user_id, username FROM users WHERE username IS NOT NULL")
                rows = await cursor.fetchall()
                for row in rows:
                    if row['username'] and row['username'] != row['username'].lower():
                        # Use direct parameter binding for the UPDATE statement
                        await execute_schema(
                            db_pool,
                            cursor,
                            "UPDATE users SET username = ? WHERE user_id = ?",
                            (row['username'].lower(), row['user_id'])
                        )
                        logger.debug(f"Converted username for user_id {row['user_id']} to lowercase.")
            except aiosqlite.OperationalError as e:
                # This can happen if the 'users' table doesn't exist yet, which is fine
                logger.warning(f"Failed to migrate usernames to lowercase (likely table not created yet): {e}")

            # Create database tables
            schema_definitions = [
                (
                    f"""
                    CREATE TABLE IF NOT EXISTS groups (
                        group_id INTEGER PRIMARY KEY,
                        group_name TEXT NOT NULL,
                        added_at TEXT NOT NULL,
                        punish_action TEXT NOT NULL DEFAULT '{DEFAULT_PUNISH_ACTION}',
                        punish_duration_profile INTEGER NOT NULL DEFAULT {DEFAULT_PUNISH_DURATION_PROFILE_SECONDS},
                        punish_duration_message INTEGER NOT NULL DEFAULT {DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS},
                        punish_duration_mention_profile INTEGER NOT NULL DEFAULT {DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS}
                    )
                    """,
                    () # No params needed for CREATE TABLE with embedded defaults
                ),
                (
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        interacted_at TEXT NOT NULL,
                        has_started_bot INTEGER NOT NULL DEFAULT 0 CHECK (has_started_bot IN (0, 1))
                    )
                    """,
                    ()
                ),
                (
                    """
                    CREATE TABLE IF NOT EXISTS group_user_exemptions (
                        group_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        PRIMARY KEY (group_id, user_id),
                        FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE,
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                    )
                    """,
                    ()
                ),
                (
                    """
                    CREATE TABLE IF NOT EXISTS feature_control (
                        feature_name TEXT PRIMARY KEY,
                        is_enabled INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1))
                    )
                    """,
                    ()
                ),
                (
                    """
                    CREATE TABLE IF NOT EXISTS bad_actors (
                        user_id INTEGER PRIMARY KEY,
                        reason TEXT NOT NULL,
                        added_at TEXT NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                    )
                    """,
                    ()
                ),
                (
                    """
                    CREATE TABLE IF NOT EXISTS timed_broadcasts (
                        job_name TEXT PRIMARY KEY,
                        target_type TEXT NOT NULL,
                        message_text TEXT NOT NULL,
                        interval_seconds INTEGER NOT NULL CHECK (interval_seconds > 0),
                        created_at TEXT NOT NULL,
                        next_run_time REAL NOT NULL,
                        markup_json TEXT
                    )
                    """,
                    ()
                ),
                (
                    """
                    CREATE TABLE IF NOT EXISTS unmute_attempts (
                        user_id INTEGER NOT NULL,
                        chat_id INTEGER NOT NULL,
                        attempt_timestamp REAL NOT NULL,
                        PRIMARY KEY (user_id, chat_id),
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                    )
                    """,
                    ()
                ),
                (
                    """
                    CREATE TABLE IF NOT EXISTS action_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        action TEXT NOT NULL,
                        user_id INTEGER NOT NULL,
                        chat_id INTEGER,
                        reason TEXT,
                        timestamp TEXT NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                    )
                    """,
                    ()
                )
            ]

            for query, params in schema_definitions:
                await execute_schema(db_pool, cursor, query, params) # Pass db_pool here

            # Create indexes
            index_queries = [
                "CREATE INDEX IF NOT EXISTS idx_users_username ON users (username)",
                "CREATE INDEX IF NOT EXISTS idx_group_user_exemptions_user_id ON group_user_exemptions (user_id)",
                "CREATE INDEX IF NOT EXISTS idx_bad_actors_added_at ON bad_actors (added_at)",
                "CREATE INDEX IF NOT EXISTS idx_unmute_attempts_timestamp ON unmute_attempts (attempt_timestamp)",
                "CREATE INDEX IF NOT EXISTS idx_action_log_timestamp ON action_log (timestamp)",
                "CREATE INDEX IF NOT EXISTS idx_action_log_user_id ON action_log (user_id)"
            ]

            for query in index_queries:
                await execute_schema(db_pool, cursor, query) # No params for simple CREATE INDEX

            # Helper function to check column existence
            async def column_exists(conn: aiosqlite.Connection, cursor: aiosqlite.Cursor, table_name: str, column_name: str) -> bool:
                try:
                    await cursor.execute(f"PRAGMA table_info({table_name})")
                    columns = await cursor.fetchall()
                    return any(col['name'] == column_name for col in columns)
                except (aiosqlite.ProgrammingError, ValueError) as e:
                    logger.error(f"Error checking column existence for {table_name}.{column_name}: {e}", exc_info=True)
                    raise

            # Helper function to add column
            async def add_column_if_not_exists(conn: aiosqlite.Connection, cursor: aiosqlite.Cursor, table_name: str, column_name: str, column_def: str) -> None:
                if not await column_exists(conn, cursor, table_name, column_name): # Pass conn, cursor
                    # Direct string formatting is acceptable for ALTER TABLE ADD COLUMN as column_def is controlled
                    await execute_schema(conn, cursor, f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}") # Pass conn, cursor
                    logger.info(f"Added column '{column_name}' to '{table_name}'.")

            # Schema migrations
            migrations = [
                ("users", "last_name", "TEXT"),
                ("users", "has_started_bot", "INTEGER NOT NULL DEFAULT 0 CHECK (has_started_bot IN (0, 1))"),
                ("groups", "punish_duration_profile", f"INTEGER NOT NULL DEFAULT {DEFAULT_PUNISH_DURATION_PROFILE_SECONDS}"),
                ("groups", "punish_duration_message", f"INTEGER NOT NULL DEFAULT {DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS}"),
                ("groups", "punish_duration_mention_profile", f"INTEGER NOT NULL DEFAULT {DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS}"),
                ("timed_broadcasts", "markup_json", "TEXT")
            ]

            for table_name, column_name, column_def in migrations:
                await add_column_if_not_exists(db_pool, cursor, table_name, column_name, column_def) # Pass db_pool, cursor

            # Migrate old punish_duration column
            if await column_exists(db_pool, cursor, "groups", "punish_duration") and await column_exists(db_pool, cursor, "groups", "punish_duration_message"): # Pass db_pool, cursor
                try:
                    await execute_schema(db_pool, cursor, """
                        UPDATE groups
                        SET punish_duration_message = punish_duration
                        WHERE punish_duration_message IS NULL AND punish_duration IS NOT NULL
                    """)
                    # Recreate groups_temp table with embedded defaults, similar to initial creation
                    await execute_schema(db_pool, cursor, f"""
                        CREATE TABLE groups_temp (
                            group_id INTEGER PRIMARY KEY,
                            group_name TEXT NOT NULL,
                            added_at TEXT NOT NULL,
                            punish_action TEXT NOT NULL DEFAULT '{DEFAULT_PUNISH_ACTION}',
                            punish_duration_profile INTEGER NOT NULL DEFAULT {DEFAULT_PUNISH_DURATION_PROFILE_SECONDS},
                            punish_duration_message INTEGER NOT NULL DEFAULT {DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS},
                            punish_duration_mention_profile INTEGER NOT NULL DEFAULT {DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS}
                        )
                    """)
                    await execute_schema(db_pool, cursor, """
                        INSERT INTO groups_temp (
                            group_id, group_name, added_at, punish_action,
                            punish_duration_profile, punish_duration_message, punish_duration_mention_profile
                        )
                        SELECT
                            group_id, group_name, added_at, punish_action,
                            punish_duration_profile, punish_duration_message, punish_duration_mention_profile
                        FROM groups
                    """)
                    await execute_schema(db_pool, cursor, "DROP TABLE groups")
                    await execute_schema(db_pool, cursor, "ALTER TABLE groups_temp RENAME TO groups")
                    logger.info("Migrated 'groups' table, removed 'punish_duration' column.")
                except aiosqlite.OperationalError as e:
                    logger.warning(f"Failed to migrate 'punish_duration' column: {e}. Manual intervention might be required if this is a persistent issue.")

            await db_pool.commit()
            logger.info("Database schema initialized and migrations completed.")

            # Assume get_feature_state is defined globally or imported elsewhere.
            # If not, you might need to ensure it's accessible here.
            MAINTENANCE_MODE = await get_feature_state("maintenance_mode_active", default=False)
            logger.debug(f"Maintenance mode: {MAINTENANCE_MODE}")

        finally:
            if cursor:
                await cursor.close()

    except Exception as e:
        logger.error(f"Failed to initialize database at {db_path}: {e}", exc_info=True)
        if db_pool is not None:
            try:
                await db_pool.close()
                logger.info("Closed database connection due to initialization failure.")
                db_pool = None
            except Exception as close_e:
                logger.error(f"Error closing database connection: {close_e}", exc_info=True)
        raise

        
import asyncio
from aiosqlite import OperationalError

async def db_execute(sql: str, params: Tuple = ()) -> None:
    """Execute an SQL statement with parameters.

    Args:
        sql: The SQL query to execute.
        params: Tuple of parameters for the SQL query.

    Raises:
        ConnectionError: If the database pool is not initialized.
        aiosqlite.OperationalError: For database operational errors (e.g., locked database).
        aiosqlite.ProgrammingError: For SQL syntax or parameter errors.
        Exception: For other unexpected errors.
    """
    global db_pool, SHUTTING_DOWN

    # Check shutdown state
    if SHUTTING_DOWN:
        logger.warning("Skipping db_execute due to shutdown in progress.")
        return

    # Validate database pool
    if db_pool is None:
        logger.error("Database pool not initialized for db_execute.")
        raise ConnectionError("Database pool not initialized")

    retries = 3
    last_error: Optional[Exception] = None

    for attempt in range(1, retries + 1):
        try:
            async with db_pool.cursor() as cursor:
                # Enable foreign key enforcement
                await cursor.execute("PRAGMA foreign_keys = ON")
                await cursor.execute(sql, params)
                await db_pool.commit()
                logger.debug(f"Successfully executed SQL: {sql[:50]}... with params: {params}")
                return
        except aiosqlite.OperationalError as e:
            last_error = e
            if "database is locked" in str(e).lower() and attempt < retries:
                logger.debug(f"Database locked, retrying {attempt}/{retries} after {0.2 * attempt}s...")
                await asyncio.sleep(0.2 * attempt)  # Linear backoff
                continue
            logger.error(
                f"Operational error after {retries} retries: {e} for SQL: {sql[:100]}... with params: {params}",
                exc_info=True
            )
            raise
        except aiosqlite.ProgrammingError as e:
            logger.error(
                f"Programming error: {e} for SQL: {sql[:100]}... with params: {params}",
                exc_info=True
            )
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error: {e} for SQL: {sql[:100]}... with params: {params}",
                exc_info=True
            )
            raise

    # If retries are exhausted (shouldn't reach here due to raise in loop)
    if last_error:
        logger.error(
            f"Failed to execute SQL after {retries} retries: {last_error} for SQL: {sql[:100]}... with params: {params}"
        )
        raise last_error

async def db_fetchone(sql: str, params: Tuple = ()) -> Optional[Dict[str, any]]:
    """Fetch one row from the database as a dictionary."""
    global db_pool, SHUTTING_DOWN
    if SHUTTING_DOWN:
        logger.warning("Skipping db_fetchone during shutdown.")
        return None
    if db_pool is None:
        logger.error("DB pool not initialized for db_fetchone")
        raise ConnectionError("Database pool not initialized")

    retries = 3
    for attempt in range(retries):
        try:
            async with db_pool.cursor() as cursor:
                await cursor.execute("PRAGMA foreign_keys = ON")
                await cursor.execute(sql, params)
                row = await cursor.fetchone()
                return dict(row) if row else None
        except OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB operational error fetching one: {e} for SQL: {sql} with params: {params}", exc_info=True)
            raise
        except aiosqlite.ProgrammingError as e:
            logger.error(f"DB programming error fetching one: {e} for SQL: {sql} with params: {params}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB fetchone error: {e} for SQL: {sql} with params: {params}", exc_info=True)
            raise
            
async def db_fetchall(sql: str, params: Tuple = ()) -> List[Dict[str, any]]:
    """Fetch all rows from the database as a list of dictionaries."""
    global db_pool, SHUTTING_DOWN
    if SHUTTING_DOWN:
        logger.warning("Skipping db_fetchall during shutdown.")
        return []
    if db_pool is None:
        logger.error("DB pool not initialized for db_fetchall")
        raise ConnectionError("Database pool not initialized")

    retries = 3
    for attempt in range(retries):
        try:
            async with db_pool.cursor() as cursor:
                await cursor.execute("PRAGMA foreign_keys = ON")
                await cursor.execute(sql, params)
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB operational error fetching all: {e} for SQL: {sql} with params: {params}", exc_info=True)
            raise
        except aiosqlite.ProgrammingError as e:
            logger.error(f"DB programming error fetching all: {e} for SQL: {sql} with params: {params}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB fetchall error: {e} for SQL: {sql} with params: {params}", exc_info=True)
            raise

async def add_group(group_id: int, group_name: str, added_at: Optional[str] = None) -> None:
    """Add or update a group in the database."""
    added_at_iso = added_at or datetime.now(timezone.utc).isoformat()
    retries = 3
    for attempt in range(retries):
        try:
            await db_execute(
                """INSERT INTO groups (
                    group_id, group_name, added_at, punish_action,
                    punish_duration_profile, punish_duration_message, punish_duration_mention_profile
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(group_id) DO UPDATE SET
                    group_name = excluded.group_name,
                    added_at = COALESCE(groups.added_at, excluded.added_at)""",
                (
                    group_id, group_name, added_at_iso, DEFAULT_PUNISH_ACTION,
                    DEFAULT_PUNISH_DURATION_PROFILE_SECONDS, DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS,
                    DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS
                )
            )
            logger.debug(f"Group {group_id} added/updated in database.")
            return
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error adding/updating group {group_id}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error adding/updating group {group_id}: {e}", exc_info=True)
            raise
            
async def remove_group_from_db(group_id: int) -> None:
    """Remove a group and its exemptions from the database."""
    retries = 3
    for attempt in range(retries):
        try:
            async with db_pool.cursor() as cursor:
                await cursor.execute("DELETE FROM group_user_exemptions WHERE group_id = ?", (group_id,))
                exemptions_deleted = cursor.rowcount
                await cursor.execute("DELETE FROM groups WHERE group_id = ?", (group_id,))
                groups_deleted = cursor.rowcount
                await db_pool.commit()
            logger.info(f"Group {group_id} removed (deleted {groups_deleted} group(s), {exemptions_deleted} exemption(s)).")
            return
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error removing group {group_id}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error removing group {group_id}: {e}", exc_info=True)
            raise
            
async def close_db_pool() -> None:
    """Close the SQLite database connection pool."""
    global db_pool
    if db_pool is None:
        logger.debug("No database pool to close.")
        return

    try:
        await db_pool.close()
        logger.info("Database connection pool closed successfully.")
        db_pool = None  # Reset to prevent reuse
    except Exception as e:
        logger.error(f"Error closing database pool: {e}", exc_info=True)
        raise    
        
async def add_user(
    user_id: int,
    username: str = "",
    first_name: str = "",
    last_name: str = "",
    has_started_bot: bool = False
) -> None:
    """Add or update a user in the database, supporting username resolution."""
    if user_id <= 0:
        logger.warning(f"Invalid user_id {user_id} provided to add_user.")
        return

    retries = 3
    for attempt in range(retries):
        try:
            # Clean username: strip @, normalize case, convert empty/None to None
            username_cleaned = username.lstrip('@').lower() if username and username.strip() else None
            first_name_cleaned = first_name if first_name and first_name.strip() else None
            last_name_cleaned = last_name if last_name and last_name.strip() else None

            existing_user = await db_fetchone(
                "SELECT has_started_bot, username, first_name, last_name FROM users WHERE user_id = ?",
                (user_id,)
            )
            current_has_started = has_started_bot
            current_time = datetime.now(timezone.utc).isoformat()

            if existing_user:
                if existing_user.get("has_started_bot", 0) == 1:
                    current_has_started = True
                final_username = username_cleaned if username_cleaned else existing_user.get("username")
                final_first_name = first_name_cleaned if first_name_cleaned else existing_user.get("first_name")
                final_last_name = last_name_cleaned if last_name_cleaned else existing_user.get("last_name")

                update_needed = (
                    existing_user.get("has_started_bot", 0) != int(current_has_started) or
                    existing_user.get("username") != final_username or
                    existing_user.get("first_name") != final_first_name or
                    existing_user.get("last_name") != final_last_name
                )

                if update_needed:
                    await db_execute(
                        """UPDATE users SET has_started_bot = ?, username = ?, first_name = ?, last_name = ?, interacted_at = ?
                           WHERE user_id = ?""",
                        (
                            int(current_has_started), final_username, final_first_name,
                            final_last_name, current_time, user_id
                        )
                    )
                    logger.debug(f"Updated user {user_id} in database.")
            else:
                await db_execute(
                    """INSERT INTO users (user_id, username, first_name, last_name, interacted_at, has_started_bot)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        user_id, username_cleaned, first_name_cleaned,
                        last_name_cleaned, current_time, int(has_started_bot)
                    )
                )
                logger.debug(f"Inserted user {user_id} into database.")
            return
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error adding/updating user {user_id}: {e}", exc_info=True)
            raise
        except aiosqlite.IntegrityError as e:
            logger.debug(f"DB integrity error adding/updating user {user_id}: {e}")
            return
        except Exception as e:
            logger.error(f"DB error adding/updating user {user_id}: {e}", exc_info=True)
            raise
            
async def mark_user_started_bot(user_id: int) -> None:
    """Mark a user as having started the bot."""
    if user_id <= 0:
        logger.warning(f"Invalid user_id {user_id} provided to mark_user_started_bot.")
        return

    retries = 3
    for attempt in range(retries):
        try:
            existing = await db_fetchone(
                "SELECT has_started_bot FROM users WHERE user_id = ?",
                (user_id,)
            )
            if existing and existing.get("has_started_bot", 0) == 1:
                logger.debug(f"User {user_id} already marked as started; skipping update.")
                return

            await db_execute(
                "UPDATE users SET has_started_bot = 1, interacted_at = ? WHERE user_id = ?",
                (datetime.now(timezone.utc).isoformat(), user_id)
            )
            logger.debug(f"User {user_id} marked as having started the bot.")
            return
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error marking user {user_id} as started bot: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error marking user {user_id} as started bot: {e}", exc_info=True)
            raise

async def get_group_punish_action(group_id: int) -> str:
    """Fetch the punish action for a group, returning default if not set."""
    retries = 3
    for attempt in range(retries):
        try:
            row = await db_fetchone(
                "SELECT punish_action FROM groups WHERE group_id = ?",
                (group_id,)
            )
            return row["punish_action"] if row and row["punish_action"] else DEFAULT_PUNISH_ACTION
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error fetching punish_action for group {group_id}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error fetching punish_action for group {group_id}: {e}", exc_info=True)
            raise
    return DEFAULT_PUNISH_ACTION

async def set_group_punish_action_async(group_id: int, group_name: str, action: str) -> None:
    """Set the punish action for a group."""
    if action not in ["mute", "kick", "ban"]:
        logger.warning(f"Invalid punish action '{action}' for group {group_id}.")
        return

    retries = 3
    for attempt in range(retries):
        try:
            await db_execute(
                """INSERT INTO groups (
                    group_id, group_name, added_at, punish_action,
                    punish_duration_profile, punish_duration_message, punish_duration_mention_profile
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(group_id) DO UPDATE SET
                    punish_action = excluded.punish_action,
                    group_name = excluded.group_name""",
                (
                    group_id, group_name, datetime.now(timezone.utc).isoformat(), action,
                    DEFAULT_PUNISH_DURATION_PROFILE_SECONDS, DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS,
                    DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS
                )
            )
            logger.info(f"Punish action for group {group_id} set to {action}.")
            return
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error setting punish_action for group {group_id}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error setting punish_action for group {group_id}: {e}", exc_info=True)
            raise

async def get_group_punish_duration_for_trigger(group_id: int, trigger_type: str) -> int:
    """Fetch the punish duration for a group trigger type."""
    trigger_map = {
        "profile": ("punish_duration_profile", DEFAULT_PUNISH_DURATION_PROFILE_SECONDS),
        "message": ("punish_duration_message", DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS),
        "mention_profile": ("punish_duration_mention_profile", DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS)
    }
    column_name, default_duration = trigger_map.get(
        trigger_type, ("punish_duration_profile", DEFAULT_PUNISH_DURATION_PROFILE_SECONDS)
    )

    retries = 3
    for attempt in range(retries):
        try:
            row = await db_fetchone(
                f"SELECT {column_name} FROM groups WHERE group_id = ?",
                (group_id,)
            )
            return row[column_name] if row and row[column_name] is not None else default_duration
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error fetching {column_name} for group {group_id}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error fetching {column_name} for group {group_id}: {e}", exc_info=True)
            raise
    return default_duration

async def set_group_punish_duration_for_trigger_async(group_id: int, group_name: str, trigger_type: str, duration_seconds: int) -> None:
    """Set the punish duration for a group trigger type."""
    trigger_map = {
        "profile": "punish_duration_profile",
        "message": "punish_duration_message",
        "mention_profile": "punish_duration_mention_profile"
    }
    column_name = trigger_map.get(trigger_type)
    if not column_name:
        logger.warning(f"Invalid trigger_type '{trigger_type}' for setting duration for group {group_id}.")
        return

    retries = 3
    for attempt in range(retries):
        try:
            await db_execute(
                f"""INSERT INTO groups (
                    group_id, group_name, added_at, {column_name}
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(group_id) DO UPDATE SET
                    {column_name} = excluded.{column_name},
                    group_name = excluded.group_name""",
                (group_id, group_name, datetime.now(timezone.utc).isoformat(), duration_seconds)
            )
            logger.info(f"Punish duration for '{trigger_type}' in group {group_id} set to {duration_seconds}s.")
            return
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error setting {column_name} for group {group_id}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error setting {column_name} for group {group_id}: {e}", exc_info=True)
            raise
            
async def set_all_group_punish_durations_async(group_id: int, group_name: str, duration_seconds: int) -> None:
    """Set all punish durations for a group."""
    retries = 3
    for attempt in range(retries):
        try:
            await db_execute(
                """INSERT INTO groups (
                    group_id, group_name, added_at,
                    punish_duration_profile, punish_duration_message, punish_duration_mention_profile
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(group_id) DO UPDATE SET
                    punish_duration_profile = excluded.punish_duration_profile,
                    punish_duration_message = excluded.punish_duration_message,
                    punish_duration_mention_profile = excluded.punish_duration_mention_profile,
                    group_name = excluded.group_name""",
                (
                    group_id, group_name, datetime.now(timezone.utc).isoformat(),
                    duration_seconds, duration_seconds, duration_seconds
                )
            )
            logger.info(f"All punish durations for group {group_id} set to {duration_seconds} seconds.")
            return
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error setting all punish durations for group {group_id}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error setting all punish durations for group {group_id}: {e}", exc_info=True)
            raise
            
async def add_group_user_exemption(group_id: int, user_id: int) -> None:
    """Add a user exemption for a group."""
    retries = 3
    for attempt in range(retries):
        try:
            async with db_pool.cursor() as cursor:
                await cursor.execute(
                    "INSERT OR IGNORE INTO group_user_exemptions (group_id, user_id) VALUES (?, ?)",
                    (group_id, user_id)
                )
                await db_pool.commit()
                if cursor.rowcount > 0:
                    logger.info(f"Added group user exemption for G:{group_id} U:{user_id}")
                else:
                    logger.debug(f"Exemption for G:{group_id} U:{user_id} already exists.")
            return
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error adding group user exemption for G:{group_id} U:{user_id}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error adding group user exemption for G:{group_id} U:{user_id}: {e}", exc_info=True)
            raise
            
async def remove_group_user_exemption(group_id: int, user_id: int) -> None:
    """Remove a user exemption for a group."""
    retries = 3
    for attempt in range(retries):
        try:
            async with db_pool.cursor() as cursor:
                await cursor.execute(
                    "DELETE FROM group_user_exemptions WHERE group_id = ? AND user_id = ?",
                    (group_id, user_id)
                )
                await db_pool.commit()
                if cursor.rowcount > 0:
                    logger.info(f"Removed group user exemption for G:{group_id} U:{user_id}")
                else:
                    logger.debug(f"No exemption found for G:{group_id} U:{user_id} to remove.")
            return
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error removing group user exemption for G:{group_id} U:{user_id}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error removing group user exemption for G:{group_id} U:{user_id}: {e}", exc_info=True)
            raise
            
async def is_user_exempt_in_group(group_id: int, user_id: int) -> bool:
    """Check if a user is exempt in a group."""
    retries = 3
    for attempt in range(retries):
        try:
            row = await db_fetchone(
                "SELECT 1 FROM group_user_exemptions WHERE group_id = ? AND user_id = ?",
                (group_id, user_id)
            )
            return bool(row)
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error checking group exemption for G:{group_id} U:{user_id}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error checking group exemption for G:{group_id} U:{user_id}: {e}", exc_info=True)
            raise
    return False
    

async def get_feature_state(feature_name: str, default: bool = False) -> bool:
    """Check if a feature is enabled."""
    retries = 3
    for attempt in range(retries):
        try:
            row = await db_fetchone(
                "SELECT is_enabled FROM feature_control WHERE feature_name = ?",
                (feature_name,)
            )
            return bool(row["is_enabled"]) if row and row["is_enabled"] is not None else default
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error getting state for feature '{feature_name}': {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error getting state for feature '{feature_name}': {e}", exc_info=True)
            raise
    return default
    
async def set_feature_state(feature_name: str, is_enabled: bool) -> None:
    """Set the enabled state of a feature."""
    retries = 3
    for attempt in range(retries):
        try:
            async with db_pool.cursor() as cursor:
                await cursor.execute(
                    "INSERT OR REPLACE INTO feature_control (feature_name, is_enabled) VALUES (?, ?)",
                    (feature_name, int(is_enabled))
                )
                await db_pool.commit()
            logger.info(f"Feature '{feature_name}' set to {'enabled' if is_enabled else 'disabled'}.")
            if feature_name == "maintenance_mode_active":
                global MAINTENANCE_MODE
                MAINTENANCE_MODE = is_enabled
            return
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error setting state for feature '{feature_name}': {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error setting state for feature '{feature_name}': {e}", exc_info=True)
            raise
            
async def get_all_groups_from_db(batch_size: int = 100) -> List[int]:
    """Fetch all group IDs from the database, paginated."""
    groups = []
    offset = 0
    retries = 3
    while True:
        for attempt in range(retries):
            try:
                rows = await db_fetchall(
                    "SELECT group_id FROM groups LIMIT ? OFFSET ?",
                    (batch_size, offset)
                )
                if not rows:
                    return groups
                groups.extend(row['group_id'] for row in rows)
                offset += batch_size
                break
            except aiosqlite.OperationalError as e:
                if "database is locked" in str(e) and attempt < retries - 1:
                    logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                logger.error(f"DB error fetching groups (offset={offset}): {e}", exc_info=True)
                raise
            except Exception as e:
                logger.error(f"DB error fetching groups (offset={offset}): {e}", exc_info=True)
                raise
    return groups
    
async def get_all_users_from_db(started_only: bool = False) -> List[int]:
    """Fetch all user IDs from the database."""
    sql = "SELECT user_id FROM users"
    if started_only:
        sql += " WHERE has_started_bot = 1"

    retries = 3
    for attempt in range(retries):
        try:
            rows = await db_fetchall(sql)
            return [row['user_id'] for row in rows]
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error getting users (started_only={started_only}): {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error getting users (started_only={started_only}): {e}", exc_info=True)
            raise
    return []

async def get_all_groups_count() -> int:
    """Fetch the total number of groups in the database."""
    retries = 3
    for attempt in range(retries):
        try:
            row = await db_fetchone("SELECT COUNT(*) AS count FROM groups")
            return row['count'] if row else 0
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error getting group count: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error getting group count: {e}", exc_info=True)
            raise
    return 0
    
async def get_all_users_count(started_only: bool = False) -> int:
    """Fetch the total number of users in the database."""
    sql = "SELECT COUNT(*) AS count FROM users"
    if started_only:
        sql += " WHERE has_started_bot = 1"

    retries = 3
    for attempt in range(retries):
        try:
            row = await db_fetchone(sql)
            return row['count'] if row else 0
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error getting user count (started_only={started_only}): {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error getting user count (started_only={started_only}): {e}", exc_info=True)
            raise
    return 0
    
async def get_user_id_from_username(username: str) -> Optional[int]:
    """Retrieve a user ID from the database based on a username."""
    clean_username = username.lstrip('@').lower()
    retries = 3
    for attempt in range(retries):
        try:
            row = await db_fetchone(
                "SELECT user_id FROM users WHERE username = ?",
                (clean_username,)
            )
            return row['user_id'] if row else None
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error fetching user ID for username '{username}': {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error fetching user ID for username '{username}': {e}", exc_info=True)
            raise
    return None
    
async def add_unmute_attempt(user_id: int, chat_id: int) -> None:
    """Record a user's attempt to unmute themselves in a specific chat."""
    retries = 3
    for attempt in range(retries):
        try:
            async with db_pool.cursor() as cursor:
                current_timestamp = time.time()
                await cursor.execute(
                    """INSERT INTO unmute_attempts (user_id, chat_id, attempt_timestamp)
                       VALUES (?, ?, ?)
                       ON CONFLICT(user_id, chat_id) DO UPDATE SET
                           attempt_timestamp = excluded.attempt_timestamp""",
                    (user_id, chat_id, current_timestamp)
                )
                await db_pool.commit()
            logger.debug(f"Recorded unmute attempt for U:{user_id} in G:{chat_id} at {current_timestamp}.")
            return
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error recording unmute attempt for U:{user_id} G:{chat_id}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error recording unmute attempt for U:{user_id} G:{chat_id}: {e}", exc_info=True)
            raise
            
async def get_last_unmute_attempt_time(user_id: int, chat_id: int) -> Optional[float]:
    """Fetch the timestamp of the last unmute attempt for a user in a chat."""
    retries = 3
    for attempt in range(retries):
        try:
            row = await db_fetchone(
                "SELECT attempt_timestamp FROM unmute_attempts WHERE user_id = ? AND chat_id = ?",
                (user_id, chat_id)
            )
            return float(row['attempt_timestamp']) if row and row['attempt_timestamp'] is not None else None
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error fetching last unmute attempt for U:{user_id} G:{chat_id}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error fetching last unmute attempt for U:{user_id} G:{chat_id}: {e}", exc_info=True)
            raise
    return None
    
# Bad Actor DB Functions
async def add_bad_actor(user_id: int, reason: str) -> None:
    """Add or update a bad actor in the database."""
    if user_id <= 0:
        logger.warning(f"Invalid user_id {user_id} provided to add_bad_actor.")
        return

    retries = 3
    for attempt in range(retries):
        try:
            async with db_pool.cursor() as cursor:
                await cursor.execute(
                    """INSERT INTO bad_actors (user_id, reason, added_at)
                       VALUES (?, ?, ?)
                       ON CONFLICT(user_id) DO UPDATE SET
                           reason = excluded.reason,
                           added_at = excluded.added_at""",
                    (user_id, reason, datetime.now(timezone.utc).isoformat())
                )
                await db_pool.commit()
            logger.info(f"User {user_id} added/updated as bad actor. Reason: {reason}")
            return
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error adding bad actor {user_id}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error adding bad actor {user_id}: {e}", exc_info=True)
            raise
            
#is_bad_actor function 
async def is_bad_actor(user_id: int) -> bool:
    """Check if a user is a bad actor based on expiry settings."""
    global BAD_ACTOR_EXPIRY_SECONDS

    if user_id <= 0:
        logger.warning(f"Invalid user_id {user_id} provided to is_bad_actor.")
        return False

    retries = 3
    for attempt in range(retries):
        try:
            row = await db_fetchone(
                "SELECT added_at FROM bad_actors WHERE user_id = ?",
                (user_id,)
            )
            if not row:
                return False

            if BAD_ACTOR_EXPIRY_SECONDS == 0:
                logger.debug(f"User {user_id} is a permanent bad actor.")
                return True

            added_at_str = row["added_at"]
            try:
                added_at = datetime.fromisoformat(added_at_str).replace(tzinfo=timezone.utc)
            except ValueError:
                logger.warning(f"Invalid added_at format '{added_at_str}' for user {user_id}. Assuming permanent.")
                return True

            now = datetime.now(timezone.utc)
            if (now - added_at).total_seconds() <= BAD_ACTOR_EXPIRY_SECONDS:
                logger.debug(f"User {user_id} is a temporary bad actor (expires in {format_duration(BAD_ACTOR_EXPIRY_SECONDS)}).")
                return True

            async with db_pool.cursor() as cursor:
                await cursor.execute("DELETE FROM bad_actors WHERE user_id = ?", (user_id,))
                await db_pool.commit()
            logger.info(f"Expired bad actor status for user {user_id} removed.")
            return False
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error checking bad actor status for {user_id}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error checking bad actor status for {user_id}: {e}", exc_info=True)
            raise
    return False
    
# Timed Broadcast DB Functions
async def add_timed_broadcast_to_db(
    job_name: str,
    target_type: str,
    message_text: str,
    interval_seconds: int,
    next_run_time: float,
    markup_json: Optional[str] = None
) -> None:
    """Add or update a timed broadcast in the database."""
    if not job_name or not job_name.strip():
        logger.warning("Invalid job_name provided to add_timed_broadcast_to_db.")
        return
    if interval_seconds <= 0:
        logger.warning(f"Invalid interval_seconds {interval_seconds} for job {job_name}.")
        return

    retries = 3
    for attempt in range(retries):
        try:
            async with db_pool.cursor() as cursor:
                await cursor.execute(
                    """INSERT OR REPLACE INTO timed_broadcasts (
                        job_name, target_type, message_text, interval_seconds, created_at, next_run_time, markup_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        job_name, target_type, message_text, interval_seconds,
                        datetime.now(timezone.utc).isoformat(), next_run_time, markup_json
                    )
                )
                await db_pool.commit()
            logger.info(f"Timed broadcast '{job_name}' added/updated in DB (markup: {markup_json is not None}).")
            return
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries} for job {job_name}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error adding timed broadcast '{job_name}': {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error adding timed broadcast '{job_name}': {e}", exc_info=True)
            raise
            
async def remove_timed_broadcast_from_db(job_name: str) -> None:
    """Remove a timed broadcast from the database."""
    if not job_name or not job_name.strip():
        logger.warning("Invalid job_name provided to remove_timed_broadcast_from_db.")
        return

    retries = 3
    for attempt in range(retries):
        try:
            async with db_pool.cursor() as cursor:
                await cursor.execute("DELETE FROM timed_broadcasts WHERE job_name = ?", (job_name,))
                await db_pool.commit()
                if cursor.rowcount > 0:
                    logger.info(f"Timed broadcast '{job_name}' removed from DB.")
                else:
                    logger.debug(f"No timed broadcast found for '{job_name}' to remove.")
            return
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries} for job {job_name}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error removing timed broadcast '{job_name}': {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error removing timed broadcast '{job_name}': {e}", exc_info=True)
            raise
            
async def get_all_timed_broadcasts_from_db(batch_size: int = 100) -> List[Dict[str, Any]]:
    """Fetch all timed broadcasts from the database, paginated."""
    broadcasts = []
    offset = 0
    retries = 3
    while True:
        for attempt in range(retries):
            try:
                rows = await db_fetchall(
                    """SELECT job_name, target_type, message_text, interval_seconds, next_run_time, markup_json
                       FROM timed_broadcasts LIMIT ? OFFSET ?""",
                    (batch_size, offset)
                )
                if not rows:
                    return broadcasts
                broadcasts.extend(rows)
                offset += batch_size
                break
            except aiosqlite.OperationalError as e:
                if "database is locked" in str(e) and attempt < retries - 1:
                    logger.debug(f"Database locked, retrying {attempt + 1}/{retries} for broadcasts...")
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                logger.error(f"DB error fetching timed broadcasts (offset={offset}): {e}", exc_info=True)
                raise
            except Exception as e:
                logger.error(f"DB error fetching timed broadcasts (offset={offset}): {e}", exc_info=True)
                raise
    return broadcasts

# --- Feature Control Decorator ---
def feature_controlled(feature_name_or_handler):
    """Decorator to control feature execution based on feature state and maintenance mode."""
    feature_name = (
        feature_name_or_handler
        if isinstance(feature_name_or_handler, str)
        else feature_name_or_handler.__name__.replace("_command", "").lower()
    )

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            global MAINTENANCE_MODE
            user = update.effective_user
            chat = update.effective_chat

            maintenance_bypass_commands = {"maintenance", "enable", "disable", "stats", "clearcache", "broadcast", "bcastall", "bcastself", "start", "help"}

            if MAINTENANCE_MODE and feature_name not in maintenance_bypass_commands:
                logger.debug(f"Feature '{feature_name}' blocked for user {user.id if user else 'N/A'} in maintenance mode.")
                target_id = chat.id if chat else user.id if user else None
                if target_id:
                    await send_message_safe(context, target_id, patterns.MAINTENANCE_MODE_MESSAGE)
                return

            always_enabled_features = {"start", "help"}
            if feature_name in always_enabled_features:
                logger.debug(f"Feature '{feature_name}' is always enabled for user {user.id if user else 'N/A'}.")
                return await func(update, context, *args, **kwargs)

            if not await get_feature_state(feature_name, default=True):
                logger.debug(f"Feature '{feature_name}' is disabled for user {user.id if user else 'N/A'}.")
                target_id = chat.id if chat else user.id if user else None
                if target_id:
                    await send_message_safe(context, target_id, patterns.FEATURE_DISABLED_MESSAGE.format(command_name=feature_name))
                return

            return await func(update, context, *args, **kwargs)
        return wrapper

    return decorator if isinstance(feature_name_or_handler, str) else decorator(feature_name_or_handler)
    
async def is_message_processing_enabled() -> bool:
    """Check if message processing is enabled."""
    global MAINTENANCE_MODE
    if MAINTENANCE_MODE:
        logger.debug("Message processing disabled due to maintenance mode.")
        return False
    return await get_feature_state("message_processing", default=True)

# --- Utility Functions ---
async def resolve_username_via_link(username: str) -> Optional[int]:
    """Resolve a username via t.me link when getChat fails."""
    clean_username = username.lstrip('@').strip()
    if not clean_username:
        logger.warning("Empty or invalid username provided to resolve_username_via_link.")
        return None

    retries = 3
    for attempt in range(retries):
        try:
            chat = await get_chat_with_retry(context.bot, f"@{clean_username}")
            if chat and hasattr(chat, 'id'):
                logger.debug(f"Resolved {username} via link to user ID {chat.id}")
                return chat.id
            return None
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries} for username {username}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error resolving username {username}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.debug(f"Failed to resolve {username} via link: {e}")
            return None

def log_cache_access(cache_name: str, key: Any, action: str, cache_instance: Optional[TTLCache]) -> None:
    """Log cache access details."""
    logger.debug(f"Cache '{cache_name}': {action} key={key!r}, size={len(cache_instance) if cache_instance else 'N/A'}")
    
async def cleanup_caches_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periodically clean up caches."""
    global user_profile_cache, username_to_id_cache
    try:
        if user_profile_cache is None or username_to_id_cache is None:
            logger.warning("Cache cleanup skipped: caches not initialized.")
            return
        pc_before, uc_before = len(user_profile_cache), len(username_to_id_cache)
        user_profile_cache.clear()
        username_to_id_cache.clear()
        logger.info(f"Cache cleanup: cleared {pc_before} profile entries, {uc_before} username entries.")
    except Exception as e:
        logger.error(f"Error during cache cleanup: {e}", exc_info=True)
        
async def get_bot_username(context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
    """Fetch and cache the bot's username."""
    global bot_username_cache
    if bot_username_cache:
        return bot_username_cache

    retries = 3
    for attempt in range(retries):
        try:
            bot = await context.bot.get_me()
            bot_username_cache = bot.username
            logger.debug(f"Bot username cached: {bot_username_cache}")
            return bot_username_cache
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries} for bot username...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error getting bot username: {e}", exc_info=True)
            bot_username_cache = None
            return None
        except Exception as e:
            logger.error(f"Error getting bot username: {e}", exc_info=True)
            bot_username_cache = None
            return None
            
def is_potential_command(message: TGMessage) -> bool:
    """Check if a message is likely a command."""
    if not message or not message.text:
        return False

    text = message.text.strip()
    if not text.startswith("/"):
        return False

    if message.entities:
        for entity in message.entities:
            if entity.type == MessageEntity.BOT_COMMAND and entity.offset == 0:
                command_text = text[:entity.length]
                if re.match(r"^/[a-zA-Z0-9_]+(@[a-zA-Z0-9_]+)?$", command_text):
                    return True

    return message.text.count(' ') <= MAX_COMMAND_ARGS_SPACES
    
async def check_for_links_enhanced(context: ContextTypes.DEFAULT_TYPE, text: str, field: str = "message_text") -> Tuple[bool, Optional[str]]:
    if not text:
        logger.debug(f"Field '{field}' is empty for text check, skipping")
        return False, None
    logger.debug(f"Checking {field}: '{text[:50]}...' with pattern {patterns.COMBINED_FORBIDDEN_PATTERN}")
    
    
    logger.info(f"Checking field '{field}' for links/keywords: '{text[:100]}{'...' if len(text) > 100 else ''}'")
    
    text_lower = text.lower()
    whitelist_patterns = getattr(patterns, 'WHITELIST_PATTERNS', [])
    combined_forbidden_pattern = getattr(patterns, 'COMBINED_FORBIDDEN_PATTERN', r"a^")
    forbidden_words = getattr(patterns, 'FORBIDDEN_WORDS', [])
    
    logger.debug(f"Applying whitelist patterns to '{field}': {whitelist_patterns}")
    for pattern in whitelist_patterns:
        try:
            if re.search(pattern, text_lower, re.IGNORECASE):
                logger.info(f"Whitelisted pattern '{pattern}' matched in '{text[:50]}...' (field: {field})")
                return False, "whitelist_ok"
        except re.error as e:
            logger.error(f"Invalid regex in WHITELIST_PATTERNS: '{pattern}'. Error: {e}")
            continue
    
    logger.debug(f"Applying forbidden pattern to '{field}': {combined_forbidden_pattern}")
    if combined_forbidden_pattern:
        try:
            if re.search(combined_forbidden_pattern, text, re.IGNORECASE):
                logger.info(f"Forbidden link pattern matched in '{text[:50]}...' (field: {field})")
                return True, "forbidden_link"
        except re.error as e:
            logger.error(f"Invalid regex in COMBINED_FORBIDDEN_PATTERN: '{combined_forbidden_pattern}'. Error: {e}")
    
    normalized_text = ' '.join(re.sub(r'[^\w\s]', '', text_lower, flags=re.UNICODE).split())
    logger.debug(f"Normalized text for keyword check in '{field}': '{normalized_text[:50]}...'")
    
    if forbidden_words:
        logger.debug(f"Applying forbidden words to '{field}': {forbidden_words}")
        try:
            for word in forbidden_words:
                if re.search(word, normalized_text, re.IGNORECASE | re.UNICODE):
                    logger.info(f"Forbidden keyword '{word}' matched in '{normalized_text[:50]}...' (field: {field})")
                    return True, "prohibited_keyword"
        except re.error as e:
            logger.error(f"Invalid regex in FORBIDDEN_WORDS: '{word}'. Error: {e}")
    
    logger.info(f"No forbidden links/keywords found in '{field}'")
    return False, None

from telegram import Message # Make sure to import Message

async def send_message_safe(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    retries: int = 3,
    **kwargs
) -> Optional[Message]:
    """Safely send a message, handling common errors."""
    if not text:
        logger.warning(f"Attempted to send empty message to {chat_id}.")
        return None

    for attempt in range(retries):
        try:
            return await context.bot.send_message(
                chat_id=chat_id, text=text, **kwargs
            )
        except RetryAfter as e:
            if attempt == retries - 1:
                logger.error(f"Max retries reached for chat {chat_id}: {e}")
                return None
            logger.warning(f"Rate limit for {chat_id}. Retrying after {e.retry_after}s.")
            await asyncio.sleep(e.retry_after)
        except Forbidden as e:
            logger.warning(f"Forbidden to send to {chat_id}: {e}")
            if chat_id < 0:
                try:
                    chat_member = await context.bot.get_chat_member(chat_id, context.bot.id)
                    if chat_member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED]:
                        await remove_group_from_db(chat_id)
                except Exception as e_check:
                    logger.warning(f"Could not check bot status in {chat_id}: {e_check}. Removing from DB.")
                    await remove_group_from_db(chat_id)
            return None
        except BadRequest as e:
            logger.warning(f"BadRequest to {chat_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error sending to {chat_id}: {e}", exc_info=True)
            return None
    return None


async def get_chat_with_retry(bot, chat_id: Union[str, int], retries: int = 3, delay: int = 2) -> Optional[telegram.Chat]:
    """Fetch a chat with retry logic."""
    if isinstance(chat_id, str) and not chat_id.startswith('@'):
        chat_id = f'@{chat_id.strip()}'

    for attempt in range(retries):
        try:
            logger.debug(f"Attempt {attempt + 1}/{retries} to get chat {chat_id}")
            return await bot.get_chat(chat_id)
        except BadRequest as e:
            if "chat not found" in str(e).lower():
                logger.debug(f"Chat {chat_id} not found on attempt {attempt + 1}.")
                return None
            if "too many requests" in str(e).lower():
                if attempt < retries - 1:
                    logger.warning(f"Flood control for {chat_id}. Retrying after {delay * (attempt + 1)}s.")
                    await asyncio.sleep(delay * (attempt + 1))
                else:
                    logger.error(f"Failed {chat_id} after {retries} attempts: flood control.")
                    raise
            else:
                logger.error(f"BadRequest for {chat_id}: {e}", exc_info=True)
                raise
        except (TimedOut, NetworkError) as e:
            if attempt < retries - 1:
                logger.warning(f"Network error for {chat_id}: {e}. Retrying after {delay * (attempt + 1)}s.")
                await asyncio.sleep(delay * (attempt + 1))
            else:
                logger.error(f"Failed {chat_id} after {retries} attempts: {e}")
                raise
        except Forbidden as e:
            logger.warning(f"Forbidden for {chat_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error for {chat_id}: {e}", exc_info=True)
            if attempt < retries - 1:
                await asyncio.sleep(delay * (attempt + 1))
            else:
                raise
    return None

# --- get_chat_name function ---
async def get_chat_name(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> str:
    """Fetch the chat name safely."""
    if chat_id > 0:
        return f"Private Chat {chat_id}"

    try:
        chat = await get_chat_with_retry(context.bot, chat_id)
        if not chat:
            return f"Unknown Chat {chat_id}"
        return chat.title or f"@{chat.username}" if chat.username else f"Chat {chat_id}"
    except Exception as e:
        logger.error(f"Error fetching chat name for {chat_id}: {e}", exc_info=True)
        return f"Error Fetching Chat Name {chat_id}"
# --- get_chat_name function ---

async def user_has_links_cached(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> Tuple[bool, Optional[str], Optional[str]]:
    global user_profile_cache
    cache_key = user_id
    if cache_key in user_profile_cache:
        return user_profile_cache[cache_key]

    try:
        user_chat = await get_chat_with_retry(context.bot, user_id)
        if not user_chat:
            result = (False, "user_not_found", None)
            user_profile_cache[cache_key] = result
            return result

        fields_to_check = [
            ("first_name", user_chat.first_name or ""),
            ("last_name", getattr(user_chat, 'last_name', "") or ""),
            ("bio", getattr(user_chat, 'bio', "") or ""),
            ("username", getattr(user_chat, 'username', "") or "")
        ]

        for field_name, field_value in fields_to_check:
            if field_value:
                has_issue, issue_type = await check_for_links_enhanced(context, field_value, field_name)
                if has_issue:
                    result = (True, field_name, issue_type)
                    user_profile_cache[cache_key] = result
                    return result

        result = (False, None, None)
        user_profile_cache[cache_key] = result
        return result
    except Exception as e:
        logger.error(f"Error checking profile for user {user_id}: {e}", exc_info=True)
        result = (False, "error", str(e))
        user_profile_cache[cache_key] = result
        return result
        
async def is_real_telegram_user_cached(context: ContextTypes.DEFAULT_TYPE, username: str) -> Tuple[Optional[str], bool]:
    """Check if a username corresponds to a real Telegram user, using cache."""
    username = username.strip().lstrip('@')
    if not username:
        logger.warning("Empty username provided to is_real_telegram_user_cached.")
        return None, False

    if username.lower().endswith('bot'):
        logger.debug(f"Username @{username} ends with 'bot'.")
        return None, False

    cache_key = f"user_cache:@{username.lower()}"
    cached = context.bot_data.get(cache_key)
    if cached:
        logger.debug(f"Cache hit for @{username}: {cached}")
        return cached["user_id"], cached["is_real"]

    try:
        user_id = await get_user_id_from_username(username)
        if user_id:
            result = (str(user_id), True)
            context.bot_data[cache_key] = {"user_id": str(user_id), "is_real": True}
            logger.debug(f"Resolved @{username} to user_id {user_id} from DB.")
            return result

        chat = await get_chat_with_retry(context.bot, f"@{username}")
        if chat and hasattr(chat, 'id'):
            result = (str(chat.id), True)
            context.bot_data[cache_key] = {"user_id": str(chat.id), "is_real": True}
            logger.debug(f"Resolved @{username} to user_id {chat.id} via API.")
        else:
            result = (None, False)
            context.bot_data[cache_key] = {"user_id": None, "is_real": False}
            logger.debug(f"Failed to resolve @{username}.")
        return result
    except Exception as e:
        logger.error(f"Error resolving @{username}: {e}", exc_info=True)
        result = (None, False)
        context.bot_data[cache_key] = {"user_id": None, "is_real": False}
        return result
        
async def is_user_subscribed(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id_for_pm_guidance: Optional[int] = None
) -> bool:
    """Check if a user is subscribed to the required channel."""
    channel_id = settings.get("channel_id")
    if not channel_id:
        logger.debug("No channel ID set; subscription check bypassed.")
        return True

    try:
        channel_chat = await get_chat_with_retry(context.bot, channel_id)
        if not channel_chat or channel_chat.type != TGChat.CHANNEL:
            logger.error(f"Invalid channel ID {channel_id}. Disabling subscription check.")
            settings["channel_id"] = None
            return True

        invite_link = settings.get("channel_invite_link")
        if not invite_link:
            invite_link = channel_chat.invite_link or (f"https://t.me/{channel_chat.username}" if channel_chat.username else None)
            if invite_link:
                settings["channel_invite_link"] = invite_link
            else:
                logger.warning(f"No invite link for channel {channel_id}.")

        member = await context.bot.get_chat_member(channel_id, user_id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return True

        if chat_id_for_pm_guidance and invite_link:
            bot_username = await get_bot_username(context)
            if bot_username:
                pm_message = patterns.VERIFY_PLEASE_JOIN_CHANNEL_MESSAGE.format(channel_link=invite_link)
                kb = [[InlineKeyboardButton(
                    patterns.VERIFY_JOIN_BUTTON_TEXT,
                    callback_data=f"verify_join_pm_{chat_id_for_pm_guidance}"
                )]]
                await send_message_safe(
                    context, user_id, pm_message,
                    reply_markup=InlineKeyboardMarkup(kb),
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
                logger.info(f"Sent PM to {user_id} for channel subscription.")
        return False

    except RetryAfter as e:
        logger.warning(f"Rate limit for subscription check for {user_id}. Retrying after {e.retry_after}s.")
        await asyncio.sleep(e.retry_after)
        return await is_user_subscribed(context, user_id, chat_id_for_pm_guidance)
    except (Forbidden, BadRequest) as e:
        if isinstance(e, Forbidden) or "admin_rights_restricted" in str(e).lower():
            logger.warning(f"Bot lacks permissions in channel {channel_id}: {e}. Disabling subscription check.")
            settings["channel_id"] = None
            return True
        logger.debug(f"User {user_id} not in channel {channel_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error checking subscription for {user_id} in {channel_id}: {e}", exc_info=True)
        return False

async def log_action_db(
    context: ContextTypes.DEFAULT_TYPE,
    action: str,
    user_id: int,
    chat_id: Optional[int],
    reason: str
) -> None:
    """Log an action to the database and logger."""
    user_mention = f"User ID {user_id}"
    try:
        user_chat = await get_chat_with_retry(context.bot, user_id)
        if user_chat:
            user_mention = user_chat.mention_html() if hasattr(user_chat, 'mention_html') else f"@{user_chat.username or user_id}"
    except Exception as e:
        logger.debug(f"Could not fetch user {user_id} for logging: {e}")

    chat_info = f"Chat: {chat_id}" if chat_id is not None else "PM"
    logger.info(f"ACTION: {action} | User: {user_mention} ({user_id}) | {chat_info} | Reason: {reason}")

    retries = 3
    for attempt in range(retries):
        try:
            async with db_pool.cursor() as cursor:
                await cursor.execute(
                    """INSERT INTO action_log (action, user_id, chat_id, reason, timestamp)
                       VALUES (?, ?, ?, ?, ?)""",
                    (action, user_id, chat_id, reason, datetime.now(timezone.utc).isoformat())
                )
                await db_pool.commit()
            logger.debug(f"Logged action '{action}' for user {user_id} in DB.")
            return
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries} for action log...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error logging action for {user_id}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"DB error logging action for {user_id}: {e}", exc_info=True)
            raise

async def get_problematic_mentions(context: ContextTypes.DEFAULT_TYPE, text: str) -> List[Tuple[str, int, Optional[str]]]:
    """Identify problematic user mentions in text."""
    problematic_users: List[Tuple[str, int, Optional[str]]] = []
    if not text:
        logger.debug("Empty text; no problematic mentions.")
        return problematic_users

    try:
        words = text.split()
        mentions = [w.rstrip('.,!?;:"\'') for w in words if w.startswith('@')]
        tg_links = [w for w in words if w.startswith(('t.me/', 'https://t.me/'))]

        for mention in mentions:
            clean_mention = mention.lstrip('@')
            if not clean_mention:
                logger.debug(f"Skipping empty mention: {mention}")
                continue

            if clean_mention.lower().endswith('bot'):
                logger.debug(f"Mention @{clean_mention} ends with 'bot'.")
                problematic_users.append((clean_mention, 1, None))
                continue

            user_id = await get_user_id_from_username(clean_mention)
            if user_id:
                spam_score = 0  # Placeholder; implement scoring if needed
                problematic_users.append((clean_mention, spam_score, str(user_id)))
                logger.debug(f"Resolved @{clean_mention} to user_id {user_id}.")
                continue

            for link in tg_links:
                link_username = link.split('t.me/')[-1].lstrip('@')
                if link_username.lower() == clean_mention.lower():
                    chat = await get_chat_with_retry(context.bot, f"@{link_username}")
                    if chat and hasattr(chat, 'id'):
                        user_id = str(chat.id)
                        problematic_users.append((clean_mention, 0, user_id))
                        logger.debug(f"Resolved @{clean_mention} via link to {user_id}.")
                        break
            else:
                logger.debug(f"Unresolved mention @{clean_mention}.")
                problematic_users.append((clean_mention, 0, None))

        logger.debug(f"Problematic mentions: {problematic_users}")
        return problematic_users
    except Exception as e:
        logger.error(f"Error in get_problematic_mentions: {e}", exc_info=True)
        return []

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not (message and user and chat) or chat.type not in [TGChat.GROUP, TGChat.SUPERGROUP]:
        return

    message_text = message.text or message.caption or ""
    has_issue, issue_type = await check_for_links_enhanced(context, message_text, "message_text")
    if has_issue:
        reasons = [f"Message contains {issue_type}"]
        await take_action(update, context, reasons, "message")
 
    
async def _process_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    chat: telegram.Chat,
    user: telegram.User,
    message: telegram.Message,
    message_key: Tuple[int, int]
) -> None:
    """Process a message for rule violations."""
    if chat.type not in [TGChat.GROUP, TGChat.SUPERGROUP]:
        logger.debug(f"Message in {chat.id} (type: {chat.type}) is not a group/supergroup.")
        return

    is_sender_admin = (
        (message.sender_chat and message.sender_chat.id == chat.id) or
        await is_user_group_admin_or_creator(context, chat.id, user.id)
    )
    if is_sender_admin:
        logger.debug(f"Sender {user.id} is admin in {chat.id}.")
        message_text = message.text or message.caption or ""
        problematic_mentions_list = await get_problematic_mentions(context, message_text)
        if problematic_mentions_list:
            await take_action(
                update, context,
                ["Admin message mentioned problematic users"],
                None,
                problematic_mentions_list
            )
        return

    chat_info = await get_chat_with_retry(context.bot, chat.id)
    if not chat_info:
        logger.warning(f"Chat {chat.id} inaccessible. Removing from DB.")
        if chat.id < 0:
            await remove_group_from_db(chat.id)
        return

    if user.id in settings.get("free_users", set()) or await is_user_exempt_in_group(chat.id, user.id):
        logger.debug(f"User {user.id} is exempt in {chat.id}.")
        return

    await add_group(chat.id, chat.title or f"Group_{chat.id}")
    await add_user(
        user_id=user.id,
        username=user.username or "",
        first_name=user.first_name or "",
        last_name=user.last_name or ""
    )

    if is_potential_command(message):
        command_entity = next((e for e in message.entities if e.type == MessageEntity.BOT_COMMAND and e.offset == 0), None)
        if command_entity:
            command_text = message.text[:command_entity.length]
            bot_name = await get_bot_username(context)
            if "@" in command_text and bot_name and command_text.split("@")[1].lower() != bot_name.lower():
                logger.debug(f"Command '{command_text}' in {chat.id} is for another bot.")
                return

    message_text = message.text or message.caption or ""
    primary_trigger_type: Optional[str] = None
    reasons: List[str] = []

    try:
        if await is_bad_actor(user.id):
            primary_trigger_type = "profile"
            reasons.append(patterns.SENDER_IS_BAD_ACTOR_REASON.get("english", "Known bad actor"))
        else:
            has_issue, field, issue_type = await user_has_links_cached(context, user.id)
            if has_issue:
                primary_trigger_type = "profile"
                reasons.append(
                    patterns.SENDER_PROFILE_VIOLATION_REASON.format(
                        field=field or patterns.UNKNOWN_TEXT,
                        issue_type=issue_type or patterns.UNKNOWN_TEXT
                    )
                )
                await add_bad_actor(user.id, f"Profile issue ({issue_type or 'unknown'}) in {field or 'unknown'}")

        has_issue, issue_type = await check_for_links_enhanced(context, message_text, "message_text")
        if has_issue:
            primary_trigger_type = primary_trigger_type or "message"
            reasons.append(
                patterns.MESSAGE_VIOLATION_REASON.format(
                    message_issue_type=issue_type or patterns.UNKNOWN_TEXT
                )
            )
            if user.id not in AUTHORIZED_USERS:
                await add_bad_actor(user.id, f"Message content issue ({issue_type or 'unknown'})")

        problematic_mentions_list = await get_problematic_mentions(context, message_text)
        if problematic_mentions_list:
            reasons.append(
                patterns.MENTIONED_USER_PROFILE_VIOLATION_REASON.format(
                    users_summary=", ".join(f"@{m[0]}" for m in problematic_mentions_list)
                )
            )

        if has_issue:
            try:
                await message.delete()
                logger.debug(f"Deleted message from {user.id} in {chat.id}.")
            except (BadRequest, Forbidden) as e:
                logger.warning(f"Could not delete message from {user.id} in {chat.id}: {e}")

        if primary_trigger_type or problematic_mentions_list:
            await take_action(update, context, reasons, primary_trigger_type, problematic_mentions_list)

    except Forbidden as e:
        logger.warning(f"Forbidden in {chat.id}: {e}")
        if chat.id < 0:
            await remove_group_from_db(chat.id)
    except Exception as e:
        logger.error(f"Error processing message from {user.id} in {chat.id}: {e}", exc_info=True)
        
async def get_bot_permissions(bot, chat_id: int) -> Dict[str, bool]:
    """Fetch bot's permissions in the chat."""
    retries = 3
    for attempt in range(retries):
        try:
            bot_member = await bot.get_chat_member(chat_id, bot.id)
            return {
                "can_restrict_members": getattr(bot_member, "can_restrict_members", False),
                "can_ban_members": getattr(bot_member, "can_ban_members", False),
            }
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                logger.debug(f"Database locked, retrying {attempt + 1}/{retries} for permissions in {chat_id}...")
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            logger.error(f"DB error fetching permissions in {chat_id}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Error fetching permissions in {chat_id}: {e}", exc_info=True)
            return {"can_restrict_members": False, "can_ban_members": False}
            
async def apply_action(
    bot, chat_id: int, user_id: int, action: str, duration_seconds: int, permissions: Dict[str, bool]
) -> Optional[str]:
    """Apply an action (mute, kick, ban) to a user."""
    try:
        if action == "ban":
            if not permissions["can_ban_members"]:
                logger.warning(f"No permission to ban {user_id} in {chat_id}")
                return None
            await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            return "banned"
        elif action == "kick":
            if not permissions["can_ban_members"]:
                logger.warning(f"No permission to kick {user_id} in {chat_id}")
                return None
            await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            await asyncio.sleep(1)
            await bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)
            return "kicked"
        else:  # mute
            if not permissions["can_restrict_members"]:
                logger.warning(f"No permission to mute {user_id} in {chat_id}")
                return None
            until_date = (
                datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
                if duration_seconds > 0 else None
            )
            mute_permissions = ChatPermissions(
                can_send_messages=False, can_send_audios=False, can_send_documents=False,
                can_send_photos=False, can_send_videos=False, can_send_video_notes=False,
                can_send_voice_notes=False, can_send_polls=False, can_send_other_messages=False,
                can_add_web_page_previews=False, can_change_info=False, can_invite_users=False,
                can_pin_messages=False, can_manage_topics=False
            )
            await bot.restrict_chat_member(
                chat_id=chat_id, user_id=user_id, permissions=mute_permissions, until_date=until_date
            )
            return "muted"
    except Forbidden as e:
        logger.warning(f"Forbidden to {action} {user_id} in {chat_id}: {e}")
        return None
    except BadRequest as e:
        logger.warning(f"BadRequest to {action} {user_id} in {chat_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error applying {action} to {user_id} in {chat_id}: {e}", exc_info=True)
        return None

async def send_punishment_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    message_id: Optional[int] = None,
    reply_markup: Optional[InlineKeyboardMarkup] = None
) -> Optional[int]:
    """Send or edit a punishment message."""
    try:
        if message_id:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=text,
                parse_mode=ParseMode.HTML, reply_markup=reply_markup, disable_web_page_preview=True
            )
            return message_id
        sent_message = await send_message_safe(
            context, chat_id, text,
            reply_markup=reply_markup, parse_mode=ParseMode.HTML, disable_web_page_preview=True
        )
        return sent_message.message_id if sent_message else None
    except TelegramError as e:
        logger.error(f"Failed to {'edit' if message_id else 'send'} message in {chat_id}: {e}", exc_info=True)
        return None

async def take_action(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    reasons: List[str],
    sender_trigger_type: Optional[str],
    problematic_mentions_list: List[Tuple[str, int, Optional[str]]] = None
) -> None:
    """Handle actions for rule violations."""
    problematic_mentions_list = problematic_mentions_list or []
    chat = update.effective_chat
    sender = update.effective_user
    if not (chat and sender):
        logger.error("Missing chat or sender in take_action.")
        return

    logger.debug(
        f"take_action: user={sender.id}, chat={chat.id}, reasons={reasons}, "
        f"trigger={sender_trigger_type}, mentions={len(problematic_mentions_list)}"
    )

    sender_html = sender.mention_html() if hasattr(sender, "mention_html") else f"@{sender.username or sender.id}"
    action_taken_on_sender = False
    bot_permissions = await get_bot_permissions(context.bot, chat.id)
    cache = context.bot_data.setdefault("notification_debounce_cache", {})

    if sender_trigger_type:
        debounce_key = f"punish_notification_{chat.id}_{sender.id}"
        if debounce_key in cache:
            logger.debug(f"Debounced action for sender {sender.id} in {chat.id}")
            return

        cache[debounce_key] = True
        action = await get_group_punish_action(chat.id)
        duration_seconds = await get_group_punish_duration_for_trigger(chat.id, sender_trigger_type)
        dialogue = random.choice(getattr(patterns, "BIO_LINK_DIALOGUES_LIST", [
            {"english": "Your content violates our rules.", "hindi": "आपकी सामग्री हमारे नियमों का उल्लंघन करती है।"}
        ]))
        reason_detail = f"their {sender_trigger_type.replace('_', ' ')} ({', '.join(reasons)})"
        action_string = (
            f"muted for {format_duration(duration_seconds)}" if action == "mute" and duration_seconds > 0
            else "permanently muted" if action == "mute" else action
        )

        message_text = (
            f"<b>{sender_html}</b> has been {action_string} due to {reason_detail}. {dialogue['english']}"
            f"\n\n{dialogue['hindi']}" if dialogue.get("hindi") else ""
        )

        kb_rows = [[InlineKeyboardButton("Admin Approve", callback_data=f"approve_{sender.id}_{chat.id}_INITIAL")]]
        bot_username = await get_bot_username(context)
        if action == "mute" and bot_username:
            pm_url = f"https://t.me/{bot_username}?start=unmute_{chat.id}_{sender.id}_INITIAL"
            kb_rows.insert(0, [InlineKeyboardButton("Unmute via Bot PM", url=pm_url)])

        actual_action = await apply_action(context.bot, chat.id, sender.id, action, duration_seconds, bot_permissions)
        if actual_action:
            action_taken_on_sender = True
            await log_action_db(context, actual_action.capitalize(), sender.id, chat.id, ", ".join(reasons))
            message_id = await send_punishment_message(context, chat.id, message_text, reply_markup=InlineKeyboardMarkup(kb_rows))
            if message_id:
                kb_rows = [[InlineKeyboardButton("Admin Approve", callback_data=f"approve_{sender.id}_{chat.id}_{message_id}")]]
                if action == "mute" and bot_username:
                    pm_url = f"https://t.me/{bot_username}?start=unmute_{chat.id}_{sender.id}_{message_id}"
                    kb_rows.insert(0, [InlineKeyboardButton("Unmute via Bot PM", url=pm_url)])
                await send_punishment_message(context, chat.id, message_text, message_id=message_id, reply_markup=InlineKeyboardMarkup(kb_rows))

    muted_mentioned_users = []
    for uname, score, uid in problematic_mentions_list:
        if not uid:
            logger.debug(f"Skipping action for @{uname}: No user ID.")
            continue
        user_id = int(uid)
        if user_id == sender.id and action_taken_on_sender:
            logger.debug(f"Skipping mentioned user {user_id}: Already actioned.")
            continue
        if user_id in settings.get("free_users", set()) or await is_user_exempt_in_group(chat.id, user_id):
            logger.debug(f"Skipping mentioned user @{uname} ({user_id}): Exempt.")
            continue

        # Check if the mentioned user's profile is problematic
        has_issue, field, issue_type = await user_has_links_cached(context, user_id)
        if not has_issue:
            logger.debug(f"Skipping mentioned user @{uname} ({user_id}): No profile issues.")
            continue

        debounce_key = f"punish_notification_{chat.id}_{user_id}_mention"
        if debounce_key in cache:
            logger.debug(f"Debounced action for mentioned user {user_id} in {chat.id}")
            continue

        cache[debounce_key] = True
        duration_seconds = await get_group_punish_duration_for_trigger(chat.id, "mention_profile")
        actual_action = await apply_action(context.bot, chat.id, user_id, "mute", duration_seconds, bot_permissions)
        if actual_action:
            user_html = f"@{uname}"
            try:
                user_obj = await get_chat_with_retry(context.bot, user_id)
                if user_obj:
                    user_html = user_obj.mention_html() if hasattr(user_obj, "mention_html") else f"@{user_obj.username or user_id}"
            except Exception as e:
                logger.debug(f"Failed to get mention for {user_id}: {e}")
            muted_mentioned_users.append(user_html)
            await log_action_db(context, "Mute (Mentioned)", user_id, chat.id, f"Profile issue: {issue_type} in {field}")

    if muted_mentioned_users:
        duration = await get_group_punish_duration_for_trigger(chat.id, "mention_profile")
        message_text = (
            f"Sender {sender_html} mentioned users with problematic profiles "
            f"({', '.join(muted_mentioned_users)}). Muted for {format_duration(duration)}."
        )
        await send_punishment_message(context, chat.id, message_text)
        
async def attempt_unmute_user(
    context: ContextTypes.DEFAULT_TYPE,
    user_id_to_unmute: int,
    chat_id_of_mute: int,
    mute_message_id: Optional[int] = None,
    is_pm_flow: bool = False
) -> Tuple[bool, str]:
    """Attempt to unmute a user after checks."""
    logger.debug(
        f"Unmute attempt for user {user_id_to_unmute} in chat {chat_id_of_mute}. "
        f"PM flow: {is_pm_flow}, Message ID: {mute_message_id}"
    )

    global UNMUTE_RATE_LIMIT_SECONDS
    if UNMUTE_RATE_LIMIT_SECONDS > 0:
        last_attempt_time = await get_last_unmute_attempt_time(user_id_to_unmute, chat_id_of_mute)
        current_time = time.time()
        if last_attempt_time and (current_time - last_attempt_time) < UNMUTE_RATE_LIMIT_SECONDS:
            time_to_wait = int(UNMUTE_RATE_LIMIT_SECONDS - (current_time - last_attempt_time))
            logger.debug(f"Rate limited for {user_id_to_unmute} in {chat_id_of_mute}. Wait {time_to_wait}s.")
            return False, f"rate_limited_{time_to_wait}"

    if not await is_user_subscribed(context, user_id_to_unmute, chat_id_of_mute if is_pm_flow else None):
        logger.debug(f"Unmute failed for {user_id_to_unmute} in {chat_id_of_mute}: Not subscribed.")
        return False, "subscription_required"

    has_issue, field, _ = await user_has_links_cached(context, user_id_to_unmute)
    if has_issue:
        logger.debug(f"Unmute failed for {user_id_to_unmute} in {chat_id_of_mute}: Profile issue in {field}.")
        return False, f"profile_issue_{field or patterns.UNKNOWN_TEXT}"

    try:
        bot_member = await context.bot.get_chat_member(chat_id_of_mute, context.bot.id)
        if not getattr(bot_member, 'can_restrict_members', False):
            logger.warning(f"Bot lacks permission to unmute {user_id_to_unmute} in {chat_id_of_mute}.")
            return False, "bot_no_permission"

        unmute_permissions = ChatPermissions(
            can_send_messages=True, can_send_audios=True, can_send_documents=True,
            can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
            can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
            can_add_web_page_previews=True, can_change_info=True, can_invite_users=True,
            can_pin_messages=True, can_manage_topics=True
        )
        await context.bot.restrict_chat_member(
            chat_id=chat_id_of_mute, user_id=user_id_to_unmute, permissions=unmute_permissions
        )

        cache = context.bot_data.setdefault("notification_debounce_cache", {})
        for key in [
            f"punish_{chat_id_of_mute}_{user_id_to_unmute}",
            f"punish_{chat_id_of_mute}_{user_id_to_unmute}_mention",
            f"unmute_attempt_{user_id_to_unmute}_{chat_id_of_mute}"
        ]:
            cache.pop(key, None)

        logger.info(f"User {user_id_to_unmute} unmuted in {chat_id_of_mute}.")
        return True, "unmute_success"

    except Forbidden as e:
        logger.warning(f"Forbidden to unmute {user_id_to_unmute} in {chat_id_of_mute}: {e}")
        return False, "forbidden"
    except BadRequest as e:
        if "user not found" in str(e).lower() or "member not found" in str(e).lower():
            logger.debug(f"Unmute failed for {user_id_to_unmute} in {chat_id_of_mute}: User not in group.")
            return False, "user_not_in_group"
        logger.warning(f"BadRequest unmuting {user_id_to_unmute} in {chat_id_of_mute}: {e}")
        return False, f"bad_request_{e}"
    except Exception as e:
        logger.error(f"Error unmuting {user_id_to_unmute} in {chat_id_of_mute}: {e}", exc_info=True)
        return False, f"unknown_error_{e}"
        
# --- END ADDITION: attempt_unmute_user function ---


# --- Command Handlers ---

def get_unmute_approve_markup(user_id: int, chat_id: int) -> InlineKeyboardMarkup:
    """Generates InlineKeyboardMarkup for unmute and admin approval."""
    # Add chat_id to callback_data to know which group admin is approving for
    # patterns.UNMUTE_ME_BUTTON_TEXT and patterns.ADMIN_APPROVE_BUTTON_TEXT should be defined in patterns.py
    unmute_button_text = getattr(patterns, 'UNMUTE_ME_BUTTON_TEXT', 'Unmute Me')
    admin_approve_button_text = getattr(patterns, 'ADMIN_APPROVE_BUTTON_TEXT', 'Admin Approve')

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(unmute_button_text, callback_data=f"unmute_{user_id}_{chat_id}")],
        [InlineKeyboardButton(admin_approve_button_text, callback_data=f"approve_{user_id}_{chat_id}")]
    ])

def get_prove_admin_markup(chat_id: int, original_message_id: int) -> InlineKeyboardMarkup:
    """Generates button for anonymous admin to prove their admin status."""
    prove_admin_button_text = getattr(patterns, 'PROVE_ADMIN_BUTTON_TEXT', 'Prove Admin')
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(prove_admin_button_text, callback_data=f"proveadmin_{chat_id}_{original_message_id}")]
    ])

@feature_controlled
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command in PMs and groups with a permanent Unmute Me button."""
    user = update.effective_user
    chat = update.effective_chat
    logger.debug(f"Start command invoked by {user.id} in {chat.id} (type: {chat.type})")
    if not user or not chat:
        logger.warning("Start command received without user or chat.")
        return

    # Update user in DB
    await add_user(
        user.id,
        user.username or "",
        user.first_name or "",
        getattr(user, "last_name", ""),
        has_started_bot=(chat.type == TGChat.PRIVATE)
    )
    if chat.type == TGChat.PRIVATE:
        await mark_user_started_bot(user.id)

    bot_name = await get_bot_username(context) or "BardsSentinelBot"

    # Pattern strings (customizable messages and button texts)
    patterns_dict = {
        "start_msg_base": getattr(patterns, 'START_MESSAGE_PRIVATE_BASE', "Welcome to the bot!"),
        "start_msg_admin_config": getattr(patterns, 'START_MESSAGE_ADMIN_CONFIG', "Configure as admin."),
        "start_msg_channel_verify": getattr(patterns, 'START_MESSAGE_CHANNEL_VERIFY_INFO', "Join our channel for verification."),
        "start_msg_help": getattr(patterns, 'START_MESSAGE_HELP_PROMPT', "Type /help for commands."),
        "help_button": getattr(patterns, 'HELP_BUTTON_TEXT', 'Help'),
        "add_bot_button": getattr(patterns, 'ADD_BOT_TO_GROUP_BUTTON_TEXT', 'Add Bot').format(bot_username=bot_name),
        "join_channel_button": getattr(patterns, 'JOIN_VERIFICATION_CHANNEL_BUTTON_TEXT', 'Join Channel'),
        "verify_button": getattr(patterns, 'VERIFY_JOIN_BUTTON_TEXT', 'Verify Join'),
        "group_start_msg": getattr(patterns, 'START_MESSAGE_GROUP', 'Bot added to group {bot_username}.'),
        "pm_unmute_welcome": getattr(patterns, 'PM_UNMUTE_WELCOME', 'You are muted in {group_names}.'),
        "pm_unmute_subscribe": getattr(patterns, 'PM_UNMUTE_INSTRUCTIONS_SUBSCRIBE', '1. Join our channel: {channel_link}'),
        "pm_unmute_profile": getattr(patterns, 'PM_UNMUTE_INSTRUCTIONS_PROFILE', '2. Remove links from your {field}'),
        "pm_unmute_both": getattr(patterns, 'PM_UNMUTE_INSTRUCTIONS_BOTH', 'To unmute:\n- Join our channel: {channel_link}\n- Remove links from your {field}'),
        "pm_unmute_ready": getattr(patterns, 'PM_UNMUTE_READY_ATTEMPT_BUTTON_TEXT', 'Ready to unmute'),
        "pm_unmute_retry": getattr(patterns, 'PM_UNMUTE_RETRY_BUTTON_TEXT', 'Unmute Me'),
        "payload_error": getattr(patterns, 'PM_UNMUTE_PAYLOAD_ERROR', 'Invalid or expired unmute link. Use the Unmute Me button below.')
    }

    # Check mute status (only in PM for detailed flow, group gets a basic notice)
    muted_groups = await db_fetchall(
        "SELECT DISTINCT group_id FROM bad_actors WHERE user_id = ? AND punishment_type = 'mute' AND (punishment_end > ? OR punishment_end IS NULL)",
        (user.id, int(time.time()))
    )
    muted_groups = [row[0] for row in muted_groups] if muted_groups else []

    # Handle unmute payload (works in both PM and group, typically redirects to PM)
    if context.args and context.args[0].startswith("unmute_"):
        try:
            payload = context.args[0].split("_")
            if len(payload) != 4:
                raise ValueError(f"Invalid payload format: {context.args[0]}")
            unmute_for_group_id, unmute_for_user_id, unmute_message_id = map(int, payload[1:4])

            if user.id != unmute_for_user_id:
                logger.warning(f"User ID mismatch: {user.id} used payload for {unmute_for_user_id} in group {unmute_for_group_id}.")
                await send_message_safe(
                    context, chat.id,
                    patterns_dict["payload_error"],
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(patterns_dict["pm_unmute_retry"], callback_data=f"pmunmute_attempt_{user.id}")]]) if muted_groups else None,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
                return

            logger.info(f"Processing unmute payload for user {user.id} in group {unmute_for_group_id}, message {unmute_message_id}.")
            context.user_data['unmute_group_ids'] = [unmute_for_group_id]
            context.user_data['unmute_message_id'] = unmute_message_id
            await handle_unmute_flow(context, user, muted_groups=[unmute_for_group_id], patterns_dict=patterns_dict)
            return

        except ValueError as e:
            logger.warning(f"Invalid unmute payload: {e}")
            await send_message_safe(
                context, chat.id,
                patterns_dict["payload_error"],
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(patterns_dict["pm_unmute_retry"], callback_data=f"pmunmute_attempt_{user.id}")]]) if muted_groups else None,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            return
        except Exception as e:
            logger.error(f"Error processing unmute payload for user {user.id}: {e}", exc_info=True)
            await send_message_safe(
                context, chat.id,
                patterns_dict["payload_error"],
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(patterns_dict["pm_unmute_retry"], callback_data=f"pmunmute_attempt_{user.id}")]]) if muted_groups else None,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            return

    # Standard /start logic
    message_parts = []
    buttons = []

    if chat.type == TGChat.PRIVATE:
        # Private chat handling
        message_parts.extend([patterns_dict["start_msg_base"], patterns_dict["start_msg_admin_config"]])
        buttons.extend([
            [InlineKeyboardButton(patterns_dict["help_button"], callback_data="show_help")],
            [InlineKeyboardButton(patterns_dict["add_bot_button"], url=f"https://t.me/{bot_name}?startgroup=true")]
        ])

        # Channel subscription check
        channel_id = settings.get("channel_id")
        if channel_id:
            try:
                is_subbed = await is_user_subscribed(context, user.id, chat_id_for_pm_guidance=None)
                channel_link = settings.get("channel_invite_link") or await fetch_channel_link(context, channel_id)
                if is_subbed:
                    message_parts.append(getattr(patterns, 'VERIFICATION_STATUS_VERIFIED', "✅ You are verified."))
                else:
                    if channel_link:
                        message_parts.append(getattr(patterns, 'VERIFICATION_STATUS_NOT_VERIFIED_JOIN', "⚠️ Join our channel: {channel_link}").format(channel_link=channel_link))
                        buttons.insert(0, [InlineKeyboardButton(patterns_dict["join_channel_button"], url=channel_link)])
                    else:
                        message_parts.append(getattr(patterns, 'VERIFICATION_STATUS_NOT_VERIFIED_CLICK_VERIFY', "⚠️ Join our channel and verify."))
                        buttons.insert(0, [InlineKeyboardButton(patterns_dict["verify_button"], callback_data="verify_join_pm")])
                message_parts.append(patterns_dict["start_msg_channel_verify"])
            except telegram.error.RetryAfter as e:
                logger.warning(f"Rate limit hit: Waiting {e.retry_after}s.")
                await asyncio.sleep(e.retry_after)
                message_parts.append(getattr(patterns, 'VERIFICATION_STATUS_NOT_VERIFIED_CLICK_VERIFY', "⚠️ Join our channel and verify."))
                buttons.insert(0, [InlineKeyboardButton(patterns_dict["verify_button"], callback_data="verify_join_pm")])
            except Exception as e:
                logger.error(f"Subscription check failed for {user.id}: {e}")
                message_parts.append(getattr(patterns, 'VERIFICATION_STATUS_NOT_VERIFIED_CLICK_VERIFY', "⚠️ Join our channel and verify."))
                buttons.insert(0, [InlineKeyboardButton(patterns_dict["verify_button"], callback_data="verify_join_pm")])

        # Handle muted users in PM
        if muted_groups:
            context.user_data['unmute_group_ids'] = muted_groups
            await handle_unmute_flow(context, user, muted_groups, patterns_dict)
            return  # Exit after unmute flow to focus user on unmute process

        message_parts.append(patterns_dict["start_msg_help"])
        if muted_groups:  # Persistent Unmute Me button even if not in unmute flow yet
            buttons.append([InlineKeyboardButton(patterns_dict["pm_unmute_retry"], callback_data=f"pmunmute_attempt_{user.id}")])

        await send_message_safe(
            context, user.id,
            "\n\n".join(part for part in message_parts if part),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    else:
        # Group chat handling
        message_parts.append(patterns_dict["group_start_msg"].format(bot_username=bot_name))
        if muted_groups:
            message_parts.append("ℹ️ You are muted in this or other groups. Use /start in PM to unmute.")
            buttons.append([InlineKeyboardButton(patterns_dict["pm_unmute_retry"], url=f"https://t.me/{bot_name}?start")])

        await send_message_safe(
            context, chat.id,
            "\n\n".join(part for part in message_parts if part),
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

    logger.info(f"/start command completed for {user.id} in {chat.id} (type: {chat.type})")

# Helper function to fetch channel link (assumed available or implementable)
async def fetch_channel_link(context, channel_id):
    try:
        channel_chat = await get_chat_with_retry(context.bot, channel_id)
        link = channel_chat.invite_link or (f"https://t.me/{channel_chat.username}" if channel_chat.username else None)
        if link:
            settings["channel_invite_link"] = link
        return link
    except Exception as e:
        logger.error(f"Failed to fetch channel link for {channel_id}: {e}")
        return None
        
async def handle_unmute_flow(context: ContextTypes.DEFAULT_TYPE, user: TGUser, muted_groups: List[int], patterns_dict: Dict[str, str]) -> None:
    """Handle unmute flow for payload or standard /start."""
    try:
        # Get group names
        group_names = []
        for group_id in muted_groups:
            name = await get_chat_name(context, group_id) or f"Group {group_id}"
            group_names.append(name)
        group_names_str = ", ".join(group_names) if group_names else "unknown groups"

        # Check channel subscription
        channel_id = settings.get("channel_id")
        is_subbed = True
        channel_check_needed = bool(channel_id)
        if channel_check_needed:
            try:
                is_subbed = await is_user_subscribed(context, user.id, chat_id_for_pm_guidance=None)
            except telegram.error.RetryAfter as e:
                logger.warning(f"Rate limit hit checking subscription for user {user.id}. Waiting {e.retry_after}s.")
                await asyncio.sleep(e.retry_after)
                is_subbed = await is_user_subscribed(context, user.id, chat_id_for_pm_guidance=None)
            except telegram.error.Forbidden:
                logger.warning(f"Cannot check subscription for user {user.id}: Bot blocked.")
                is_subbed = False

        # Check user profile
        has_profile_issue, problematic_field, _ = await user_has_links_cached(context, user.id)

        # Build message and buttons
        message_parts = [patterns_dict["pm_unmute_welcome"].format(
            user_mention=user.mention_html(),
            group_names=group_names_str
        )]
        buttons = []

        channel_link = settings.get("channel_invite_link")
        if not channel_link and channel_check_needed:
            try:
                channel_chat = await get_chat_with_retry(context.bot, channel_id)
                channel_link = channel_chat.invite_link or (f"https://t.me/{channel_chat.username}" if channel_chat.username else None)
                if channel_link:
                    settings["channel_invite_link"] = channel_link
            except Exception as e:
                logger.warning(f"Failed to fetch channel link for {channel_id}: {e}")
                channel_link = None

        if channel_check_needed and not is_subbed and has_profile_issue:
            message_parts.append(patterns_dict["pm_unmute_both"].format(
                channel_link=channel_link or f"Channel ID: {channel_id}",
                field=problematic_field or "profile"
            ))
            if channel_link:
                buttons.append([InlineKeyboardButton(patterns_dict["join_channel_button"], url=channel_link)])
            buttons.append([InlineKeyboardButton(patterns_dict["verify_button"], callback_data="verify_join_pm")])
            buttons.append([InlineKeyboardButton(patterns_dict["pm_unmute_retry"], callback_data=f"pmunmute_attempt_{user.id}")])
        elif channel_check_needed and not is_subbed:
            message_parts.append(patterns_dict["pm_unmute_subscribe"].format(
                channel_link=channel_link or f"Channel ID: {channel_id}"
            ))
            if channel_link:
                buttons.append([InlineKeyboardButton(patterns_dict["join_channel_button"], url=channel_link)])
            buttons.append([InlineKeyboardButton(patterns_dict["verify_button"], callback_data="verify_join_pm")])
            buttons.append([InlineKeyboardButton(patterns_dict["pm_unmute_retry"], callback_data=f"pmunmute_attempt_{user.id}")])
        elif has_profile_issue:
            message_parts.append(patterns_dict["pm_unmute_profile"].format(field=problematic_field or "profile"))
            buttons.append([InlineKeyboardButton(patterns_dict["pm_unmute_retry"], callback_data=f"pmunmute_attempt_{user.id}")])
        else:
            message_parts.append(patterns_dict["pm_unmute_ready"])
            buttons.append([InlineKeyboardButton(patterns_dict["pm_unmute_ready"], callback_data=f"pmunmute_attempt_{user.id}")])

        await send_message_safe(
            context, user.id,
            "\n".join(message_parts),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        logger.info(f"Sent unmute guidance to user {user.id} for groups {muted_groups}.")
    except Exception as e:
        logger.error(f"Error in unmute flow for user {user.id}: {e}", exc_info=True)
        await send_message_safe(
            context, user.id,
            "An error occurred. Please try again or contact admins.",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

@feature_controlled # Default feature name "help"
async def help_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_name = await get_bot_username(context) or "BardsSentinelBot"
    # Safely access pattern strings for help messages
    help_text_private = getattr(patterns, 'HELP_COMMAND_TEXT_PRIVATE', 'Help for PM').format(bot_username=bot_name)
    help_text_group = getattr(patterns, 'HELP_COMMAND_TEXT_GROUP', 'Help for Group').format(bot_username=bot_name)


    target_chat_id = update.effective_chat.id if update.effective_chat else update.effective_user.id
    user_id = update.effective_user.id if update.effective_user else target_chat_id # Fallback user_id

    if update.effective_chat and update.effective_chat.type == "private":
        await send_message_safe(context, user_id, text=help_text_private, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    else:
        await send_message_safe(context, target_chat_id, text=help_text_group, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    logger.info(f"Help requested by user {user_id} in chat {target_chat_id}")


async def is_user_group_admin_or_creator(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, check_creator_only: bool = False) -> bool:
    """Checks if a user is an admin or creator in a group."""
    if user_id in AUTHORIZED_USERS: return True # Super admins are always effectively group admins
    if chat_id > 0: return False # Not a group/supergroup chat ID

    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if check_creator_only:
            return member.status == ChatMemberStatus.OWNER
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except RetryAfter as e:
        logger.warning(f"Rate limit for get_chat_member in is_user_group_admin ({chat_id}, {user_id}). Retrying after {e.retry_after}s.")
        await asyncio.sleep(e.retry_after)
        return await is_user_group_admin_or_creator(context, chat_id, user_id, check_creator_only) # Retry
    except (BadRequest, Forbidden) as e:
        # User not found in chat, chat not found, bot not admin in chat
        logger.debug(f"Could not determine admin/creator status for user {user_id} in chat {chat_id}: {e}")
        return False
    except Exception as e:
        logger.warning(f"Unexpected error determining admin/creator status for user {user_id} in chat {chat_id}: {e}")
        return False

def parse_duration(duration_str: str) -> int | None: # returns seconds or None
    """Parses a duration string like '30m', '1h', '2d' into seconds."""
    if not duration_str: return None
    ds = duration_str.lower().strip()
    if ds == "0" or ds == getattr(patterns, 'PERMANENT_TEXT', 'permanent').lower(): return 0 # 0 seconds means permanent

    match = re.fullmatch(r"(\d+)([mhd])", ds)
    if not match: return None

    value = int(match.group(1))
    unit = match.group(2)

    if value < 0: # Negative values are invalid
        return None

    if unit == "m": return value * 60
    if unit == "h": return value * 3600
    if unit == "d": return value * 86400
    return None # Should not happen if regex is correct

def format_duration(seconds: int) -> str:
    """Formats a duration in seconds into a human-readable string."""
    if seconds < 0: return getattr(patterns, 'NOT_APPLICABLE', 'N/A') # Should not happen
    if seconds == 0: return getattr(patterns, 'PERMANENT_TEXT', 'permanent')

    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds_rem = divmod(remainder, 60)

    parts = []
    if days > 0: parts.append(f"{days}d")
    if hours > 0: parts.append(f"{hours}h")
    if minutes > 0: parts.append(f"{minutes}m")
    # Only append seconds if there are any remaining and no larger units were added
    if seconds_rem > 0 and not parts: # Corrected condition: Only add seconds if less than a minute total
         parts.append(f"{seconds_rem}s")

    # Fallback for cases where calculation might result in empty string for small seconds
    # e.g. if somehow seconds_rem was 0 but total seconds was > 0 and < 60
    # The original logic handles 0 seconds directly.
    # For seconds between 1 and 59, the initial check handles it.
    return "".join(parts) or f"{seconds}s" # Ensure at least seconds are shown if nothing else


@feature_controlled # setpunish
async def set_punish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat, user = update.effective_chat, update.effective_user
    if not chat or not user or chat.type not in [TGChat.GROUP, TGChat.SUPERGROUP]:
        if chat and chat.type == "private":
            await send_message_safe(context, user.id, getattr(patterns, 'COMMAND_GROUP_ONLY_MESSAGE', 'Group only command').format(command_name="setpunish"), parse_mode=ParseMode.HTML)
        return
    if not await is_user_group_admin_or_creator(context, chat.id, user.id):
        await send_message_safe(context, chat.id, getattr(patterns, 'ADMIN_ONLY_COMMAND_MESSAGE', 'Admin only command'))
        return

    current_action = await get_group_punish_action(chat.id)

    if not context.args:
        # Base punishment options
        mute_button_text = getattr(patterns, 'PUNISH_ACTION_MUTE_BUTTON', 'Mute')
        kick_button_text = getattr(patterns, 'PUNISH_ACTION_KICK_BUTTON', 'Kick')
        ban_button_text = getattr(patterns, 'PUNISH_ACTION_BAN_BUTTON', 'Ban')
        batch_ops_button_text = getattr(patterns, 'PUNISH_BATCH_OPERATIONS_BUTTON', 'Batch Ops')

        kb_buttons = [
            [InlineKeyboardButton(mute_button_text, callback_data=f"setpunishcmd_mute_{chat.id}")],
            [InlineKeyboardButton(kick_button_text, callback_data=f"setpunishcmd_kick_{chat.id}")],
            [InlineKeyboardButton(ban_button_text, callback_data=f"setpunishcmd_ban_{chat.id}")],
        ]
        # Add batch operations if current mode is mute
        if current_action == "mute":
            kb_buttons.append([InlineKeyboardButton(batch_ops_button_text, callback_data=f"setpunishcmd_batchmenu_{chat.id}")])

        prompt_text = getattr(patterns, 'SET_PUNISH_PROMPT', 'Set punish prompt').format(current_action=current_action.capitalize())
        await send_message_safe(context, chat.id, prompt_text, reply_markup=InlineKeyboardMarkup(kb_buttons))
        return

    action_arg = context.args[0].lower()
    if action_arg not in ["mute", "kick", "ban"]:
        await send_message_safe(context, chat.id, getattr(patterns, 'SET_PUNISH_INVALID_ACTION', 'Invalid action {action}').format(action=action_arg))
        return

    # Need group name to pass to set_group_punish_action_async's ON CONFLICT
    group_name = chat.title or f"Group_{chat.id}"
    await set_group_punish_action_async(chat.id, group_name, action_arg)
    await send_message_safe(context, chat.id, getattr(patterns, 'SET_PUNISH_SUCCESS', 'Punish set to {action}').format(action=action_arg))

# Unified /setduration command for all violation types
@feature_controlled("setduration")
async def set_duration_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat, user = update.effective_chat, update.effective_user
    if not chat or not user or chat.type not in [TGChat.GROUP, TGChat.SUPERGROUP]:
        if chat and chat.type == "private": await send_message_safe(context, user.id, getattr(patterns, 'COMMAND_GROUP_ONLY_MESSAGE', 'Group only command').format(command_name="setduration"), parse_mode=ParseMode.HTML)
        return
    if not await is_user_group_admin_or_creator(context, chat.id, user.id):
        await send_message_safe(context, chat.id, getattr(patterns, 'ADMIN_ONLY_COMMAND_MESSAGE', 'Admin only command'))
        return

    # Need group name for DB update
    group_name = chat.title or f"Group_{chat.id}"

    if not context.args:
        # Show current duration for one type as an example (e.g., profile)
        cur_dur_profile_s = await get_group_punish_duration_for_trigger(chat.id, "profile")
        cur_dur_profile_f = format_duration(cur_dur_profile_s)

        # Using patterns for button texts
        min_30_button_text = getattr(patterns, 'DURATION_30M_BUTTON', '30m')
        hr_1_button_text = getattr(patterns, 'DURATION_1H_BUTTON', '1h')
        day_1_button_text = getattr(patterns, 'DURATION_1D_BUTTON', '1d')
        perm_button_text = getattr(patterns, 'DURATION_PERMANENT_BUTTON', 'Permanent')
        custom_button_text = getattr(patterns, 'DURATION_CUSTOM_BUTTON', 'Custom')


        kb_data_prefix = f"setdur_all_{chat.id}" # 'all' signifies it sets for all types
        kb = [
            [InlineKeyboardButton(min_30_button_text, callback_data=f"{kb_data_prefix}_30m"),
             InlineKeyboardButton(hr_1_button_text, callback_data=f"{kb_data_prefix}_1h")],
            [InlineKeyboardButton(day_1_button_text, callback_data=f"{kb_data_prefix}_1d"),
             InlineKeyboardButton(perm_button_text, callback_data=f"{kb_data_prefix}_0")],
            [InlineKeyboardButton(custom_button_text, callback_data=f"{kb_data_prefix}_custom")]
        ]
        prompt_msg = getattr(patterns, 'SET_DURATION_ALL_PROMPT', 'Set duration prompt').format(current_profile_duration=cur_dur_profile_f)
        await send_message_safe(context, chat.id, prompt_msg, reply_markup=InlineKeyboardMarkup(kb))
        return

    duration_str_arg = context.args[0]
    duration_seconds = parse_duration(duration_str_arg)
    if duration_seconds is None:
        await send_message_safe(context, chat.id, getattr(patterns, 'INVALID_DURATION_FORMAT_MESSAGE', 'Invalid duration format {duration_str}').format(duration_str=duration_str_arg))
        return

    await set_all_group_punish_durations_async(chat.id, group_name, duration_seconds)
    success_msg = getattr(patterns, 'SET_DURATION_ALL_SUCCESS', 'Duration set to {duration_formatted}').format(duration_formatted=format_duration(duration_seconds))
    await send_message_safe(context, chat.id, success_msg)


# Generic handler for specific duration commands (/setdurationprofile, /setdurationmessage, /setdurationmention)
async def generic_set_specific_duration_command(update: Update, context: ContextTypes.DEFAULT_TYPE, trigger_type: str, command_name: str):
    chat, user = update.effective_chat, update.effective_user
    if not chat or not user or chat.type not in [TGChat.GROUP, TGChat.SUPERGROUP]:
        if chat and chat.type=="private": await send_message_safe(context, user.id, getattr(patterns, 'COMMAND_GROUP_ONLY_MESSAGE', 'Group only command').format(command_name=command_name), parse_mode=ParseMode.HTML)
        return
    if not await is_user_group_admin_or_creator(context, chat.id, user.id):
        await send_message_safe(context, chat.id, getattr(patterns, 'ADMIN_ONLY_COMMAND_MESSAGE', 'Admin only command'))
        return

    # Need group name for DB update
    group_name = chat.title or f"Group_{chat.id}"

    # Use specific pattern strings, with fallbacks
    prompt_pattern_attr = f"SET_DURATION_{trigger_type.upper()}_PROMPT"
    success_pattern_attr = f"SET_DURATION_{trigger_type.upper()}_SUCCESS"
    prompt_pattern = getattr(patterns, prompt_pattern_attr, getattr(patterns, 'SET_DURATION_GENERIC_PROMPT', 'Set duration prompt for {trigger_type}'))
    success_pattern = getattr(patterns, success_pattern_attr, getattr(patterns, 'SET_DURATION_GENERIC_SUCCESS', 'Duration for {trigger_type} set to {duration_formatted}'))

    if not context.args:
        current_duration_s = await get_group_punish_duration_for_trigger(chat.id, trigger_type)
        current_duration_f = format_duration(current_duration_s)

        # Using patterns for button texts
        min_30_button_text = getattr(patterns, 'DURATION_30M_BUTTON', '30m')
        hr_1_button_text = getattr(patterns, 'DURATION_1H_BUTTON', '1h')
        day_1_button_text = getattr(patterns, 'DURATION_1D_BUTTON', '1d')
        perm_button_text = getattr(patterns, 'DURATION_PERMANENT_BUTTON', 'Permanent')
        custom_button_text = getattr(patterns, 'DURATION_CUSTOM_BUTTON', 'Custom')

        kb_data_prefix = f"setdur_{trigger_type}_{chat.id}" # Specific trigger type
        kb = [
            [InlineKeyboardButton(min_30_button_text, callback_data=f"{kb_data_prefix}_30m"),
             InlineKeyboardButton(hr_1_button_text, callback_data=f"{kb_data_prefix}_1h")],
            [InlineKeyboardButton(day_1_button_text, callback_data=f"{kb_data_prefix}_1d"),
             InlineKeyboardButton(perm_button_text, callback_data=f"{kb_data_prefix}_0")],
            [InlineKeyboardButton(custom_button_text, callback_data=f"{kb_data_prefix}_custom")]
        ]
        prompt_msg = prompt_pattern.format(trigger_type=trigger_type.replace('_', ' '), current_duration=current_duration_f)
        await send_message_safe(context, chat.id, prompt_msg, reply_markup=InlineKeyboardMarkup(kb))
        return

    duration_str_arg = context.args[0]
    duration_seconds = parse_duration(duration_str_arg)
    if duration_seconds is None:
        await send_message_safe(context, chat.id, getattr(patterns, 'INVALID_DURATION_FORMAT_MESSAGE', 'Invalid duration format {duration_str}').format(duration_str=duration_str_arg))
        return

    await set_group_punish_duration_for_trigger_async(chat.id, group_name, trigger_type, duration_seconds)
    success_msg = success_pattern.format(trigger_type=trigger_type.replace('_', ' '), duration_formatted=format_duration(duration_seconds))
    await send_message_safe(context, chat.id, success_msg)

@feature_controlled("setdurationprofile")
async def set_duration_profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await generic_set_specific_duration_command(update, context, "profile", "setdurationprofile")
@feature_controlled("setdurationmessage")
async def set_duration_message_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await generic_set_specific_duration_command(update, context, "message", "setdurationmessage")
@feature_controlled("setdurationmention")
async def set_duration_mention_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await generic_set_specific_duration_command(update, context, "mention_profile", "setdurationmention")


@feature_controlled # freepunish
async def freepunish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat, user = update.effective_chat, update.effective_user
    if not chat or not user or chat.type not in [TGChat.GROUP, TGChat.SUPERGROUP]:
        await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'COMMAND_GROUP_ONLY_MESSAGE', 'Group only command').format(command_name="freepunish"))
        return
    if not await is_user_group_admin_or_creator(context, chat.id, user.id):
        await send_message_safe(context, chat.id, getattr(patterns, 'ADMIN_ONLY_COMMAND_MESSAGE', 'Admin only command'))
        return
    if not context.args:
        await send_message_safe(context, chat.id, getattr(patterns, 'FREEPUNISH_USAGE_MESSAGE', 'Usage: /freepunish [user_id or @username or reply]'))
        return

    target_user_id: Optional[int] = None
    identifier = context.args[0]

    # Handle reply case
    if update.effective_message and update.effective_message.reply_to_message and not context.args:
        target_user = update.effective_message.reply_to_message.from_user
        if target_user:
            target_user_id = target_user.id
    # Handle numeric ID
    elif identifier.isdigit():
        target_user_id = int(identifier)
    # Handle username
    elif identifier.startswith('@'):
        username = identifier[1:]
        # Step 1: Check database
        target_user_id = await get_user_id_from_username(username)
        if not target_user_id:
            # Step 2: Check text_mention entities
            message = update.effective_message
            if message and message.entities:
                for entity in message.entities:
                    if entity.type == "text_mention" and entity.user:
                        if entity.user.username and entity.user.username.lower() == username.lower():
                            target_user_id = entity.user.id
                            break
            # Step 3: If still unresolved, prompt for contact/forwarded message
            if not target_user_id:
                context.user_data['awaiting_contact_for'] = {
                    'command': 'freepunish',
                    'username': username,
                    'chat_id': chat.id
                }
                kb = [[InlineKeyboardButton("Cancel", callback_data="cancel_resolution")]]
                await send_message_safe(context, user.id, f"Could not resolve {identifier}. Please share the user's contact or forward a message from them in this PM.", reply_markup=InlineKeyboardMarkup(kb))
                await send_message_safe(context, chat.id, f"Resolving {identifier}. Please check your PM with the bot.")
                return
    else:
        await send_message_safe(context, chat.id, getattr(patterns, 'INVALID_USER_ID_MESSAGE', 'Invalid user ID'))
        return

    if target_user_id is None:
        await send_message_safe(context, chat.id, getattr(patterns, 'FREEPUNISH_USAGE_MESSAGE', 'Usage: /freepunish [user_id or @username or reply]'))
        return

    await add_group_user_exemption(chat.id, target_user_id)
    await send_message_safe(context, chat.id, getattr(patterns, 'FREEPUNISH_SUCCESS_MESSAGE', 'User {user_id} exempted').format(user_id=target_user_id))

@feature_controlled # unfreepunish
async def unfreepunish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat, user = update.effective_chat, update.effective_user
    if not chat or not user or chat.type not in [TGChat.GROUP, TGChat.SUPERGROUP]:
        await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'COMMAND_GROUP_ONLY_MESSAGE', 'Group only command').format(command_name="unfreepunish"))
        return
    if not await is_user_group_admin_or_creator(context, chat.id, user.id):
        await send_message_safe(context, chat.id, getattr(patterns, 'ADMIN_ONLY_COMMAND_MESSAGE', 'Admin only command'))
        return
    if not context.args:
        await send_message_safe(context, chat.id, getattr(patterns, 'UNFREEPUNISH_USAGE_MESSAGE', 'Usage: /unfreepunish [user_id or reply]'))
        return

    target_user_id: Optional[int] = None
    identifier = context.args[0]

    if update.effective_message and update.effective_message.reply_to_message and not context.args:
         # If no args but it's a reply, target the replied user
         target_user = update.effective_message.reply_to_message.from_user
         if target_user: target_user_id = target_user.id
    elif identifier.startswith('@'):
        target_user_id, _ = await is_real_telegram_user_cached(context, identifier)
        if target_user_id is None:
            await send_message_safe(context, chat.id, getattr(patterns, 'USER_NOT_FOUND_MESSAGE', 'User {identifier} not found').format(identifier=identifier))
            return
    else:
        try: target_user_id = int(identifier)
        except ValueError: await send_message_safe(context, chat.id, getattr(patterns, 'INVALID_USER_ID_MESSAGE', 'Invalid user ID')); return

    if target_user_id is None:
         await send_message_safe(context, chat.id, getattr(patterns, 'UNFREEPUNISH_USAGE_MESSAGE', 'Usage: /unfreepunish [user_id or reply]'))
         return


    await remove_group_user_exemption(chat.id, target_user_id)
    await send_message_safe(context, chat.id, getattr(patterns, 'UNFREEPUNISH_SUCCESS_MESSAGE', 'User {user_id} unexempted').format(user_id=target_user_id))

# --- Super Admin Commands ---
async def _is_super_admin(user_id: int) -> bool:
    return user_id in AUTHORIZED_USERS

@feature_controlled("gfreepunish")
async def gfreepunish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not await _is_super_admin(user.id):
        await send_message_safe(context, update.effective_chat.id, getattr(patterns, 'SUPER_ADMIN_ONLY_COMMAND_MESSAGE', 'Super admin only.'))
        return
    if not context.args:
        await send_message_safe(context, update.effective_chat.id, getattr(patterns, 'GFREEPUNISH_USAGE_MESSAGE', 'Usage: /gfreepunish [user_id]'))
        return
    try:
        target_user_id_str = context.args[0]
        target_user_id: Optional[int] = None
        if target_user_id_str.startswith('@'):
            target_user_id, _ = await is_real_telegram_user_cached(context, target_user_id_str)
            if target_user_id is None:
                await send_message_safe(context, update.effective_chat.id, getattr(patterns, 'USER_NOT_FOUND_MESSAGE', 'User {identifier} not found').format(identifier=target_user_id_str))
                return
        else:
            target_user_id = int(target_user_id_str)

        settings["free_users"].add(target_user_id)
        await send_message_safe(context, update.effective_chat.id, getattr(patterns, 'GFREEPUNISH_SUCCESS_MESSAGE', 'User {user_id} globally exempted').format(user_id=target_user_id))
        logger.info(f"Super admin {user.id} granted global immunity to user {target_user_id}")
    except ValueError:
        await send_message_safe(context, update.effective_chat.id, getattr(patterns, 'INVALID_USER_ID_MESSAGE', 'Invalid user ID'))
    except Exception as e:
         logger.error(f"Error in gfreepunish command for user {user.id}: {e}", exc_info=True)
         await send_message_safe(context, update.effective_chat.id, f"An error occurred: {e}")


@feature_controlled("gunfreepunish")
async def gunfreepunish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not await _is_super_admin(user.id):
        await send_message_safe(context, update.effective_chat.id, getattr(patterns, 'SUPER_ADMIN_ONLY_COMMAND_MESSAGE', 'Super admin only.'))
        return
    if not context.args:
        await send_message_safe(context, update.effective_chat.id, getattr(patterns, 'GUNFREEPUNISH_USAGE_MESSAGE', 'Usage: /gunfreepunish [user_id]'))
        return
    try:
        target_user_id_str = context.args[0]
        target_user_id: Optional[int] = None
        if target_user_id_str.startswith('@'):
            target_user_id, _ = await is_real_telegram_user_cached(context, target_user_id_str)
            if target_user_id is None:
                await send_message_safe(context, update.effective_chat.id, getattr(patterns, 'USER_NOT_FOUND_MESSAGE', 'User {identifier} not found').format(identifier=target_user_id_str))
                return
        else:
            target_user_id = int(target_user_id_str)

        if target_user_id in settings.get("free_users", set()):
            settings["free_users"].remove(target_user_id)
            await send_message_safe(context, update.effective_chat.id, getattr(patterns, 'GUNFREEPUNISH_SUCCESS_MESSAGE', 'User {user_id} global exemption removed').format(user_id=target_user_id))
            logger.info(f"Super admin {user.id} removed global immunity from user {target_user_id}")
        else:
            await send_message_safe(context, update.effective_chat.id, getattr(patterns, 'GUNFREEPUNISH_NOT_IMMUNE_MESSAGE', 'User {user_id} not immune').format(user_id=target_user_id))
    except ValueError:
        await send_message_safe(context, update.effective_chat.id, getattr(patterns, 'INVALID_USER_ID_MESSAGE', 'Invalid user ID'))
    except Exception as e:
        logger.error(f"Error in gunfreepunish command for user {user.id}: {e}", exc_info=True)
        await send_message_safe(context, update.effective_chat.id, f"An error occurred: {e}")


from typing import Optional
from telegram import Update, User as TGUser
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, TelegramError
import logging

logger = logging.getLogger(__name__)

@feature_controlled("clearcache")
async def clear_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not await _is_super_admin(user.id):
        await send_message_safe(context, update.effective_chat.id, getattr(patterns, 'SUPER_ADMIN_ONLY_COMMAND_MESSAGE', 'Super admin only.'))
        return
    pc, uc = (len(user_profile_cache) if user_profile_cache else 0), (len(username_to_id_cache) if username_to_id_cache else 0)
    if user_profile_cache: user_profile_cache.clear()
    if username_to_id_cache: username_to_id_cache.clear()
    await send_message_safe(context, update.effective_chat.id, getattr(patterns, 'CLEAR_CACHE_SUCCESS_MESSAGE', 'Cache cleared').format(profile_cache_count=pc, username_cache_count=uc))
    logger.info(f"Super admin {user.id} cleared caches. Cleared {pc} profile, {uc} username entries.")

@feature_controlled("checkbio")
async def check_bio_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /checkbio command to inspect a user's or bot's bio.
    Updates cache and bad actors table for both problematic and non-problematic users.
    Supports user ID, username (@username), or reply-to message.
    Includes fallback resolution via Telegram link for usernames.
    """
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        logger.warning("check_bio_command missing user or chat.")
        return

    # Validate input
    if not context.args and (not update.effective_message or not update.effective_message.reply_to_message):
        await send_message_safe(
            context, chat.id,
            getattr(patterns, 'CHECKBIO_USAGE_MESSAGE', 'Usage: /checkbio [user_id or @username or reply]'),
            parse_mode=ParseMode.HTML
        )
        return

    target_user_id: Optional[int] = None
    identifier: Optional[str] = None
    target_user_obj: Optional[TGUser] = None

    # Handle input
    if update.effective_message and update.effective_message.reply_to_message and not context.args:
        target_user = update.effective_message.reply_to_message.from_user
        if target_user:
            target_user_id = target_user.id
            identifier = f"Reply to {target_user.id}"
            target_user_obj = target_user
    elif context.args:
        identifier = context.args[0]
        if identifier.startswith('@'):
            # Try standard username resolution first
            user_id, is_real = await is_real_telegram_user_cached(context, identifier)
            if not is_real or user_id is None:
                # Try fallback resolution via Telegram link
                logger.info(f"Attempting fallback resolution for {identifier}")
                user_id = await resolve_username_via_link(identifier)
                if user_id is None:
                    # Cache the failed resolution
                    if identifier.lower().endswith('bot'):
                        context.bot_data.setdefault("username_to_id_cache", {})[identifier.lower()] = {"user_id": None, "is_real": False}
                        logger.debug(f"Cached failed resolution for bot username {identifier}")
                    await send_message_safe(
                        context, chat.id,
                        getattr(patterns, 'USER_NOT_FOUND_MESSAGE', 'User {identifier} not found').format(identifier=identifier),
                        parse_mode=ParseMode.HTML
                    )
                    return
                target_user_id = int(user_id)
            else:
                target_user_id = int(user_id)
            try:
                target_user_obj = await get_chat_with_retry(context.bot, target_user_id)
            except Exception as e:
                logger.debug(f"Failed to fetch user object for {target_user_id} ({identifier}): {e}")
        else:
            try:
                target_user_id = int(identifier)
                try:
                    target_user_obj = await get_chat_with_retry(context.bot, target_user_id)
                except Exception as e:
                    logger.debug(f"Failed to fetch user object for {target_user_id}: {e}")
            except ValueError:
                await send_message_safe(
                    context, chat.id,
                    getattr(patterns, 'INVALID_USER_ID_MESSAGE', 'Invalid user ID'),
                    parse_mode=ParseMode.HTML
                )
                return

    if not target_user_id:
        await send_message_safe(context, chat.id, "Could not determine target user.", parse_mode=ParseMode.HTML)
        return

    # Ensure user object
    if not target_user_obj:
        try:
            target_user_obj = await get_chat_with_retry(context.bot, target_user_id)
            if not target_user_obj:
                # Cache the failed resolution
                context.bot_data.setdefault("username_to_id_cache", {})[identifier.lower() if identifier and identifier.startswith('@') else str(target_user_id)] = {"user_id": None, "is_real": False}
                await send_message_safe(
                    context, chat.id,
                    getattr(patterns, 'USER_NOT_FOUND_MESSAGE', 'User {identifier} not found').format(identifier=identifier or str(target_user_id)),
                    parse_mode=ParseMode.HTML
                )
                return
        except Exception as e:
            logger.error(f"Error fetching user {target_user_id}: {e}", exc_info=True)
            await send_message_safe(
                context, chat.id,
                getattr(patterns, 'CHECKBIO_ERROR_MESSAGE', 'Error checking bio: Could not fetch user details.'),
                parse_mode=ParseMode.HTML
            )
            return

    # Update user in DB (skip self-check)
    if target_user_id != user.id:
        await add_user(
            target_user_id,
            target_user_obj.username or "",
            target_user_obj.first_name or "",
            target_user_obj.last_name or ""
        )

    # Update username_to_id_cache
    if target_user_obj.username:
        context.bot_data.setdefault("username_to_id_cache", {})[f"@{target_user_obj.username.lower()}"] = {
            "user_id": str(target_user_id),
            "is_real": True
        }
        logger.debug(f"Updated username_to_id_cache for @{target_user_obj.username}: {target_user_id}")

    # Check if target is a bot
    is_bot = getattr(target_user_obj, 'is_bot', False) or (target_user_obj.username and target_user_obj.username.lower().endswith('bot'))
    issuer_mention = user.mention_html() if hasattr(user, 'mention_html') else f"@{user.username or user.id}"

    if is_bot:
        logger.info(f"User {user.id} ({issuer_mention}) checked bio for bot {target_user_id}.")
        bio_text = getattr(target_user_obj, 'bio', None) or getattr(target_user_obj, 'description', None) or ""
        username_text = target_user_obj.username or getattr(patterns, 'NOT_APPLICABLE', 'N/A')

        # Update user_profile_cache for bot
        context.bot_data.setdefault("user_profile_cache", {})[str(target_user_id)] = {
            "bio": bio_text,
            "has_issue": True,  # Bots are considered problematic
            "field": "username",
            "issue_type": "bot_account"
        }
        logger.debug(f"Updated user_profile_cache for bot {target_user_id}")

        # Update bad actors table for bot
        await add_bad_actor(
            target_user_id,
            f"Bot account detected via /checkbio (username: {username_text})"
        )
        is_bad = await is_bad_actor(target_user_id)

        result_message = (
            getattr(patterns, 'CHECKBIO_RESULT_HEADER', 'Profile check for {user_id}').format(user_id=target_user_id, username=username_text) +
            f"\nIs a Bot: Yes" +
            (f"\nDescription/Bio: <pre>{bio_text}</pre>" if bio_text else f"\nDescription/Bio: {getattr(patterns, 'BIO_IS_BLANK_MESSAGE', 'Bio is blank.')}")
            + f"\nProblematic: Yes (bot account)" +
            f"\nKnown Bad Actor: {'Yes' if is_bad else 'No'}"
        )

        await send_message_safe(context, chat.id, result_message, parse_mode=ParseMode.HTML)
        # Trigger take_action for bots
        await take_action(update, context, ["bot_account"], "profile_violation", [])
        return

    # Non-bot: Check bio
    bio_text = getattr(target_user_obj, 'bio', None) or ""
    username_text = target_user_obj.username or getattr(patterns, 'NOT_APPLICABLE', 'N/A')
    has_issue, problematic_field, issue_type = await user_has_links_cached(context, target_user_id)

    # Update user_profile_cache
    context.bot_data.setdefault("user_profile_cache", {})[str(target_user_id)] = {
        "bio": bio_text,
        "has_issue": has_issue,
        "field": problematic_field,
        "issue_type": issue_type
    }
    logger.debug(f"Updated user_profile_cache for user {target_user_id}: has_issue={has_issue}")

    # Update bad actors table
    if has_issue:
        await add_bad_actor(
            target_user_id,
            f"Profile issue ({issue_type or patterns.UNKNOWN_TEXT}) in field {problematic_field or patterns.UNKNOWN_TEXT} found via /checkbio."
        )
        logger.info(f"Added {target_user_id} to bad actors: {issue_type} in {problematic_field}")
    else:
        # Mark as safe by removing from bad actors table
        await remove_bad_actor(target_user_id)
        logger.debug(f"Removed {target_user_id} from bad actors table (non-problematic)")

    # Build result message
    is_bad = await is_bad_actor(target_user_id)
    result_message = (
        getattr(patterns, 'CHECKBIO_RESULT_HEADER', 'Profile check for {user_id}').format(user_id=target_user_id, username=username_text) +
        f"\nBio: <pre>{bio_text}</pre>" +
        f"\nProblematic: {'Yes' if has_issue else 'No'}" +
        (getattr(patterns, 'CHECKBIO_RESULT_PROBLEM_DETAILS', '\n  - Issue in <b>{field}</b> ({issue_type})').format(
            field=problematic_field or patterns.UNKNOWN_TEXT,
            issue_type=issue_type or patterns.NOT_APPLICABLE
        ) if has_issue else "") +
        f"\nKnown Bad Actor: {'Yes' if is_bad else 'No'}"
    )

    logger.info(f"User {user.id} ({issuer_mention}) checked bio for user {target_user_id}. Has issue: {has_issue}. Is bad actor: {is_bad}")
    await send_message_safe(context, chat.id, result_message, parse_mode=ParseMode.HTML)

    # Trigger take_action if problematic
    if has_issue:
        reasons = [f"{problematic_field}_{issue_type}"]
        await take_action(update, context, reasons, "profile_violation", [])

@feature_controlled("setchannel")
async def set_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not await _is_super_admin(user.id):
        await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'SUPER_ADMIN_ONLY_COMMAND_MESSAGE', 'Super admin only.'))
        return

    # Clear any pending forward request for this user
    if "awaiting_channel_forward" in context.user_data:
        del context.user_data["awaiting_channel_forward"]
        logger.debug(f"Cleared pending channel forward flag for user {user.id}.")

    if not context.args:
        context.user_data["awaiting_channel_forward"] = True # Set flag for this user
        await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'SET_CHANNEL_PROMPT', 'Set channel prompt'), parse_mode=ParseMode.HTML)
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
        if 'Channel' not in config: config.add_section('Channel')
        config.set('Channel', 'ChannelId', '')
        config.set('Channel', 'ChannelInviteLink', '')
        with open(CONFIG_FILE_NAME, 'w') as configfile:
             config.write(configfile)
        await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'SET_CHANNEL_CLEARED_MESSAGE', 'Channel cleared.'))
        logger.info(f"Verification channel requirement cleared by super admin {user.id}")
        return

    channel_identifier = context.args[0] # Original casing might be needed for usernames
    try:
        logger.info(f"Super admin {user.id} attempting to set verification channel to: {channel_identifier}")
        target_chat_obj = await get_chat_with_retry(context.bot, channel_identifier)

        if not target_chat_obj or target_chat_obj.type != TGChat.CHANNEL:
            error_msg = getattr(patterns, 'SET_CHANNEL_NOT_A_CHANNEL_ERROR', "Not a channel.").format(identifier=channel_identifier, type=target_chat_obj.type if target_chat_obj else 'unknown')
            await send_message_safe(context, chat.id if chat else user.id, error_msg)
            return

        # Check if bot is admin in the target channel
        bot_member = await context.bot.get_chat_member(target_chat_obj.id, context.bot.id)
        if bot_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'SET_CHANNEL_BOT_NOT_ADMIN_ERROR', 'Bot not admin.'))
            logger.warning(f"Bot is not an admin in target channel {target_chat_obj.id} set by admin {user.id}.")
            return

        # Try to get an invite link
        invite_link = getattr(target_chat_obj, 'invite_link', None)
        if not invite_link: # Try to create or export one if bot has permission
            bot_member_perms = getattr(bot_member, 'can_invite_users', False) or getattr(bot_member, 'can_create_invite_links', False) # Check both old and new perms
            if bot_member_perms:
                try:
                    # Prefer creating a new one if permission exists
                    new_link_obj = await context.bot.create_chat_invite_link(target_chat_obj.id, name=f"{target_chat_obj.title or 'Verification'} Link", creates_join_request=False)
                    invite_link = new_link_obj.invite_link
                    logger.info(f"Created new invite link for channel {target_chat_obj.id}.")
                except Exception as e_link_create:
                    logger.warning(f"Could not create invite link for channel {target_chat_obj.id}: {e_link_create}. Trying export.")
                    try: # Fallback to exporting existing primary link
                         invite_link = await context.bot.export_chat_invite_link(target_chat_obj.id)
                         logger.info(f"Exported invite link for channel {target_chat_obj.id}.")
                    except Exception as e_export:
                         logger.warning(f"Could not export invite link for channel {target_chat_obj.id}: {e_export}")
            else:
                 logger.warning(f"Bot lacks permissions to create or export invite links for channel {target_chat_obj.id}.")


        settings["channel_id"] = target_chat_obj.id
        settings["channel_invite_link"] = invite_link # Store even if None, to indicate attempt was made

        # Update config file
        config = configparser.ConfigParser()
        if os.path.exists(CONFIG_FILE_NAME): config.read(CONFIG_FILE_NAME)
        if 'Channel' not in config: config.add_section('Channel')
        config.set('Channel', 'ChannelId', str(target_chat_obj.id))
        config.set('Channel', 'ChannelInviteLink', invite_link or '') # Store empty string if None
        with open(CONFIG_FILE_NAME, 'w') as configfile: config.write(configfile)

        reply_message_text = getattr(patterns, 'SET_CHANNEL_SUCCESS_MESSAGE', 'Channel set.').format(
            channel_title=target_chat_obj.title or target_chat_obj.username or target_chat_obj.id,
            channel_id=target_chat_obj.id
        )
        if invite_link:
            reply_message_text += getattr(patterns, 'SET_CHANNEL_INVITE_LINK_APPEND', '\nLink: {invite_link}').format(invite_link=invite_link)
        else:
            reply_message_text += getattr(patterns, 'SET_CHANNEL_NO_INVITE_LINK_APPEND', '\nNo link.')

        await send_message_safe(context, chat.id if chat else user.id, reply_message_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        logger.info(f"Verification channel set to {target_chat_obj.id} (Invite: {invite_link or 'N/A'}) by super admin {user.id}")

    except BadRequest as e:
        logger.error(f"BadRequest accessing channel '{channel_identifier}' for setchannel: {e}", exc_info=True)
        await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'SET_CHANNEL_BADREQUEST_ERROR', 'BR error.').format(identifier=channel_identifier, error=e))
    except Forbidden as e:
        logger.error(f"Forbidden accessing channel '{channel_identifier}' for setchannel: {e}", exc_info=True)
        await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'SET_CHANNEL_FORBIDDEN_ERROR', 'Forbidden error.').format(identifier=channel_identifier, error=e))
    except Exception as e:
        logger.error(f"Unexpected error setting verification channel to {channel_identifier}: {e}", exc_info=True)
        await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'SET_CHANNEL_UNEXPECTED_ERROR', 'Unexpected error.').format(error=e))

async def handle_forwarded_channel_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message
    chat = update.effective_chat # This is the PM chat with the bot

    # This handler is only for super admins who were prompted by /setchannel
    if not user or not chat or chat.type != TGChat.PRIVATE or not await _is_super_admin(user.id):
        # If a non-super-admin forwards something in PM, or if the flag isn't set
        # and they forward something, just ignore it for this handler.
        # If the flag was set for a non-admin, clear it.
        if context.user_data.get("awaiting_channel_forward"):
             del context.user_data["awaiting_channel_forward"]
             logger.debug(f"Cleared awaiting_channel_forward flag for non-super-admin user {user.id}.")
        return # Ignore if not in PM with super admin and awaiting forward

    # If we are here, it's a super admin in PM, potentially awaiting a forward.
    if not context.user_data.get("awaiting_channel_forward"):
        # Super admin forwarded something in PM, but was not prompted by /setchannel. Ignore for this handler.
        logger.debug(f"Super admin {user.id} forwarded message in PM but was not awaiting channel forward. Skipping handler.")
        return


    # We are a super admin, in PM, and awaiting a channel forward.
    del context.user_data["awaiting_channel_forward"] # Consume the flag

    if message and message.forward_from_chat and message.forward_from_chat.type == TGChat.CHANNEL:
        # Create a pseudo Update object or just call set_channel_command logic with the channel ID
        channel_id_from_forward = message.forward_from_chat.id
        logger.info(f"Super admin {user.id} forwarded message from channel {channel_id_from_forward}.")

        # We need to simulate the context.args for set_channel_command
        context.args = [str(channel_id_from_forward)]

        # Call set_channel_command logic, ensuring it replies to the admin's PM
        # set_channel_command already replies to update.effective_chat, which is correct here (admin's PM)
        await set_channel_command(update, context)

    else:
        await send_message_safe(context, user.id, getattr(patterns, 'SET_CHANNEL_FORWARD_NOT_CHANNEL_ERROR', 'Not forwarded from channel.'))
        logger.warning(f"Super admin {user.id} sent a message in PM but it was not a valid channel forward while awaiting one.")

async def handle_contact_for_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle contact shared in PM for username resolution."""
    if 'awaiting_contact_for' not in context.user_data:
        return
    user = update.effective_user
    contact = update.message.contact

    if not contact or not contact.user_id:
        await send_message_safe(context, user.id, "Invalid contact. Please share a valid contact.")
        return

    command_data = context.user_data['awaiting_contact_for']
    command = command_data['command']
    username = command_data['username']
    chat_id = command_data['chat_id']

    target_user_id = contact.user_id
    # Update database with new mapping
    await add_user(target_user_id, username, contact.first_name or "", contact.last_name or "")

    # Proceed with command
    if command == 'freepunish':
        await add_group_user_exemption(chat_id, target_user_id)
        await send_message_safe(context, chat_id, getattr(patterns, 'FREEPUNISH_SUCCESS_MESSAGE', 'User {user_id} exempted').format(user_id=target_user_id))
    elif command == 'unfreepunish':
        await remove_group_user_exemption(chat_id, target_user_id)
        await send_message_safe(context, chat_id, getattr(patterns, 'UNFREEPUNISH_SUCCESS_MESSAGE', 'User {user_id} unexempted').format(user_id=target_user_id))
    elif command == 'gfreepunish':
        settings["free_users"].add(target_user_id)
        await send_message_safe(context, chat_id, getattr(patterns, 'GFREEPUNISH_SUCCESS_MESSAGE', 'User {user_id} globally exempted').format(user_id=target_user_id))
    elif command == 'gunfreepunish':
        if target_user_id in settings.get("free_users", set()):
            settings["free_users"].remove(target_user_id)
            await send_message_safe(context, chat_id, getattr(patterns, 'GUNFREEPUNISH_SUCCESS_MESSAGE', 'User {user_id} global exemption removed').format(user_id=target_user_id))
        else:
            await send_message_safe(context, chat_id, getattr(patterns, 'GUNFREEPUNISH_NOT_IMMUNE_MESSAGE', 'User {user_id} not immune').format(user_id=target_user_id))
    elif command == 'checkbio':
        pseudo_update = Update(update.update_id, _effective_user=user, _effective_chat=update.effective_chat)
        context.args = [str(target_user_id)]
        await check_bio_command(pseudo_update, context)

    await send_message_safe(context, user.id, f"Resolved @{username} to user ID {target_user_id}.")
    del context.user_data['awaiting_contact_for']

async def handle_forwarded_message_for_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle forwarded message in PM for username resolution."""
    if 'awaiting_contact_for' not in context.user_data:
        return
    user = update.effective_user
    forwarded_from = update.message.forward_from

    if not forwarded_from or not forwarded_from.id:
        await send_message_safe(context, user.id, "Could not determine user from forwarded message. Please forward a message from a user.")
        return

    command_data = context.user_data['awaiting_contact_for']
    command = command_data['command']
    username = command_data['username']
    chat_id = command_data['chat_id']

    target_user_id = forwarded_from.id
    # Update database with new mapping
    await add_user(target_user_id, username, forwarded_from.first_name or "", forwarded_from.last_name or "")

    # Proceed with command
    if command == 'freepunish':
        await add_group_user_exemption(chat_id, target_user_id)
        await send_message_safe(context, chat_id, getattr(patterns, 'FREEPUNISH_SUCCESS_MESSAGE', 'User {user_id} exempted').format(user_id=target_user_id))
    elif command == 'unfreepunish':
        await remove_group_user_exemption(chat_id, target_user_id)
        await send_message_safe(context, chat_id, getattr(patterns, 'UNFREEPUNISH_SUCCESS_MESSAGE', 'User {user_id} unexempted').format(user_id=target_user_id))
    elif command == 'gfreepunish':
        settings["free_users"].add(target_user_id)
        await send_message_safe(context, chat_id, getattr(patterns, 'GFREEPUNISH_SUCCESS_MESSAGE', 'User {user_id} globally exempted').format(user_id=target_user_id))
    elif command == 'gunfreepunish':
        if target_user_id in settings.get("free_users", set()):
            settings["free_users"].remove(target_user_id)
            await send_message_safe(context, chat_id, getattr(patterns, 'GUNFREEPUNISH_SUCCESS_MESSAGE', 'User {user_id} global exemption removed').format(user_id=target_user_id))
        else:
            await send_message_safe(context, chat_id, getattr(patterns, 'GUNFREEPUNISH_NOT_IMMUNE_MESSAGE', 'User {user_id} not immune').format(user_id=target_user_id))
    elif command == 'checkbio':
        pseudo_update = Update(update.update_id, _effective_user=user, _effective_chat=update.effective_chat)
        context.args = [str(target_user_id)]
        await check_bio_command(pseudo_update, context)

    await send_message_safe(context, user.id, f"Resolved @{username} to user ID {target_user_id}.")
    del context.user_data['awaiting_contact_for']

@feature_controlled("stats")
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not await _is_super_admin(user.id):
        await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'SUPER_ADMIN_ONLY_COMMAND_MESSAGE', 'Super admin only.'))
        return

    groups_count = await get_all_groups_count()
    total_users_count = await get_all_users_count(started_only=False)
    started_users_count = await get_all_users_count(started_only=True) # Users who have started the bot

    profile_cache_size = len(user_profile_cache) if user_profile_cache else getattr(patterns, 'NOT_APPLICABLE', 'N/A')
    username_cache_size = len(username_to_id_cache) if username_to_id_cache else getattr(patterns, 'NOT_APPLICABLE', 'N/A')
    globally_free_users_count = len(settings.get("free_users", set()))
    verification_channel_id = str(settings.get("channel_id", getattr(patterns, 'NOT_APPLICABLE', 'N/A')))
    bad_actors_count_row = await db_fetchone("SELECT COUNT(*) AS count FROM bad_actors")
    bad_actors_count = bad_actors_count_row['count'] if bad_actors_count_row and bad_actors_count_row.get('count') is not None else 0

    uptime_seconds = 0
    if hasattr(context.application, 'start_time_epoch'):
        uptime_seconds = int(time.time() - context.application.start_time_epoch)
    uptime_formatted = format_duration(uptime_seconds)

    stats_message = getattr(patterns, 'STATS_COMMAND_MESSAGE', 'Stats').format(
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
        maintenance_mode_status=getattr(patterns, 'ON_TEXT', 'ON') if MAINTENANCE_MODE else getattr(patterns, 'OFF_TEXT', 'OFF')
    )
    await send_message_safe(context, chat.id if chat else user.id, stats_message, parse_mode=ParseMode.HTML)


@feature_controlled("disable")
async def disable_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not await _is_super_admin(user.id):
        await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'SUPER_ADMIN_ONLY_COMMAND_MESSAGE', 'Super admin only.'))
        return
    if not context.args:
        await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'DISABLE_COMMAND_USAGE_MESSAGE', 'Usage: /disable [feature_name]'))
        return

    feature_name_to_disable = context.args[0].lower()
    # Prevent disabling critical commands/features
    critical_features = {"disable", "enable", "maintenance", "start", "help", "stats", "message_processing", "chat_member_processing"} # Add chat_member_processing if used
    if feature_name_to_disable in critical_features:
        await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'DISABLE_COMMAND_CRITICAL_ERROR', 'Cannot disable {feature_name}').format(feature_name=feature_name_to_disable))
        return

    await set_feature_state(feature_name_to_disable, False)
    await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'DISABLE_COMMAND_SUCCESS_MESSAGE', 'Feature {feature_name} disabled').format(feature_name=feature_name_to_disable))
    logger.info(f"Super admin {user.id} disabled feature: {feature_name_to_disable}")

@feature_controlled("enable")
async def enable_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not await _is_super_admin(user.id):
        await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'SUPER_ADMIN_ONLY_COMMAND_MESSAGE', 'Super admin only.'))
        return
    if not context.args:
        await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'ENABLE_COMMAND_USAGE_MESSAGE', 'Usage: /enable [feature_name]'))
        return

    feature_name_to_enable = context.args[0].lower()
    await set_feature_state(feature_name_to_enable, True)
    await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'ENABLE_COMMAND_SUCCESS_MESSAGE', 'Feature {feature_name} enabled').format(feature_name=feature_name_to_enable))
    logger.info(f"Super admin {user.id} enabled feature: {feature_name_to_enable}")

@feature_controlled("maintenance")
async def maintenance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    # MAINTENANCE_MODE global is updated by set_feature_state
    if not user or not await _is_super_admin(user.id):
        await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'SUPER_ADMIN_ONLY_COMMAND_MESSAGE', 'Super admin only.'))
        return

    current_state_str = getattr(patterns, 'ON_TEXT', 'ON') if MAINTENANCE_MODE else getattr(patterns, 'OFF_TEXT', 'OFF')
    if not context.args or context.args[0].lower() not in ["on", "off"]:
        await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'MAINTENANCE_COMMAND_USAGE_MESSAGE', 'Usage: /maintenance [on|off]').format(current_state=current_state_str))
        return

    new_state_str = context.args[0].lower()
    new_state_bool = (new_state_str == "on")

    # Check if state is already as requested
    if MAINTENANCE_MODE == new_state_bool:
         await send_message_safe(context, chat.id if chat else user.id, f"Maintenance mode is already {current_state_str}.")
         return


    await set_feature_state("maintenance_mode_active", new_state_bool) # This will update MAINTENANCE_MODE global
    # MAINTENANCE_MODE is already updated by set_feature_state
    final_state_str = getattr(patterns, 'ENABLED_TEXT', 'enabled').upper() if new_state_bool else getattr(patterns, 'DISABLED_TEXT', 'disabled').upper() # Using different words for clarity
    action_str = 'rests' if new_state_bool else 'resumes its watch'
    await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'MAINTENANCE_COMMAND_SUCCESS_MESSAGE', 'Maintenance mode {state}.').format(state=final_state_str, action=action_str))
    logger.info(f"Super admin {user.id} set maintenance mode to {new_state_str.upper()}.")


# --- Broadcast Logic ---
def _detect_message_format(message_text: str) -> str | None:
    """Detects the probable parse mode (HTML or MarkdownV2) of a message."""
    if not message_text: return None

    # Basic HTML tag detection
    # More robust check including common HTML formatting tags
    html_tags = r"<\/?(?:b|i|u|s|strike|code|pre|a\s+href=)"
    if re.search(html_tags, message_text, re.IGNORECASE):
        return ParseMode.HTML

    # Basic Markdown V2 detection (simplified)
    # Looks for unescaped *, _, ~, `, [text](url), ||spoiler||
    # This is tricky as these characters are common in normal text.
    # A simple approach is to check for presence of *unescaped* control characters
    # or specific patterns like links or spoilers.
    mdv2_chars = r"(?<!\\)[*_~`]|(?<!\\)\|\|.+?(?<!\\)\|\||\[[^\]]+?\]\([^)]+?\)"
    if re.search(mdv2_chars, message_text):
         # If MD chars are present and no clear HTML was detected earlier, lean towards MDV2.
         # MDV2 requires strict escaping, so false positives are possible if user used these chars naturally.
         # HTML detection is often more reliable for user-provided text.
         # Given the potential for false positives with MDV2, prioritizing HTML if any tags are found might be safer.
         if not re.search(html_tags, message_text, re.IGNORECASE): # Only suggest MDV2 if no HTML-like tags found
              return ParseMode.MARKDOWN_V2

    return None # Default to Plain text if no specific formatting detected

async def _send_single_broadcast_message(context: ContextTypes.DEFAULT_TYPE, target_id: int, message_text: str, detected_parse_mode: str | None, reply_markup: Optional[InlineKeyboardMarkup] = None, job_name_for_log: str = "Broadcast") -> bool:
    """Sends a single broadcast message with retries and error handling."""
    if not message_text:
         logger.warning(f"{job_name_for_log}: Attempted to send empty message to {target_id}.")
         return False

    try:
        await context.bot.send_message(chat_id=target_id, text=message_text, parse_mode=detected_parse_mode, disable_web_page_preview=True, reply_markup=reply_markup)
        await asyncio.sleep(BROADCAST_SLEEP_INTERVAL) # Crucial for rate limiting
        return True
    except RetryAfter as e:
        logger.warning(f"{job_name_for_log}: Rate limit hit for {target_id}. Retrying after {e.retry_after}s.")
        await asyncio.sleep(e.retry_after)
        # Retry once more, could be made configurable
        try:
            await context.bot.send_message(chat_id=target_id, text=message_text, parse_mode=detected_parse_mode, disable_web_page_preview=True, reply_markup=reply_markup)
            await asyncio.sleep(BROADCAST_SLEEP_INTERVAL)
            return True
        except Exception as e_retry:
            logger.error(f"{job_name_for_log}: Failed on retry for {target_id}: {e_retry}")
            return False
    except Forbidden:
        logger.warning(f"{job_name_for_log}: Forbidden to send to {target_id}.")
        if target_id < 0 : await remove_group_from_db(target_id) # Remove inactive group
        # Optionally remove user if Forbidden and chat_id > 0 (PM) - be careful with false positives
        # elif target_id > 0: await db_execute("DELETE FROM users WHERE user_id = ?", (target_id,))
    except BadRequest as e:
        # Handle common BadRequest errors more gracefully
        error_msg_lower = str(e).lower()
        if "chat not found" in error_msg_lower or "user is deactivated" in error_msg_lower or "bot was blocked by the user" in error_msg_lower:
            logger.warning(f"{job_name_for_log}: BadRequest (Chat/User not found or blocked) for {target_id}: {e}. Text: {message_text[:50]}")
            if target_id < 0: await remove_group_from_db(target_id)
            # elif target_id > 0: await db_execute("DELETE FROM users WHERE user_id = ?", (target_id,)) # Optionally remove inactive user
        elif "bad request: can't parse" in error_msg_lower:
             logger.warning(f"{job_name_for_log}: BadRequest (Parse error) for {target_id} with parse mode {detected_parse_mode}: {e}. Retrying as plain text.")
             # Retry sending as plain text if parse mode failed
             try:
                 await context.bot.send_message(chat_id=target_id, text=message_text, parse_mode=None, disable_web_page_preview=True, reply_markup=reply_markup)
                 await asyncio.sleep(BROADCAST_SLEEP_INTERVAL)
                 return True
             except Exception as e_plain:
                 logger.error(f"{job_name_for_log}: Failed on plain text retry for {target_id}: {e_plain}")
                 return False
        else:
            logger.warning(f"{job_name_for_log}: BadRequest for {target_id}: {e} (ParseMode: {detected_parse_mode}, Text: {message_text[:100]})")
    except Exception as e:
        logger.error(f"{job_name_for_log}: Unexpected error for {target_id}: {e}", exc_info=True)
    return False

async def _execute_broadcast(context: ContextTypes.DEFAULT_TYPE,
                             message_text: str,
                             target_type: str, # 'all_groups', 'all_users', 'specific_target'
                             reply_markup: Optional[InlineKeyboardMarkup] = None,
                             job_name_for_log: str = "Broadcast",
                             specific_target_id: int | None = None):
    """Internal function to handle the logic of sending broadcasts."""
    detected_format = _detect_message_format(message_text)
    sent_count, failed_count = 0, 0
    target_ids: List[int] = []

    if specific_target_id is not None:
        target_ids = [specific_target_id]
    elif target_type == "all_groups":
        target_ids = await get_all_groups_from_db()
    elif target_type == "all_users":
        target_ids = await get_all_users_from_db(started_only=True) # Only PM users who started the bot
    # Add other target types here if needed (e.g., 'all_groups_and_users')

    if not target_ids:
        logger.info(f"{job_name_for_log}: No targets found for type '{target_type}'.")
        return sent_count, failed_count

    logger.info(f"{job_name_for_log}: Starting broadcast to {len(target_ids)} targets of type '{target_type}' with format '{detected_format or 'Plain Text'}'.")

    for target_id in target_ids:
        # Check SHUTTING_DOWN flag periodically
        if SHUTTING_DOWN:
            logger.warning(f"{job_name_for_log}: Shutting down, stopping broadcast.")
            break

        if await _send_single_broadcast_message(context, target_id, message_text, detected_format, reply_markup=reply_markup, job_name_for_log=job_name_for_log):
            sent_count += 1
        else:
            failed_count += 1
        # Log progress more frequently for large broadcasts
        if (sent_count + failed_count) > 0 and (sent_count + failed_count) % 50 == 0:
            logger.info(f"{job_name_for_log}: Progress - Processed: {sent_count + failed_count}/{len(target_ids)}, Sent: {sent_count}, Failed: {failed_count}")


    logger.info(f"{job_name_for_log}: Broadcast to type '{target_type}' complete. Sent: {sent_count}, Failed: {failed_count}.")
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
    reply_markup_json = job_data.get("markup") # Get markup if stored as JSON <-- MODIFIED

    if not target_type or not message_text:
        logger.error(f"Timed broadcast job '{job_name}' is missing target_type or message_text in job.data. Removing job.")
        # Remove this faulty job
        running_jobs = context.job_queue.get_jobs_by_name(job_name)
        for r_job in running_jobs: r_job.schedule_removal()
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


    sent, failed = await _execute_broadcast(context, message_text, target_type, reply_markup=reply_markup, job_name_for_log=f"TimedBroadcast-{job_name}")
    logger.info(f"Timed broadcast job {job_name} finished. Sent: {sent}, Failed: {failed}")

    # The JobQueue automatically schedules the next run based on the interval.
    # We don't need to manually update next_run_time in DB for repeating jobs if JobQueue persists state (default).
    # However, if JobQueue state is NOT persisted across restarts, the DB store is crucial.
    # The initial `load_and_schedule_timed_broadcasts` uses the DB time.
    # For robustness, we could update the DB with the *actual* next scheduled time after each run,
    # but JobQueue's built-in persistence or recalculation on load is usually sufficient.

# --- Broadcast Commands ---
@feature_controlled("broadcast") # Super admin command
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat # Command sender chat
    if not user or not chat or not await _is_super_admin(user.id):
        await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'SUPER_ADMIN_ONLY_COMMAND_MESSAGE', 'Super admin only.'))
        return

    args = context.args
    # Expected formats:
    # /broadcast <message> (to all groups, no interval)
    # /broadcast [target_id] <message> (to specific group/user, no interval)
    # /broadcast [interval (e.g., 30m, 2h, 1d)] <message> (to all groups, repeating)
    # /broadcast [interval (e.g., 30m, 2h, 1d)] [target_id] <message> (NOT supported by this logic)

    if not args:
        await send_message_safe(context, chat.id, getattr(patterns, 'BROADCAST_USAGE_MESSAGE', 'Broadcast usage.'))
        return

    time_interval_str: Optional[str] = None
    target_id_input: Optional[str] = None
    message_start_index = 0

    # Check for time interval (e.g., "3h", "30m") as the first argument
    if len(args) > 0 and parse_duration(args[0]) is not None and parse_duration(args[0]) != 0: # 0 duration implies immediate, not repeating
        time_interval_str = args[0]
        message_start_index = 1
        if len(args) == 1: # Only interval given
             await send_message_safe(context, chat.id, "Please provide a message for the timed broadcast.")
             return


    # Check for target_id if it's the next argument (only if interval wasn't the first arg or was).
    # Note: Original logic didn't support timed broadcasts to specific IDs via /broadcast, maintaining that.
    # If time_interval_str is None, check if args[0] is a target_id.
    # If time_interval_str is present, check if args[1] is a target_id.
    potential_target_idx = 0 if time_interval_str is None else 1

    if len(args) > potential_target_idx and args[potential_target_idx].lstrip('-').isdigit():
         target_id_input = args[potential_target_idx]
         message_start_index = potential_target_idx + 1
         # If an interval was also provided, this format (interval + target_id) is not supported by this command.
         if time_interval_str:
             await send_message_safe(context, chat.id, "Timed broadcasts with a specific target ID are not supported via /broadcast. Use /bcastall or /bcastself for timed global broadcasts, or omit target_id for timed group broadcast.")
             return


    message_text = " ".join(args[message_start_index:])
    if not message_text:
        await send_message_safe(context, chat.id, getattr(patterns, 'BROADCAST_NO_MESSAGE_ERROR', 'No message provided.'))
        return

    interval_seconds: Optional[int] = None
    if time_interval_str:
        interval_seconds = parse_duration(time_interval_str)
        # We already checked for 0 duration earlier, this check confirms it's a valid positive interval
        if interval_seconds is None or interval_seconds <= 0:
             await send_message_safe(context, chat.id, f"Invalid time interval '{time_interval_str}'. Must be positive like 30m, 2h, 1d.")
             return


    job_name = f"manual_broadcast_{int(time.time())}" # Unique job name using timestamp


    if interval_seconds: # Timed broadcast (only to all groups for this command)
        target_type_for_timed = "all_groups"
        # target_id_input is checked above to ensure it's not present with interval
        if context.job_queue:
            job_data = {"target_type": target_type_for_timed, "message_text": message_text}
            context.job_queue.run_repeating(timed_broadcast_job_callback, interval=interval_seconds, first=0, data=job_data, name=job_name)
            await add_timed_broadcast_to_db(job_name, target_type_for_timed, message_text, interval_seconds, time.time())
            settings["active_timed_broadcasts"][job_name] = True
            await send_message_safe(context, chat.id,
                                    f"Scheduled timed broadcast to all groups every {format_duration(interval_seconds)}. Job name: <code>{job_name}</code>\nMessage: {message_text[:100]}...",
                                    parse_mode=ParseMode.HTML)
        else:
            await send_message_safe(context, chat.id, "JobQueue not available. Timed broadcast cannot be scheduled.")
        return

    # --- Immediate Broadcast ---
    await send_message_safe(context, chat.id, getattr(patterns, 'BROADCAST_STARTED_MESSAGE', 'Broadcast started.').format(format=(_detect_message_format(message_text) or "Plain Text")))

    specific_target_id_int: Optional[int] = None
    broadcast_target_type = "all_groups" # Default target for immediate /broadcast

    if target_id_input:
        try:
            specific_target_id_int = int(target_id_input)
            broadcast_target_type = "specific_target"
        except ValueError:
             await send_message_safe(context, chat.id, f"Invalid target_id: {target_id_input}")
             return

    sent, failed = await _execute_broadcast(context, message_text, broadcast_target_type, specific_target_id=specific_target_id_int, job_name_for_log="Broadcast")
    await send_message_safe(context, chat.id, getattr(patterns, 'BROADCAST_COMPLETE_MESSAGE', 'Broadcast complete.').format(sent_count=sent, failed_count=failed))


@feature_controlled("bcastall") # Super admin command
async def bcastall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat or not await _is_super_admin(user.id):
        await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'SUPER_ADMIN_ONLY_COMMAND_MESSAGE', 'Super admin only.'))
        return

    args = context.args
    time_interval_str: Optional[str] = None
    message_start_index = 0

    if args and parse_duration(args[0]) is not None and parse_duration(args[0]) != 0:
        time_interval_str = args[0]
        message_start_index = 1
        if len(args) == 1: # Only time given
             await send_message_safe(context, chat.id, "Please provide a message for the timed universal broadcast."); return


    message_text = " ".join(args[message_start_index:])
    if not message_text:
        await send_message_safe(context, chat.id, getattr(patterns, 'BCASTALL_USAGE_MESSAGE', 'Bcastall usage.')); return


    interval_seconds: Optional[int] = None
    if time_interval_str:
        interval_seconds = parse_duration(time_interval_str)
        if interval_seconds is None or interval_seconds <=0:
            await send_message_safe(context, chat.id, f"Invalid time interval '{time_interval_str}'. Must be positive like 30m, 2h, 1d."); return

    job_name_base = "bcastall"
    job_name_timestamp = int(time.time()) # Use a single timestamp for related jobs

    if interval_seconds: # Timed universal broadcast (groups and users)
        if context.job_queue:
            # Schedule job for all groups
            group_job_name = f"{job_name_base}_groups_{job_name_timestamp}"
            job_data_groups = {"target_type": "all_groups", "message_text": message_text}
            context.job_queue.run_repeating(timed_broadcast_job_callback, interval=interval_seconds, first=0, data=job_data_groups, name=group_job_name)
            await add_timed_broadcast_to_db(group_job_name, "all_groups", message_text, interval_seconds, time.time())
            settings["active_timed_broadcasts"][group_job_name] = True

            # Schedule job for all users (PMs)
            user_job_name = f"{job_name_base}_users_{job_name_timestamp}"
            job_data_users = {"target_type": "all_users", "message_text": message_text}
            # Stagger user broadcast slightly to avoid hitting API limits simultaneously with group broadcast
            user_first_run_delay = interval_seconds / 2 if interval_seconds > 10 else 5 # Delay by half interval or 5s, whichever is less (min 5s)
            context.job_queue.run_repeating(timed_broadcast_job_callback, interval=interval_seconds, first=user_first_run_delay, data=job_data_users, name=user_job_name)
            await add_timed_broadcast_to_db(user_job_name, "all_users", message_text, interval_seconds, time.time() + user_first_run_delay)
            settings["active_timed_broadcasts"][user_job_name] = True

            await send_message_safe(context, chat.id,
                                    f"Scheduled universal timed broadcast (groups and users) every {format_duration(interval_seconds)}.\nGroup Job: <code>{group_job_name}</code>, User Job: <code>{user_job_name}</code>\nMessage: {message_text[:100]}...",
                                    parse_mode=ParseMode.HTML)
        else:
            await send_message_safe(context, chat.id, "JobQueue not available. Timed universal broadcast cannot be scheduled.")
        return

    # Immediate bcastall
    await send_message_safe(context, chat.id, getattr(patterns, 'BCASTALL_STARTED_MESSAGE', 'Bcastall started.').format(format=(_detect_message_format(message_text) or "Plain Text")))
    sent_g, failed_g = await _execute_broadcast(context, message_text, "all_groups", job_name_for_log="BcastAll-Groups")
    sent_u, failed_u = await _execute_broadcast(context, message_text, "all_users", job_name_for_log="BcastAll-Users") # users who started bot

    await send_message_safe(context, chat.id,
                            getattr(patterns, 'BCASTALL_COMPLETE_MESSAGE', 'Bcastall complete.').format(sent_groups=sent_g, failed_groups=failed_g, sent_users=sent_u, failed_users=failed_u))


@feature_controlled("bcastself") # Super admin command
async def bcastself_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat or not await _is_super_admin(user.id):
        await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'SUPER_ADMIN_ONLY_COMMAND_MESSAGE', 'Super admin only.'))
        return

    args = context.args
    time_interval_str: Optional[str] = None
    if args and parse_duration(args[0]) is not None and parse_duration(args[0]) != 0: # Optional time interval
        time_interval_str = args[0]
        if len(args) > 1:
             await send_message_safe(context, chat.id, f"Usage: <code>/bcastself [interval]</code>. Message text is fixed. Extra arguments ignored.")
             return # Ignore extra args after interval

    bot_name = await get_bot_username(context) or "BardsSentinelBot"
    self_promo_message = getattr(patterns, 'BCASTSELF_MESSAGE_TEMPLATE', 'Self promo. Add me: t.me/{bot_username}?startgroup=true').format(bot_username=bot_name)
    # Add button to message
    add_bot_button_text = getattr(patterns, 'ADD_BOT_TO_GROUP_BUTTON_TEXT', 'Add Bot').format(bot_username=bot_name)
    add_bot_button = InlineKeyboardButton(add_bot_button_text, url=f"https://t.me/{bot_name}?startgroup=true")
    markup = InlineKeyboardMarkup([[add_bot_button]])


    interval_seconds: Optional[int] = None
    if time_interval_str:
        interval_seconds = parse_duration(time_interval_str)
        if interval_seconds is None or interval_seconds <=0:
            await send_message_safe(context, chat.id, f"Invalid time interval '{time_interval_str}'. Must be positive like 30m, 2h, 1d. Or omit for one-time broadcast."); return

    job_name_base = "bcastself"
    job_name = f"{job_name_base}_{int(time.time())}" # Unique job name


    if interval_seconds: # Timed self-promo broadcast to all users who started PM
        if context.job_queue:
            job_data = {"target_type": "all_users", "message_text": self_promo_message, "markup": markup.to_json()} # Pass markup as JSON
            context.job_queue.run_repeating(timed_broadcast_job_callback, interval=interval_seconds, first=0, data=job_data, name=job_name)
            # Store markup json in DB for persistence
            await add_timed_broadcast_to_db(job_name, "all_users", self_promo_message, interval_seconds, time.time()) # DB does not store markup currently
            # Need to update DB schema for timed_broadcasts table to store markup JSON if needed for persistence
            # For now, markup persistence for timed jobs is not implemented in DB functions.
            settings["active_timed_broadcasts"][job_name] = True
            await send_message_safe(context, chat.id,
                                    f"Scheduled self-promotion broadcast to all users (who started PM) every {format_duration(interval_seconds)}. Job: <code>{job_name}</code>",
                                    parse_mode=ParseMode.HTML)
        else:
            await send_message_safe(context, chat.id, "JobQueue not available. Timed self-promo cannot be scheduled.")
        return

    # Immediate self-promo broadcast
    await send_message_safe(context, chat.id, getattr(patterns, 'BCASTSELF_STARTED_MESSAGE', 'Bcastself started.'))
    # Target users who have started a PM with the bot.
    # For sending with markup, we need to call _execute_broadcast with the markup.
    sent, failed = await _execute_broadcast(context, self_promo_message, "all_users", reply_markup=markup, job_name_for_log="BcastSelf")

    await send_message_safe(context, chat.id, getattr(patterns, 'BCASTSELF_COMPLETE_MESSAGE', 'Bcastself complete.').format(sent_count=sent, failed_count=failed))


@feature_controlled("stopbroadcast") # Super admin command
async def stop_broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat or not await _is_super_admin(user.id):
        await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'SUPER_ADMIN_ONLY_COMMAND_MESSAGE', 'Super admin only.'))
        return

    if not context.args:
        active_jobs_list = list(settings["active_timed_broadcasts"].keys())
        active_jobs_str = "\n".join(f"• <code>{job_name}</code>" for job_name in active_jobs_list) if active_jobs_list else getattr(patterns, 'NOT_APPLICABLE', 'N/A')
        await send_message_safe(context, chat.id,
                                getattr(patterns, 'STOP_BROADCAST_USAGE', 'Stop broadcast usage.').format(job_name='<job_name>') + f"\nActive timed broadcasts:\n{active_jobs_str}",
                                parse_mode=ParseMode.HTML)
        return

    job_name_to_stop = context.args[0]
    if context.job_queue:
        jobs = context.job_queue.get_jobs_by_name(job_name_to_stop)
        if jobs:
            for job in jobs:
                job.schedule_removal()
                logger.info(f"Super admin {user.id} scheduled removal for job {job_name_to_stop}.")

            if job_name_to_stop in settings["active_timed_broadcasts"]:
                del settings["active_timed_broadcasts"][job_name_to_stop]
                logger.debug(f"Removed job {job_name_to_stop} from active_timed_broadcasts settings.")

            await remove_timed_broadcast_from_db(job_name_to_stop) # Remove from DB persistence
            await send_message_safe(context, chat.id, getattr(patterns, 'STOP_BROADCAST_SUCCESS', 'Job {job_name} stopped.').format(job_name=job_name_to_stop))
            logger.info(f"Super admin {user.id} stopped and removed timed broadcast '{job_name_to_stop}'.")
        else:
            await send_message_safe(context, chat.id, getattr(patterns, 'STOP_BROADCAST_NOT_FOUND', 'Job {job_name} not found.').format(job_name=job_name_to_stop))
            logger.warning(f"Super admin {user.id} tried to stop non-existent job '{job_name_to_stop}'.")
    else:
        await send_message_safe(context, chat.id, "JobQueue not available. Cannot stop timed broadcasts.")
        logger.error("JobQueue not available in stop_broadcast_command.")


# Helper for unmuteall commands
async def _perform_unmute_all_operation(context: ContextTypes.DEFAULT_TYPE, target_chat_id: int, user_ids_to_process: List[int], operation_name: str, admin_user_id: int):
    """Attempts to unmute a list of users in a specific chat.
       Args:
           context: The context object.
           target_chat_id: The ID of the chat to perform the operation in.
           user_ids_to_process: A list of user IDs to attempt to unmute.
           operation_name: A string name for logging (e.g., "UnmuteAll", "GlobalUnmuteAll-GroupX").
           admin_user_id: The user ID of the admin who initiated the operation. <-- ADDED argument
    """
    unmuted_count = 0
    failed_count = 0
    not_in_group_count = 0 # Counter for users explicitly identified as not in the group
    # Define standard unmute permissions (allow sending messages, media, etc.)
    unmute_permissions = ChatPermissions(
        can_send_messages=True, can_send_audios=True, can_send_documents=True,
        can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
        can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True, # Simplified basic perms
        can_add_web_page_previews=True,
        # Do not change 
        can_change_info=True, can_invite_users=True, can_pin_messages=True, can_manage_topics=True
    )

    # Check bot's permissions once before starting the loop
    bot_has_restrict_permission = False
    try:
        bot_member = await context.bot.get_chat_member(target_chat_id, context.bot.id)
        bot_has_restrict_permission = getattr(bot_member, 'can_restrict_members', False)
        if not bot_has_restrict_permission:
             logger.warning(f"{operation_name}: Bot lacks 'can_restrict_members' permission in chat {target_chat_id}. Unmuting will likely fail.")
             # Notify the admin who initiated the command directly <-- ADDED
             await send_message_safe(context, admin_user_id, f"Warning: Cannot perform batch unmute in group {target_chat_id}. I lack 'Restrict Members' permission.")

    except Exception as e:
        logger.error(f"{operation_name}: Could not get bot permissions in chat {target_chat_id}: {e}. Proceeding but expecting failures.")
        # Assume no necessary permissions if check fails

    if not bot_has_restrict_permission:
         # No permission, cannot proceed with unmuting.
         # Return counts. The warning has been sent to the admin.
         return 0, len(user_ids_to_process), 0 # Report all as failed attempts due to permission


    for i, user_id_to_unmute in enumerate(user_ids_to_process): # Added index i for progress logging
        # Check SHUTTING_DOWN flag
        if SHUTTING_DOWN:
            logger.warning(f"{operation_name}: Shutting down, stopping unmute operations.")
            break

        try:
            # Attempt to restrict with permissions that allow sending
            await context.bot.restrict_chat_member(
                chat_id=target_chat_id, user_id=user_id_to_unmute, permissions=unmute_permissions
            )
            unmuted_count += 1
        except Forbidden:
            # This might happen if the bot is removed during the operation, or user blocked the bot.
            logger.debug(f"{operation_name}: Forbidden attempting to unmute {user_id_to_unmute} in {target_chat_id}.")
            failed_count += 1 # Count as failed from bot's perspective
        except BadRequest as e:
            error_msg_lower = str(e).lower()
            if "user not found" in error_msg_lower or "member not found" in error_msg_lower or "user_is_not_a_participant" in error_msg_lower or "participant_id_invalid" in error_msg_lower: # Added participant_id_invalid check
                not_in_group_count += 1 # User explicitly identified as not in the group
                logger.debug(f"{operation_name}: User {user_id_to_unmute} not found in group {target_chat_id}.")
            else:
                # Log other types of BadRequest errors as warnings
                logger.warning(f"{operation_name}: Could not unmute {user_id_to_unmute} in {target_chat_id} (BadRequest: {e}).")
                failed_count += 1
        except Exception as e:
            # Catch TimedOut, NetworkError, or other unexpected exceptions during the API call
            logger.error(f"{operation_name}: Unexpected error unmuting {user_id_to_unmute} in {target_chat_id}: {e}", exc_info=True)
            failed_count += 1 # Count as failed
        # Add a short delay between API calls to respect rate limits
        await asyncio.sleep(BROADCAST_SLEEP_INTERVAL)

    return unmuted_count, failed_count, not_in_group_count

@feature_controlled("unmuteall") # Super admin command
async def unmuteall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat or not await _is_super_admin(user.id):
        await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'SUPER_ADMIN_ONLY_COMMAND_MESSAGE', 'Super admin only.'))
        return
    if not context.args or len(context.args) != 1:
        await send_message_safe(context, chat.id, getattr(patterns, 'UNMUTEALL_USAGE_MESSAGE', 'Unmuteall usage.'), parse_mode=ParseMode.HTML); return
    try:
        target_group_id = int(context.args[0])
        if target_group_id >= 0:
             await send_message_safe(context, chat.id, getattr(patterns, 'UNMUTEALL_INVALID_GROUP_ID', 'Invalid group ID. Please provide a negative group chat ID.'), parse_mode=ParseMode.HTML); return
    except ValueError: await send_message_safe(context, chat.id, getattr(patterns, 'UNMUTEALL_INVALID_GROUP_ID', 'Invalid group ID. Please provide a negative group chat ID.'), parse_mode=ParseMode.HTML); return

    await send_message_safe(context, chat.id, getattr(patterns, 'UNMUTEALL_STARTED_MESSAGE', 'Unmuteall started.').format(group_id=target_group_id))
    # Get all users bot knows about. This might be a very large list.
    all_known_user_ids_in_db = await get_all_users_from_db()
    if not all_known_user_ids_in_db:
        await send_message_safe(context, chat.id, getattr(patterns, 'GUNMUTEALL_NO_DATA_MESSAGE', 'No data for gunmuteall.').replace("gunmuteall", "unmuteall")); return

    # Execute the unmute operation, passing the admin's user ID <-- MODIFIED
    unmuted, failed, not_in_group = await _perform_unmute_all_operation(context, target_group_id, all_known_user_ids_in_db, "UnmuteAll", user.id)

    await send_message_safe(context, chat.id,
        getattr(patterns, 'UNMUTEALL_COMPLETE_MESSAGE', 'Unmuteall complete.').format(group_id=target_group_id, unmuted_count=unmuted, failed_count=failed, not_in_group_count=not_in_group))


@feature_controlled("gunmuteall") # Super admin command
async def gunmuteall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat or not await _is_super_admin(user.id):
        await send_message_safe(context, chat.id if chat else user.id, getattr(patterns, 'SUPER_ADMIN_ONLY_COMMAND_MESSAGE', 'Super admin only.'))
        return

    await send_message_safe(context, chat.id, getattr(patterns, 'GUNMUTEALL_STARTED_MESSAGE', 'Gunmuteall started.'))
    all_group_ids_in_db = await get_all_groups_from_db()
    all_user_ids_in_db = await get_all_users_from_db() # Get all users bot knows

    if not all_group_ids_in_db or not all_user_ids_in_db:
        await send_message_safe(context, chat.id, getattr(patterns, 'GUNMUTEALL_NO_DATA_MESSAGE', 'No data for gunmuteall.')); return

    total_ops_unmuted, total_ops_failed, total_ops_not_in_group = 0, 0, 0
    processed_groups = 0
    total_groups = len(all_group_ids_in_db)

    for group_id in all_group_ids_in_db:
        logger.info(f"GlobalUnmuteAll: Processing group {group_id} ({processed_groups + 1}/{total_groups})...")
        # Perform unmute for all known users within this group, passing admin ID <-- MODIFIED
        unmuted, failed, not_in_group = await _perform_unmute_all_operation(context, group_id, all_user_ids_in_db, f"GlobalUnmuteAll-Group{group_id}", user.id)

        total_ops_unmuted += unmuted
        total_ops_failed += failed
        # not_in_group count is per group, summing it up might be misleading, but we can keep it for general stats
        # total_ops_not_in_group += not_in_group # Keep track of users not found across all groups

        processed_groups += 1
        if processed_groups % 10 == 0 or processed_groups == total_groups: # Log progress
             await send_message_safe(context, chat.id, f"Global Unmute All progress: Processed {processed_groups}/{total_groups} groups. Currently {total_ops_unmuted} successful ops.")


    await send_message_safe(context, chat.id,
        getattr(patterns, 'GUNMUTEALL_COMPLETE_MESSAGE', 'Gunmuteall complete.').format(
            groups_count=total_groups,
            users_per_group_approx=len(all_user_ids_in_db), # Approx, as not all users in all groups
            total_unmuted_ops=total_ops_unmuted,
            total_failed_ops=total_ops_failed # This includes users not found in a specific group for simplicity in total failed ops
        ))
@feature_controlled("checkallbios")
async def check_all_bios_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not await _is_super_admin(user.id):
        await send_message_safe(context, chat.id if chat else user.id, "Super admin only command.")
        return

    if not context.args:
        await send_message_safe(context, chat.id, "Usage: /checkallbios <group_id>")
        return

    try:
        group_id = int(context.args[0])
    except ValueError:
        await send_message_safe(context, chat.id, "Invalid group ID.")
        return

    group = await db_fetchone("SELECT * FROM groups WHERE group_id = ?", (group_id,))
    if not group:
        await send_message_safe(context, chat.id, f"Group {group_id} not found in database.")
        return

    await send_message_safe(context, chat.id, f"Starting bio check for all members in group {group_id}...")

    members = []
    try:
        # Try fetching group admins first (as a reliable source)
        admins = await context.bot.get_chat_administrators(chat_id=group_id)
        members.extend([admin.user for admin in admins if not admin.user.is_bot])
        
        # Optionally, fetch known users from the database (if you track group members)
        # Note: This assumes you have a table linking users to groups
        user_ids = await db_fetchall(
            "SELECT user_id FROM bad_actors WHERE group_id = ? UNION SELECT user_id FROM users",
            (group_id,)
        )
        user_ids = [row[0] for row in user_ids]

        # Check each user to confirm membership
        for user_id in user_ids:
            try:
                member = await context.bot.get_chat_member(chat_id=group_id, user_id=user_id)
                if member.status in ["member", "administrator", "creator"] and not member.user.is_bot:
                    if member.user not in members:  # Avoid duplicates
                        members.append(member.user)
            except BadRequest:  # User not in group or other error
                continue
    except Exception as e:
        logger.error(f"Error fetching members for group {group_id}: {e}")
        await send_message_safe(context, chat.id, f"Error fetching members for group {group_id}: {e}")
        return

    if not members:
        await send_message_safe(context, chat.id, f"No members found in group {group_id}.")
        return

    issue_count = 0
    for member in members:
        try:
            has_issue, field, issue_type = await user_has_links_cached(context, member.id)
            if has_issue:
                reason = f"Profile issue: {issue_type} in {field}"
                # Create pseudo update
                pseudo_update = Update(
                    update_id=update.update_id + 1,  # Increment to avoid conflicts
                    effective_chat=await context.bot.get_chat(group_id),
                    effective_user=member
                )
                await take_action(pseudo_update, context, [reason], "profile", [])
                issue_count += 1
            await asyncio.sleep(0.1)  # Avoid rate limits
        except Exception as e:
            logger.error(f"Error processing user {member.id} in group {group_id}: {e}")
            continue

    await send_message_safe(
        context,
        chat.id,
        f"Completed bio check for group {group_id}. Found {issue_count} issue{'s' if issue_count != 1 else ''}."
    )
    
async def _batch_action_on_muted_users(context: ContextTypes.DEFAULT_TYPE, chat_id: int, action: str, admin_user_id: int, status_message_id: int):
    """Helper for kick/ban all muted users.
       Args:
           context: The context object.
           chat_id: The ID of the group chat.
           action: The action to perform ('kick' or 'ban').
           admin_user_id: The user ID of the admin who initiated the operation. <-- ADDED argument
           status_message_id: The ID of the message in the group to update with status. <-- ADDED argument
    """
    chat = await get_chat_with_retry(context.bot, chat_id)
    if not chat:
         logger.error(f"Batch action: Could not get chat object for ID {chat_id}. Cannot proceed.")
         await send_message_safe(context, admin_user_id, f"Error: Could not access chat {chat_id} to perform batch action.")
         return

    # The admin permission check is already done in the callbackquery_handler caller.
    # We keep a defensive check here, but it's redundant if called only from the handler.
    # if not await is_user_group_admin_or_creator(context, chat.id, admin_user_id):
    #     logger.warning(f"Batch action: Non-admin user {admin_user_id} attempted batch action in chat {chat.id}. This should not happen.")
    #     await send_message_safe(context, admin_user_id, getattr(patterns, 'ADMIN_ONLY_ACTION_ERROR', 'Admin only action'))
    #     return

    # Check bot's permissions
    bot_has_action_permission = False
    try:
        bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
        if action == "kick" or action == "ban":
             bot_has_action_permission = getattr(bot_member, 'can_ban_members', False)
             if not bot_has_action_permission:
                  logger.warning(f"Batch {action}: Bot lacks 'can_ban_members' permission in chat {chat.id}. Batch operation will likely fail.")
                  # Notify the admin who clicked the button directly <-- ADDED
                  await send_message_safe(context, admin_user_id, f"Error performing batch '{action}' in group {chat.id}: I lack 'Ban Users' permission.")

        # Note: Checking mute status requires 'can_restrict_members', which might not be needed for just kicking/banning.
        # We will rely on the ban permission for the action itself.

    except Exception as e:
        logger.error(f"Batch {action}: Could not get bot permissions in chat {chat.id}: {e}. Proceeding but expecting failures.")
        # Assume no necessary permissions if check fails


    if not bot_has_action_permission:
         # No permission, cannot proceed. Admin notified above.
         return # Return silently, admin already warned

    # Get the original message object to update its text using the passed message_id <-- MODIFIED
    status_message: Optional[TGMessage] = None
    if status_message_id:
         try:
             status_message = await context.bot.get_message(chat_id=chat_id, message_id=status_message_id)
         except Exception as e:
             logger.warning(f"Batch {action}: Could not get status message {status_message_id} in chat {chat_id} for editing: {e}")


    # Initial status message (now edits the provided message_id or sends a new one if fetch failed) <-- MODIFIED
    initial_status_text = f"Attempting to {action} all currently muted users in this group. This may take time..."
    if status_message:
        try:
            await context.bot.edit_message_text(
                chat_id=status_message.chat.id,
                message_id=status_message.message_id,
                text=initial_status_text,
                parse_mode=ParseMode.HTML,
                reply_markup=None # Remove buttons from the status message
            )
        except Exception as e:
             logger.warning(f"Batch {action}: Failed to edit status message {status_message_id} in chat {chat_id} to initial text: {e}")
             status_message = None # Clear status_message so we send new messages instead
    # If status_message is None (either fetch failed or edit failed), send a new one.
    if status_message is None:
         status_message = await send_message_safe(context, chat_id, initial_status_text, parse_mode=ParseMode.HTML)
         if status_message is None:
              logger.error(f"Batch {action}: Failed to send initial status message to chat {chat_id}.")
              # Cannot provide status updates if initial message failed, return early?
              # Let's continue but log warnings for failed edits.


    # Getting "all muted users" is non-trivial without iterating all users
    # and checking their restrictions, which is very API intensive.
    # A practical approach: iterate users known to the bot (from `users` table) and check their status in *this* group.
    # This won't get users muted by other admins if the bot doesn't know them from previous interactions.

    known_users_in_db = await get_all_users_from_db()
    actioned_count = 0
    failed_count = 0
    skipped_not_muted = 0 # Users known to the bot but not currently muted in THIS group
    total_users_to_check = len(known_users_in_db)

    if total_users_to_check == 0:
        final_msg = "No users known to the bot to check for muting status."
        if status_message:
            try: await status_message.edit_text(final_msg, parse_mode=ParseMode.HTML, reply_markup=None)
            except Exception: pass # Failed to edit, ignore
        else:
            await send_message_safe(context, chat_id, final_msg)
        return # Return counts if the caller needs them (currently not used by callbackquery_handler)


    logger.info(f"Batch {action}: Checking {total_users_to_check} known users in chat {chat.id}...")

    for i, user_id in enumerate(known_users_in_db):
        # Check SHUTTING_DOWN flag
        if SHUTTING_DOWN:
            logger.warning(f"Batch {action}: Shutting down, stopping operation.")
            break

        try:
            # Check member status to see if they are restricted (muted by us or other admin)
            member = await context.bot.get_chat_member(chat.id, user_id)
            # A user is considered muted if they are restricted and can_send_messages is False
            is_muted = (member.status == ChatMemberStatus.RESTRICTED and not getattr(member, 'can_send_messages', True))

            if is_muted:
                logger.debug(f"User {user_id} is muted in group {chat.id}. Attempting to {action}.")
                try:
                    if action == "kick":
                        # Ban first, then unban for kick
                        await context.bot.ban_chat_member(chat.id, user_id)
                        await asyncio.sleep(0.5) # Small delay between ban and unban
                        await context.bot.unban_chat_member(chat.id, user_id, only_if_banned=True)
                    elif action == "ban":
                        await context.bot.ban_chat_member(chat.id, user_id)
                    actioned_count += 1
                    # Log the action
                    log_reason = f"Batch {action} by admin {admin_user_id}"
                    await log_action_db(context, action.capitalize() + " (Batch Muted)", user_id, chat.id, log_reason)
                    logger.info(f"Successfully batch-{action}ed user {user_id} in chat {chat.id}.")

                except Forbidden:
                    logger.warning(f"Batch {action}: Forbidden to {action} user {user_id} in {chat.id}.")
                    failed_count += 1
                except BadRequest as e:
                    error_msg_lower = str(e).lower()
                    if "member not found" not in error_msg_lower and "user not found" not in error_msg_lower and "user_is_not_a_participant" not in error_msg_lower and "participant_id_invalid" not in error_msg_lower: # Added participant_id_invalid check
                        logger.warning(f"Batch {action}: BadRequest trying to {action} user {user_id} in {chat.id}: {e}")
                        failed_count += 1
                    else:
                         logger.debug(f"Batch {action}: User {user_id} not found in group {chat.id} during action attempt.")

                except Exception as e:
                    logger.error(f"Error during batch {action} for user {user_id} in {chat.id}: {e}", exc_info=True)
                    failed_count += 1
            else:
                skipped_not_muted += 1
                logger.debug(f"User {user_id} is not muted in group {chat.id}. Skipping batch {action}.")

        except BadRequest as e:
             # Handle BadRequest during get_chat_member (e.g., user not in group)
             error_msg_lower = str(e).lower()
             if "member not found" in error_msg_lower or "user not found" in error_msg_lower or "user_is_not_a_participant" in error_msg_lower or "participant_id_invalid" in error_msg_lower: # Added participant_id_invalid check
                  skipped_not_muted += 1 # User not in group, so not muted there by us
                  logger.debug(f"Batch {action}: User {user_id} not found in group {chat.id} during status check.")
             else:
                  logger.warning(f"Batch {action}: BadRequest checking status for user {user_id} in {chat.id}: {e}")
                  failed_count += 1 # Count check failure as operational failure
        except Forbidden:
             # Handle Forbidden during get_chat_member (e.g., bot removed, or lacks permission to see members)
             logger.warning(f"Batch {action}: Forbidden to check status for user {user_id} in {chat.id}. Cannot determine mute status.")
             failed_count += 1 # Count check failure as operational failure
        except Exception as e:
            # Catch TimedOut, NetworkError, or other unexpected exceptions during get_chat_member
            logger.error(f"Error checking mute status for user {user_id} in {chat.id}: {e}", exc_info=True)
            failed_count += 1 # Count check failure as operational failure


        # Update status message periodically
        if (i + 1) % 50 == 0 or (i + 1) == total_users_to_check:
            if status_message:
                try:
                     await context.bot.edit_message_text(
                        chat_id=status_message.chat.id, # Use the chat ID from the sent message
                        message_id=status_message.message_id, # Use the message ID of the sent message
                        text=f"Batch {action} operation in progress for group {chat.id}.\n"
                        f"Processed {i + 1}/{total_users_to_check} known users.\n"
                        f"{action.capitalize()}ed: {actioned_count}\n"
                        f"Skipped (not muted or not in group): {skipped_not_muted}\n"
                        f"Failed attempts: {failed_count}",
                        parse_mode=ParseMode.HTML
                     )
                except Exception as e_edit:
                     logger.warning(f"Could not edit status message {status_message_id} during batch {action}: {e_edit}")
            else:
                 # If status message failed initially, just log progress
                 logger.info(f"Batch {action}: Processed {i + 1}/{total_users_to_check}. {action.capitalize()}ed: {actioned_count}, Failed: {failed_count}")


        # Add a short delay between API calls
        await asyncio.sleep(BROADCAST_SLEEP_INTERVAL)

    # Final status message
    final_msg_text = f"Batch {action} operation complete for group {chat.id}.\n" \
                     f"{action.capitalize()}ed {actioned_count} users.\n" \
                     f"Skipped (not muted or not in group): {skipped_not_muted}\n" \
                     f"Failed attempts: {failed_count}."

    if status_message:
        try:
             await status_message.edit_text(
                chat_id=status_message.chat.id,
                message_id=status_message.message_id,
                text=final_msg_text,
                parse_mode=ParseMode.HTML,
                reply_markup=None # Remove buttons if they were present (unlikely for this message)
             )
        except Exception as e_final_edit:
             logger.error(f"Could not edit final status message {status_message_id} for batch {action}: {e_final_edit}")
             # Fallback to sending a new message
             await send_message_safe(context, chat_id, final_msg_text, parse_mode=ParseMode.HTML)

    else:
         # If initial status message failed and final edit failed, send a new final message.
         await send_message_safe(context, chat_id, final_msg_text, parse_mode=ParseMode.HTML)

    # Return counts if the caller needs them (currently not used by callbackquery_handler)
    # return actioned_count, failed_count, skipped_not_muted

# --- CallbackQuery Handler ---
# [Preceding code, likely after _batch_action_on_muted_users helper]

# --- CallbackQuery Handler ---
async def callbackquery_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    message = query.message 
    chat_id = message.chat.id if message and message.chat else None

    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"Failed to answer callback query {query.id}: {e}")

    data = query.data
    logger.info(f"CallbackQuery: Data='{data}', UserID={user.id}, ChatID={chat_id if chat_id is not None else 'N/A'}, MessageID={message.message_id if message else 'N/A'}")

    global MAINTENANCE_MODE
    maintenance_bypass_callbacks = {"show_help", "verify_join_pm", "proveadmin", "pmunmute_attempt_"}
    is_maintenance_bypass_callback = any(data.startswith(prefix) for prefix in maintenance_bypass_callbacks)

    if MAINTENANCE_MODE and not is_maintenance_bypass_callback:
        if user.id not in AUTHORIZED_USERS:
            try:
                if message:
                    await query.edit_message_text(getattr(patterns, 'MAINTENANCE_MODE_MESSAGE', 'Bot is under maintenance.'), reply_markup=message.reply_markup)
                else:
                    await send_message_safe(context, user.id, getattr(patterns, 'MAINTENANCE_MODE_MESSAGE', 'Bot is under maintenance.'))
            except Exception as e:
                logger.warning(f"Failed to inform user {user.id} about maintenance: {e}")
            return

    # Handle PM unmute attempt
    if data.startswith("pmunmute_attempt_"):
        try:
            user_id = int(data.split("_")[-1])
            if user_id != user.id:
                logger.warning(f"Callback user ID mismatch: {user.id} vs {user_id}")
                await send_message_safe(context, user.id, "Invalid unmute attempt.")
                return
            group_ids = context.user_data.get('unmute_group_ids', [])
            if not group_ids:
                group_ids = [row[0] for row in await db_fetchall(
                    "SELECT DISTINCT group_id FROM bad_actors WHERE user_id = ? AND punishment_type = 'mute' AND (punishment_end > ? OR punishment_end IS NULL)",
                    (user.id, int(time.time())),
                )]
                if not group_ids:
                    await query.edit_message_text("You are not muted in any groups.", reply_markup=None) if message else await send_message_safe(context, user.id, "You are not muted.")
                    return
                context.user_data['unmute_group_ids'] = group_ids

            # Check channel and profile
            channel_id = settings.get("channel_id")
            is_subbed = True
            if channel_id:
                try:
                    is_subbed = await is_user_subscribed(context, user.id, chat_id_for_pm_guidance=None)
                except telegram.error.RetryAfter as e:
                    logger.warning(f"Rate limit hit checking subscription for user {user.id}. Waiting {e.retry_after}s.")
                    await asyncio.sleep(e.retry_after)
                    is_subbed = await is_user_subscribed(context, user.id, chat_id_for_pm_guidance=None)
                except telegram.error.Forbidden:
                    logger.warning(f"Cannot check subscription for user {user.id}: Bot blocked.")
                    is_subbed = False

            has_profile_issue, problematic_field, _ = await user_has_links_cached(context, user.id)

            patterns_dict = {
                "unmute_success": getattr(patterns, 'UNMUTE_SUCCESS', 'You have been unmuted in {group_names}.'),
                "unmute_failed": getattr(patterns, 'UNMUTE_FAILED', 'Cannot unmute. Please fix your profile or join the channel.'),
                "pm_unmute_retry": getattr(patterns, 'PM_UNMUTE_RETRY_BUTTON_TEXT', 'Unmute Me'),
                "pm_unmute_subscribe": getattr(patterns, 'PM_UNMUTE_INSTRUCTIONS_SUBSCRIBE', '1. Join our channel: {channel_link}'),
                "pm_unmute_profile": getattr(patterns, 'PM_UNMUTE_INSTRUCTIONS_PROFILE', '2. Remove links from your {field}'),
                "pm_unmute_both": getattr(patterns, 'PM_UNMUTE_INSTRUCTIONS_BOTH', 'To unmute:\n- Join our channel: {channel_link}\n- Remove links from your {field}')
            }

            if is_subbed and not has_profile_issue:
                group_names = []
                for group_id in group_ids:
                    try:
                        await context.bot.restrict_chat_member(
                            group_id, user.id,
                            permissions=ChatPermissions(
                                can_send_messages=True, can_send_media_messages=True, can_send_polls=True, can_send_other_messages=True,
                                can_send_audios=True, can_send_documents=True, can_send_photos=True, can_send_videos=True,
                                can_send_video_notes=True, can_send_voice_notes=True, can_add_web_page_previews=True,
                                can_change_info=True, can_invite_users=True, can_pin_messages=True, can_manage_topics=True
                            )
                        )
                        await db_execute(
                            "DELETE FROM bad_actors WHERE user_id = ? AND group_id = ? AND punishment_type = 'mute'",
                            (user.id, group_id)
                        )
                        name = await get_chat_name(context, group_id) or f"Group {group_id}"
                        group_names.append(name)
                    except telegram.error.RetryAfter as e:
                        logger.warning(f"Rate limit hit unmuting user {user.id} in group {group_id}. Waiting {e.retry_after}s.")
                        await asyncio.sleep(e.retry_after)
                        continue
                    except Exception as e:
                        logger.error(f"Failed to unmute user {user.id} in group {group_id}: {e}")
                if group_names:
                    await query.edit_message_text(
                        patterns_dict["unmute_success"].format(group_names=", ".join(group_names)),
                        parse_mode=ParseMode.HTML,
                        reply_markup=None
                    ) if message else await send_message_safe(context, user.id, patterns_dict["unmute_success"].format(group_names=", ".join(group_names)), parse_mode=ParseMode.HTML)
                    context.user_data.pop('unmute_group_ids', None)
                    context.user_data.pop('unmute_message_id', None)
                else:
                    await query.edit_message_text("Failed to unmute in any groups. Try again.", reply_markup=None) if message else await send_message_safe(context, user.id, "Failed to unmute.")
            else:
                message_parts = []
                buttons = []
                channel_link = settings.get("channel_invite_link")
                if not channel_link and channel_id:
                    try:
                        channel_chat = await get_chat_with_retry(context.bot, channel_id)
                        channel_link = channel_chat.invite_link or (f"https://t.me/{channel_chat.username}" if channel_chat.username else None)
                        if channel_link:
                            settings["channel_invite_link"] = channel_link
                    except Exception as e:
                        logger.warning(f"Failed to fetch channel link for {channel_id}: {e}")

                if channel_id and not is_subbed and has_profile_issue:
                    message_parts.append(patterns_dict["pm_unmute_both"].format(
                        channel_link=channel_link or f"Channel ID: {channel_id}",
                        field=problematic_field or "profile"
                    ))
                    if channel_link:
                        buttons.append([InlineKeyboardButton(getattr(patterns, 'JOIN_VERIFICATION_CHANNEL_BUTTON_TEXT', 'Join Channel'), url=channel_link)])
                    buttons.append([InlineKeyboardButton(getattr(patterns, 'VERIFY_JOIN_BUTTON_TEXT', 'Verify Join'), callback_data="verify_join_pm")])
                elif channel_id and not is_subbed:
                    message_parts.append(patterns_dict["pm_unmute_subscribe"].format(
                        channel_link=channel_link or f"Channel ID: {channel_id}"
                    ))
                    if channel_link:
                        buttons.append([InlineKeyboardButton(getattr(patterns, 'JOIN_VERIFICATION_CHANNEL_BUTTON_TEXT', 'Join Channel'), url=channel_link)])
                    buttons.append([InlineKeyboardButton(getattr(patterns, 'VERIFY_JOIN_BUTTON_TEXT', 'Verify Join'), callback_data="verify_join_pm")])
                elif has_profile_issue:
                    message_parts.append(patterns_dict["pm_unmute_profile"].format(field=problematic_field or "profile"))

                buttons.append([InlineKeyboardButton(patterns_dict["pm_unmute_retry"], callback_data=f"pmunmute_attempt_{user.id}")])
                await query.edit_message_text(
                    "\n".join([patterns_dict["unmute_failed"]] + message_parts),
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(buttons)
                ) if message else await send_message_safe(context, user.id, "\n".join([patterns_dict["unmute_failed"]] + message_parts), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Error processing pmunmute_attempt for user {user.id}: {e}", exc_info=True)
            await query.edit_message_text("An error occurred. Please try again.") if message else await send_message_safe(context, user.id, "An error occurred.")
        return

    # Handle cancel_resolution
    if data == "cancel_resolution":
        if 'awaiting_contact_for' in context.user_data:
            chat_id = context.user_data['awaiting_contact_for']['chat_id']
            del context.user_data['awaiting_contact_for']
            await send_message_safe(context, user.id, "Resolution process cancelled.")
            await send_message_safe(context, chat_id, "Username resolution cancelled by admin.")
        try:
            await query.delete_message()
        except Exception as e:
            logger.debug(f"Could not delete cancel button message: {e}")
        return

    # Handle show_help
    if data == "show_help":
        pseudo_update_for_help = Update(update_id=update.update_id)
        pseudo_update_for_help._effective_user = user
        if message:
            pseudo_update_for_help._effective_chat = message.chat
        else:
            try:
                user_pm_chat = await get_chat_with_retry(context.bot, user.id)
                if user_pm_chat:
                    pseudo_update_for_help._effective_chat = user_pm_chat
                else:
                    await send_message_safe(context, user.id, getattr(patterns, 'HELP_COMMAND_TEXT_PRIVATE', 'Help fallback.'), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                    return
            except Exception as e:
                logger.error(f"Error getting PM chat for user {user.id} for help callback: {e}")
                await send_message_safe(context, user.id, getattr(patterns, 'HELP_COMMAND_TEXT_PRIVATE', 'Help fallback.'), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                return
        await help_command_handler(pseudo_update_for_help, context)
        if message:
            try:
                await message.delete()
            except Exception as e:
                logger.debug(f"Could not delete help button message: {e}")
        return

    # Handle verify_join_pm
    if data == "verify_join_pm":
        if message is None or message.chat.type != TGChat.PRIVATE:
            logger.warning(f"verify_join_pm callback received without message or in non-private chat {chat_id}. Ignoring.")
            return
        user_id_for_verify = user.id
        channel_id_for_verify = settings.get("channel_id")
        if not channel_id_for_verify:
            await query.edit_message_text(getattr(patterns, 'VERIFY_NO_CHANNEL_SET_ERROR', 'No channel set.'), reply_markup=None) if message else await send_message_safe(context, user.id, "No channel set.")
            return

        is_subbed = await is_user_subscribed(context, user_id_for_verify, chat_id_for_pm_guidance=None)
        updated_verification_status_text = ""
        updated_kb_buttons_top = []
        bot_name = await get_bot_username(context) or "BardsSentinelBot"
        join_channel_button_text = getattr(patterns, 'JOIN_VERIFICATION_CHANNEL_BUTTON_TEXT', 'Join Channel')
        verify_button_text = getattr(patterns, 'VERIFY_JOIN_BUTTON_TEXT', 'Verify Join')

        if is_subbed:
            updated_verification_status_text = getattr(patterns, 'VERIFICATION_STATUS_VERIFIED', "✅ You are verified.")
            if user_profile_cache and user_id_for_verify in user_profile_cache:
                del user_profile_cache[user_id_for_verify]
                log_cache_access("user_profile_cache", user_id_for_verify, "delete (verified via callback)", user_profile_cache)
            logger.info(f"User {user_id_for_verify} verified subscription via PM button.")
        else:
            channel_display_link = settings.get("channel_invite_link")
            has_usable_link = bool(channel_display_link and "Channel ID:" not in channel_display_link and "error" not in channel_display_link)
            if not has_usable_link:
                try:
                    channel_chat_obj = await get_chat_with_retry(context.bot, channel_id_for_verify)
                    if channel_chat_obj:
                        new_link = channel_chat_obj.invite_link or (f"https://t.me/{channel_chat_obj.username}" if channel_chat_obj.username else None)
                        if new_link:
                            channel_display_link = new_link
                            settings["channel_invite_link"] = new_link
                            has_usable_link = True
                except Exception:
                    pass

            if has_usable_link:
                updated_verification_status_text = getattr(patterns, 'VERIFICATION_STATUS_NOT_VERIFIED_JOIN', "⚠️ Join: {channel_link}").format(channel_link=channel_display_link)
                updated_kb_buttons_top.append([InlineKeyboardButton(join_channel_button_text, url=channel_display_link)])
            else:
                updated_verification_status_text = getattr(patterns, 'VERIFICATION_STATUS_NOT_VERIFIED_CLICK_VERIFY', "⚠️ Click verify after joining.")
            updated_kb_buttons_top.append([InlineKeyboardButton(verify_button_text, callback_data="verify_join_pm")])

        start_msg_base = getattr(patterns, 'START_MESSAGE_PRIVATE_BASE', "Welcome!")
        start_msg_admin_config = getattr(patterns, 'START_MESSAGE_ADMIN_CONFIG', "Admin info.")
        start_msg_channel_verify_info = getattr(patterns, 'START_MESSAGE_CHANNEL_VERIFY_INFO', "")
        start_msg_help_prompt = getattr(patterns, 'START_MESSAGE_HELP_PROMPT', "Type /help.")
        add_bot_button_text = getattr(patterns, 'ADD_BOT_TO_GROUP_BUTTON_TEXT', 'Add Bot').format(bot_username=bot_name)

        standard_buttons = [
            [InlineKeyboardButton(getattr(patterns, 'HELP_BUTTON_TEXT', 'Help'), callback_data="show_help")],
            [InlineKeyboardButton(add_bot_button_text, url=f"https://t.me/{bot_name}?startgroup=true")]
        ]
        if context.user_data.get('unmute_group_ids'):
            standard_buttons.append([InlineKeyboardButton(getattr(patterns, 'PM_UNMUTE_RETRY_BUTTON_TEXT', 'Unmute Me'), callback_data=f"pmunmute_attempt_{user.id}")])

        final_message_parts = [start_msg_base, start_msg_admin_config]
        if channel_id_for_verify:
            final_message_parts.append(start_msg_channel_verify_info)
        if updated_verification_status_text:
            final_message_parts.append(updated_verification_status_text)
        final_message_parts.append(start_msg_help_prompt)
        final_message_text = "\n\n".join(filter(None, final_message_parts))
        all_buttons = updated_kb_buttons_top + standard_buttons

        try:
            await query.edit_message_text(final_message_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(all_buttons), disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Failed to edit message {message.message_id} for user {user.id} after verify_join_pm: {e}", exc_info=True)
            await send_message_safe(context, message.chat.id, final_message_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(all_buttons), disable_web_page_preview=True)
        return

    # Handle group unmute
    if data.startswith("unmute_"): 
        parts = data.split("_")
        if len(parts) < 4:
            logger.error(f"Invalid callback data for group unmute: {data}.")
            await query.edit_message_text(getattr(patterns, 'INVALID_DURATION_FROM_BUTTON_ERROR', 'Invalid button data.'), reply_markup=None) if message else None
            return
        try:
            user_id_to_unmute_cb = int(parts[1])
            chat_id_of_mute_button = int(parts[2])
            mute_message_id = int(parts[3])
        except ValueError:
            logger.error(f"Invalid integer in group unmute callback data: {data}")
            await query.edit_message_text(getattr(patterns, 'INVALID_DURATION_FROM_BUTTON_ERROR', 'Invalid ID in button data.'), reply_markup=None) if message else None
            return

        if chat_id_of_mute_button != chat_id:
            logger.warning(f"Group unmute button clicked in wrong chat. Expected {chat_id_of_mute_button}, got {chat_id}. User: {user.id}.")
            await query.edit_message_text("This button is for a different chat.", reply_markup=None) if message else None
            return
        if user.id != user_id_to_unmute_cb:
            await send_message_safe(context, user.id, getattr(patterns, 'UNMUTE_CANNOT_UNMUTE_OTHERS_ERROR', 'Cannot unmute others.'))
            return

        await add_unmute_attempt(user.id, chat_id_of_mute_button)
        unmute_cache_key = f"unmute_attempt_{user.id}_{chat_id_of_mute_button}"
        if unmute_cache_key in unmute_attempt_cache:
            await query.edit_message_text(getattr(patterns, 'UNMUTE_ATTEMPT_DEBOUNCE_ERROR', 'Please wait before trying again.'), reply_markup=message.reply_markup) if message else None
            return
        unmute_attempt_cache[unmute_cache_key] = True

        try:
            await query.edit_message_text(getattr(patterns, 'PM_UNMUTE_ATTEMPTING', 'Attempting to unmute...'), reply_markup=None)
        except Exception as e:
            logger.warning(f"Failed to edit group message {mute_message_id} for user {user.id}: {e}")

        unmute_successful, failure_reason = await attempt_unmute_user(context, user.id, chat_id_of_mute_button, mute_message_id, is_pm_flow=False)
        user_html_mention = user.mention_html()

        if unmute_successful:
            await db_execute(
                "DELETE FROM bad_actors WHERE user_id = ? AND group_id = ? AND punishment_type = 'mute'",
                (user.id, chat_id_of_mute_button)
            )
            unmute_success_msg_group = getattr(patterns, 'UNMUTE_SUCCESS_MESSAGE_GROUP', '{user_mention} has been unmuted.').format(user_mention=user_html_mention)
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id_of_mute_button, message_id=mute_message_id,
                    text=unmute_success_msg_group, parse_mode=ParseMode.HTML, reply_markup=None
                )
            except Exception as e:
                logger.warning(f"Failed to edit group message {mute_message_id} in {chat_id_of_mute_button}: {e}")
        else:
            fail_message_group = ""
            final_markup_for_group_failure = None
            bot_username = await get_bot_username(context)
            unmute_via_pm_button_text = getattr(patterns, 'UNMUTE_VIA_PM_BUTTON_TEXT', '✍️ Unmute via Bot PM')
            pm_url = f"https://t.me/{bot_username}?start=unmute_{chat_id_of_mute_button}_{user.id}_{mute_message_id}" if bot_username else None

            if failure_reason == "subscription_required":
                fail_message_group = getattr(patterns, 'UNMUTE_SUBSCRIPTION_REQUIRED_MESSAGE_GROUP', 'Verification required. Check your PM with the bot.')
                if pm_url:
                    final_markup_for_group_failure = InlineKeyboardMarkup([[InlineKeyboardButton(unmute_via_pm_button_text, url=pm_url)]])
            elif failure_reason and failure_reason.startswith("profile_issue_"):
                problematic_field = failure_reason.replace("profile_issue_", "").replace("_", " ")
                fail_message_group = getattr(patterns, 'UNMUTE_CHECK_PM_FOR_ISSUES_MESSAGE_GROUP', 'Profile issues detected. Check your PM with the bot.')
                if pm_url:
                    final_markup_for_group_failure = InlineKeyboardMarkup([[InlineKeyboardButton(unmute_via_pm_button_text, url=pm_url)]])
                await send_message_safe(context, user.id, getattr(patterns, 'UNMUTE_PROFILE_STILL_HAS_ISSUES_ERROR', 'Your profile has issues ({field}). Fix them.').format(field=problematic_field))
            elif failure_reason and failure_reason.startswith("rate_limited_"):
                wait_time_seconds = int(failure_reason.replace("rate_limited_", ""))
                wait_time_formatted = format_duration(wait_time_seconds)
                fail_message_group = getattr(patterns, 'UNMUTE_RATE_LIMITED_ERROR_MESSAGE', "⏳ Rate limited. Wait {wait_duration}.").format(wait_duration=wait_time_formatted)
                unmute_me_button_text = getattr(patterns, 'UNMUTE_ME_BUTTON_TEXT', 'Unmute Me')
                final_markup_for_group_failure = InlineKeyboardMarkup([[InlineKeyboardButton(unmute_me_button_text, callback_data=data)]])
            elif failure_reason == "bot_no_permission":
                fail_message_group = getattr(patterns, 'UNMUTE_BOT_NO_PERMISSION_ERROR_GROUP', 'I lack permission to unmute users.')
            elif failure_reason == "user_not_in_group":
                fail_message_group = "You are no longer in this group."
            elif failure_reason and failure_reason.startswith("bad_request_"):
                fail_message_group = getattr(patterns, 'UNMUTE_BAD_REQUEST_ERROR_GROUP', 'Error: You may not be in the group or already unmuted.')
            else:
                fail_message_group = f"Error: {failure_reason or 'Unknown'}"
                unmute_me_button_text = getattr(patterns, 'UNMUTE_ME_BUTTON_TEXT', 'Unmute Me')
                final_markup_for_group_failure = InlineKeyboardMarkup([[InlineKeyboardButton(unmute_me_button_text, callback_data=data)]])

            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id_of_mute_button, message_id=mute_message_id,
                    text=fail_message_group, parse_mode=ParseMode.HTML,
                    reply_markup=final_markup_for_group_failure
                )
            except Exception as e:
                logger.warning(f"Failed to edit group failure message {mute_message_id} in {chat_id_of_mute_button}: {e}")
                await send_message_safe(context, chat_id_of_mute_button, fail_message_group, parse_mode=ParseMode.HTML, reply_markup=final_markup_for_group_failure)
        return

    # Handle setpunishcmd_
    if data.startswith("setpunishcmd_"):
        parts = data.split("_")
        if len(parts) < 3:
            logger.error(f"Invalid callback data for setpunishcmd: {data}")
            await query.edit_message_text("Invalid button data.", reply_markup=None) if message else None
            return
        action_or_menu, target_chat_id_str = parts[1], parts[2]
        try:
            target_chat_id = int(target_chat_id_str)
        except ValueError:
            logger.error(f"Invalid group_id in setpunishcmd: {data}")
            await query.edit_message_text("Invalid group ID.", reply_markup=None) if message else None
            return

        if not await is_user_group_admin_or_creator(context, target_chat_id, user.id):
            await query.edit_message_text(getattr(patterns, 'ADMIN_ONLY_ACTION_ERROR', 'Admin only action')) if message else await send_message_safe(context, user.id, getattr(patterns, 'ADMIN_ONLY_ACTION_ERROR', 'Admin only action'))
            return

        group_chat_obj = await get_chat_with_retry(context.bot, target_chat_id)
        group_name = group_chat_obj.title or f"Group_{target_chat_id}" if group_chat_obj else f"Group_{target_chat_id}"

        if action_or_menu == "batchmenu":
            batch_kick_btn = getattr(patterns, 'PUNISH_BATCH_KICK_MUTED_BUTTON', 'Kick Muted')
            batch_ban_btn = getattr(patterns, 'PUNISH_BATCH_BAN_MUTED_BUTTON', 'Ban Muted')
            back_btn = getattr(patterns, 'BACK_BUTTON_TEXT', 'Back')
            batch_kb = [
                [InlineKeyboardButton(batch_kick_btn, callback_data=f"batchaction_kickmuted_{target_chat_id}")],
                [InlineKeyboardButton(batch_ban_btn, callback_data=f"batchaction_banmuted_{target_chat_id}")],
                [InlineKeyboardButton(back_btn, callback_data=f"setpunishcmd_back_{target_chat_id}")]
            ]
            await query.edit_message_text(getattr(patterns, 'PUNISH_BATCH_MENU_PROMPT', 'Batch menu.'), reply_markup=InlineKeyboardMarkup(batch_kb))
            return
        elif action_or_menu == "back":
            pseudo_update = Update(update_id=update.update_id, _effective_user=user, _effective_chat=group_chat_obj)
            context.args = []
            await set_punish_command(pseudo_update, context)
            await query.delete_message()
            return
        
        punish_action = action_or_menu
        if punish_action not in ["mute", "kick", "ban"]:
            logger.warning(f"Invalid punish action: {punish_action} for chat {target_chat_id}")
            await query.edit_message_text("Invalid action.", reply_markup=None) if message else None
            return
        
        await set_group_punish_action_async(target_chat_id, group_name, punish_action)
        await query.edit_message_text(getattr(patterns, 'SET_PUNISH_SUCCESS', 'Punish set to {action}').format(action=punish_action.capitalize()), reply_markup=None)
        return

    # Handle batchaction_
    if data.startswith("batchaction_"):
        parts = data.split("_")
        if len(parts) < 3:
            logger.error(f"Invalid callback for batchaction: {data}")
            await query.edit_message_text("Invalid button data.", reply_markup=None) if message else None
            return
        batch_action_type, target_chat_id_str = parts[1], parts[2]
        try:
            target_chat_id = int(target_chat_id_str)
        except ValueError:
            logger.error(f"Invalid group_id in batchaction: {data}")
            await query.edit_message_text("Invalid group ID.", reply_markup=None) if message else None
            return

        if not await is_user_group_admin_or_creator(context, target_chat_id, user.id):
            await query.edit_message_text(getattr(patterns, 'ADMIN_ONLY_ACTION_ERROR', 'Admin only action')) if message else await send_message_safe(context, user.id, getattr(patterns, 'ADMIN_ONLY_ACTION_ERROR', 'Admin only action'))
            return
        
        actual_action = "kick" if batch_action_type == "kickmuted" else "ban" if batch_action_type == "banmuted" else None
        if not actual_action:
            logger.warning(f"Unknown batch action type: {batch_action_type} for chat {target_chat_id}")
            await query.edit_message_text("Unknown batch action.", reply_markup=None) if message else None
            return

        status_message_id = message.message_id if message else None
        if not status_message_id:
            logger.error(f"Batch action {data} no message ID.")
            await query.edit_message_text("Error: Cannot start batch op.", reply_markup=None) if message else None
            return
        
        await query.edit_message_text(f"Attempting to {actual_action} all muted users...", reply_markup=None)
        context.application.create_task(
            _batch_action_on_muted_users(context, target_chat_id, actual_action, user.id, status_message_id)
        )
        return

    # Handle setdur_
    if data.startswith("setdur_"):
        parts = data.split("_")
        if len(parts) < 4:
            logger.error(f"Invalid callback for setdur: {data}")
            await query.edit_message_text("Invalid button data.", reply_markup=None) if message else None
            return
        
        duration_scope_type, target_chat_id_str, duration_value_str = parts[1], parts[2], parts[3]
        try:
            target_chat_id = int(target_chat_id_str)
        except ValueError:
            logger.error(f"Invalid group_id in setdur: {data}")
            await query.edit_message_text("Invalid group ID.", reply_markup=None) if message else None
            return

        if duration_scope_type not in ["all", "profile", "message", "mention_profile"]:
            logger.warning(f"Invalid duration scope type: {duration_scope_type} for chat {target_chat_id}")
            await query.edit_message_text("Invalid duration type.", reply_markup=None) if message else None
            return

        if not await is_user_group_admin_or_creator(context, target_chat_id, user.id):
            await query.edit_message_text(getattr(patterns, 'ADMIN_ONLY_ACTION_ERROR', 'Admin only action')) if message else await send_message_safe(context, user.id, getattr(patterns, 'ADMIN_ONLY_ACTION_ERROR', 'Admin only action'))
            return

        group_chat_obj = await get_chat_with_retry(context.bot, target_chat_id)
        group_name = group_chat_obj.title or f"Group_{target_chat_id}" if group_chat_obj else f"Group_{target_chat_id}"
        
        cmd_name_for_custom = "setduration"
        if duration_scope_type != "all":
            cmd_name_for_custom += duration_scope_type

        if duration_value_str == "custom":
            custom_prompt_text = getattr(patterns, 'DURATION_CUSTOM_PROMPT_CB', "Enter duration for {scope_type} (e.g., <code>/{command_name} 1d</code>).").format(
                scope_type=duration_scope_type.replace('_', ' ') if duration_scope_type != 'all' else getattr(patterns, 'ALL_TYPES_TEXT', 'all types'),
                command_name=cmd_name_for_custom
            )
            await query.edit_message_text(custom_prompt_text, parse_mode=ParseMode.HTML, reply_markup=None)
            return

        duration_seconds = parse_duration(duration_value_str)
        if duration_seconds is None:
            logger.error(f"Invalid duration value: {duration_value_str} in callback {data} for chat {target_chat_id}")
            await query.edit_message_text(getattr(patterns, 'INVALID_DURATION_FROM_BUTTON_ERROR', 'Invalid duration.'), reply_markup=None) if message else None
            return

        formatted_duration = format_duration(duration_seconds)
        if duration_scope_type == "all":
            await set_all_group_punish_durations_async(target_chat_id, group_name, duration_seconds)
            success_message_text = getattr(patterns, 'SET_DURATION_ALL_SUCCESS', 'Duration for all types set to {duration_formatted}').format(duration_formatted=formatted_duration)
        else:
            await set_group_punish_duration_for_trigger_async(target_chat_id, group_name, duration_scope_type, duration_seconds)
            success_pattern_cb_attr = f"SET_DURATION_{duration_scope_type.upper()}_SUCCESS"
            scope_display = duration_scope_type.replace('_', ' ')
            success_message_text = getattr(patterns, success_pattern_cb_attr, getattr(patterns, 'SET_DURATION_GENERIC_SUCCESS', 'Duration for {trigger_type} set to {duration_formatted}')).format(
                trigger_type=scope_display, duration_formatted=formatted_duration
            )
        
        await query.edit_message_text(success_message_text, reply_markup=None)
        return

    # Handle approve_
    if data.startswith("approve_"):
        parts = data.split("_")
        if len(parts) < 4:
            logger.error(f"Invalid callback for approve: {data}.")
            await query.edit_message_text("Invalid button data.", reply_markup=None) if message else None
            return
        try:
            user_id_to_approve = int(parts[1])
            chat_id_of_action = int(parts[2])
            message_id_of_action = int(parts[3])
        except ValueError:
            logger.error(f"Invalid integer in approve callback: {data}")
            await query.edit_message_text("Invalid ID in button data.", reply_markup=None) if message else None
            return

        if not await is_user_group_admin_or_creator(context, chat_id_of_action, user.id):
            await send_message_safe(context, user.id, getattr(patterns, 'ADMIN_ONLY_ACTION_ERROR', 'Admin only action'))
            return
        
        await add_group_user_exemption(chat_id_of_action, user_id_to_approve)
        edit_text_final = ""
        
        try:
            bot_member = await context.bot.get_chat_member(chat_id_of_action, context.bot.id)
            if not getattr(bot_member, 'can_restrict_members', False):
                edit_text_final = getattr(patterns, 'APPROVE_USER_UNMUTE_FORBIDDEN_ERROR_GROUP', 'Approved, but cannot unmute due to missing permissions.')
                raise Forbidden("Bot lacks restrict permission")

            unmute_perms = ChatPermissions(
                can_send_messages=True, can_send_audios=True, can_send_documents=True,
                can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
                can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
                can_add_web_page_previews=True, can_change_info=True, can_invite_users=True, 
                can_pin_messages=True, can_manage_topics=True
            )
            await context.bot.restrict_chat_member(chat_id_of_action, user_id_to_approve, permissions=unmute_perms)
            await db_execute(
                "DELETE FROM bad_actors WHERE user_id = ? AND group_id = ? AND punishment_type = 'mute'",
                (user_id_to_approve, chat_id_of_action)
            )
            
            approved_user_obj = await get_chat_with_retry(context.bot, user_id_to_approve)
            approved_user_mention = approved_user_obj.mention_html() if approved_user_obj else f"User {user_id_to_approve}"
            admin_mention = user.mention_html()
            edit_text_final = getattr(patterns, 'APPROVE_USER_SUCCESS_MESSAGE_GROUP', '{approved_user_mention} approved and unmuted by {admin_mention}.').format(
                approved_user_mention=approved_user_mention, admin_mention=admin_mention)
            
            for key_base in [f"punish_notification_{chat_id_of_action}_{user_id_to_approve}", 
                             f"punish_notification_{chat_id_of_action}_{user_id_to_approve}_mention"]:
                if key_base in notification_debounce_cache:
                    del notification_debounce_cache[key_base]
            logger.info(f"Admin {user.id} approved and unmuted user {user_id_to_approve} in chat {chat_id_of_action}.")

        except Forbidden as e:
            logger.warning(f"Forbidden error unmuting approved user {user_id_to_approve} in chat {chat_id_of_action}: {e}")
        except BadRequest as e:
            logger.warning(f"BadRequest unmuting approved user {user_id_to_approve} in chat {chat_id_of_action}: {e}")
            edit_text_final = getattr(patterns, 'APPROVE_USER_UNMUTE_BADREQUEST_ERROR_GROUP', 'Approved, but error unmuting (user may not be in group).')
        except Exception as e:
            logger.error(f"Unexpected error approving/unmuting user {user_id_to_approve} in {chat_id_of_action}: {e}", exc_info=True)
            edit_text_final = f"User approved, but error during unmute: {e}"

        try:
            await context.bot.edit_message_text(
                chat_id=chat_id_of_action, message_id=message_id_of_action,
                text=edit_text_final, parse_mode=ParseMode.HTML, reply_markup=None
            )
        except Exception as e:
            logger.warning(f"Failed to edit message {message_id_of_action} in {chat_id_of_action}: {e}")
        return

    # Handle proveadmin_
    if data.startswith("proveadmin_"):
        parts = data.split("_")
        if len(parts) < 3:
            logger.error(f"Invalid callback for proveadmin: {data}")
            await query.edit_message_text("Invalid button data.", reply_markup=None) if message else None
            return
        try:
            target_chat_id = int(parts[1])
            original_msg_id = int(parts[2])
        except ValueError:
            logger.error(f"Invalid integer in proveadmin callback: {data}")
            await query.edit_message_text("Invalid ID in button data.", reply_markup=None) if message else None
            return

        is_admin_in_target_chat = await is_user_group_admin_or_creator(context, target_chat_id, user.id)
        if is_admin_in_target_chat:
            success_msg = getattr(patterns, 'PROVE_ADMIN_SUCCESS', '{user_mention} proved admin status.').format(user_mention=user.mention_html())
            await query.edit_message_text(success_msg, parse_mode=ParseMode.HTML, reply_markup=None) if message else await send_message_safe(context, target_chat_id, success_msg, parse_mode=ParseMode.HTML)
            logger.info(f"User {user.id} proved admin for chat {target_chat_id} regarding msg {original_msg_id}.")
        else:
            await query.answer(getattr(patterns, 'PROVE_ADMIN_FAILURE', 'You are not an administrator in this group.'), show_alert=True)
        return

    logger.warning(f"Received unhandled callback query data: {data} from user {user.id} in chat {chat_id}")

# --- ChatMember Handler ---
async def new_chat_members_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles updates about changes in chat member status (joins, leaves, restricts)."""
    chat_member_update = update.chat_member
    if not chat_member_update:
        logger.debug("ChatMemberUpdate received no chat_member data.")
        return

    chat = chat_member_update.chat # Chat where the membership change happened
    new_member_info = chat_member_update.new_chat_member # Info about the user whose status changed
    old_member_info = chat_member_update.old_chat_member # Previous status
    affected_user = new_member_info.user # The user object (TGUser)
    actor_user = chat_member_update.from_user # The user who caused the change (e.g., admin who banned, or the user themselves joining)

    logger.debug(f"Chat member update in chat {chat.id} for user {affected_user.id} ({affected_user.username or 'NoUsername'}). "
                 f"Old status: {old_member_info.status if old_member_info else 'N/A'}, New status: {new_member_info.status}. "
                 f"By user: {actor_user.id if actor_user else 'N/A'} ({actor_user.username or 'N/A'})")

    # --- Bot's own status changes ---
    if affected_user.id == context.bot.id:
        group_title_for_log = chat.title or f"Group_{chat.id}"
        # Bot joined or promoted
        if new_member_info.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR]:
            is_newly_added = (not old_member_info or old_member_info.status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED])
            if is_newly_added:
                join_date = getattr(new_member_info, 'date', datetime.now(timezone.utc))
                await add_group(chat.id, group_title_for_log, join_date.isoformat())
                logger.info(f"Bot joined group {chat.id} ('{group_title_for_log}'). Added to DB.")

                # Send welcome message to group
                bot_name = await get_bot_username(context) or "BardsSentinelBot"
                welcome_msg = getattr(patterns, 'BOT_ADDED_TO_GROUP_WELCOME_MESSAGE', "Greetings! Bard's Sentinel is here to help safeguard this group.").format(bot_name=bot_name)

                # --- Create the 'Add Bot to Group' button ---
                add_bot_button_text = getattr(patterns, 'ADD_BOT_TO_GROUP_BUTTON_TEXT', 'Add Bot').format(bot_username=bot_name)
                add_bot_button = InlineKeyboardButton(add_bot_button_text, url=f"https://t.me/{bot_name}?startgroup=true")
                welcome_markup = InlineKeyboardMarkup([[add_bot_button]])
                # --- End Button Creation ---

                # Send the message including the new button markup
                await send_message_safe(context, chat.id, welcome_msg, reply_markup=welcome_markup, parse_mode=ParseMode.HTML)
                # The previous 'await send_message_safe' line was indented incorrectly.

            # Log current permissions if bot is admin
            # This block correctly remains outside the is_newly_added check,
            # as it applies if the bot becomes admin regardless of whether it just joined.
            if new_member_info.status == ChatMemberStatus.ADMINISTRATOR:
                perms = new_member_info.can_manage_chat or False # Base perm
                perms_list = []
                if getattr(new_member_info, 'can_delete_messages', False): perms_list.append("CanDelete")
                if getattr(new_member_info, 'can_restrict_members', False): perms_list.append("CanRestrict")
                if getattr(new_member_info, 'can_promote_members', False): perms_list.append("CanPromote")
                if getattr(new_member_info, 'can_invite_users', False) or getattr(new_member_info, 'can_create_invite_links', False): perms_list.append("CanInviteLinks")
                if getattr(new_member_info, 'can_pin_messages', False): perms_list.append("CanPin")
                if getattr(new_member_info, 'can_manage_topics', False): perms_list.append("CanManageTopics") # New topic permission

                perms_log_parts = ["Bot is admin."] + perms_list
                logger.info(f"Bot permissions in {chat.id} ('{group_title_for_log}'): {', '.join(perms_log_parts)}")


        # Bot left or was kicked/banned
        elif new_member_info.status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED]:
            # Check if the old status indicates it was previously a member/admin
            was_member_or_admin = (old_member_info and old_member_info.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER, ChatMemberStatus.RESTRICTED])
            if was_member_or_admin:
                 logger.info(f"Bot left or was kicked/banned from group {chat.id} ('{group_title_for_log}'). Removing from DB.")
                 await remove_group_from_db(chat.id)
            else:
                 logger.debug(f"Bot status changed in {chat.id} to {new_member_info.status} but was not previously an active member. No DB removal needed.")
        return # End processing for bot's own updates

    # --- Other users' status changes (e.g., new user joins) ---
    # Determine if this is a "new join" event that needs profile checking.
    # A join event is typically MEMBER/ADMIN/OWNER from LEFT/BANNED/RESTRICTED or None (user's first interaction).
    is_new_join_event = (
        new_member_info.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER] and
        (not old_member_info or old_member_info.status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED, ChatMemberStatus.RESTRICTED])
    )

    if not is_new_join_event:
        logger.debug(f"User {affected_user.id} status change in {chat.id} is not a new join event ({old_member_info.status if old_member_info else 'N/A'} -> {new_member_info.status}). Skipping profile check.")
        return

    # Proceed with checks only if message processing is enabled and not in maintenance
    if MAINTENANCE_MODE or not await is_message_processing_enabled(): # Using the same feature control flag
        logger.debug(f"New member join: Maintenance mode ({MAINTENANCE_MODE}) or message processing disabled. Skipping checks for {affected_user.id}.")
        return

    if affected_user.is_bot:
        logger.debug(f"New member {affected_user.id} is a bot. Skipping profile check.")
        return # Don't check other bots

    # Check exemptions for the new user
    is_globally_exempt_new_user = affected_user.id in settings.get("free_users", set())
    is_group_exempt_new_user = await is_user_exempt_in_group(chat.id, affected_user.id)
    if is_globally_exempt_new_user or is_group_exempt_new_user:
        logger.debug(f"New member {affected_user.id} is exempt (Global: {is_globally_exempt_new_user}, Group: {is_group_exempt_new_user}). Skipping profile check.")
        return

    # Add user to DB (or update interacted_at). This also handles first time seen.
    await add_user(affected_user.id, affected_user.username or "", affected_user.first_name or "", getattr(affected_user, "last_name", ""))
    # Ensure the group is in DB. It should be added when bot joins, but this is a safety check.
    await add_group(chat.id, chat.title or f"Group_{chat.id}")


    # Check the new user's profile for issues
    logger.info(f"New user {affected_user.id} ({affected_user.username or 'NoUsername'}) joined chat {chat.id}. Checking profile.")
    has_profile_issue, problematic_field, issue_type = await user_has_links_cached(context, affected_user.id)

    if has_profile_issue:
        user_html_mention_new = affected_user.mention_html() if hasattr(affected_user, 'mention_html') else f"@{affected_user.username or affected_user.id}"
        # Use getattr for safe access to pattern string
        reason_for_action_new_user = getattr(patterns, 'NEW_USER_PROFILE_VIOLATION_REASON', 'New user profile issue.').format(
            field=problematic_field or patterns.UNKNOWN_TEXT,
            issue_type=issue_type or patterns.UNKNOWN_TEXT
        )
        logger.info(f"New user {affected_user.id} ({user_html_mention_new}) in chat {chat.id} has profile issue: {reason_for_action_new_user}")
        # Add to bad actors list based on profile issue found upon joining
        await add_bad_actor(affected_user.id, f"Profile issue on join: {issue_type or patterns.UNKNOWN_TEXT} in {problematic_field or patterns.UNKNOWN_TEXT}")


        # Construct a pseudo Update object for take_action.
        # take_action expects update.effective_chat and update.effective_user.
        # No message is directly associated with a join event for deletion.
        pseudo_update_for_join = Update(update_id=update.update_id) # Use update's ID
        pseudo_update_for_join._effective_chat = chat # The group chat
        pseudo_update_for_join._effective_user = affected_user # The new user is the one being actioned

        # Call take_action. Sender_trigger_type is "profile". No problematic_mentions from a join.
        # Pass the single reason for the action.
        await take_action(pseudo_update_for_join, context, [reason_for_action_new_user], "profile", [])
        logger.info(f"Action taken on {affected_user.id} for profile issue: {reason_for_action_new_user}")
    else:
        logger.info(f"New user {affected_user.id}'s profile is clean upon joining chat {chat.id}.")


async def pm_unmute_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    message = query.message # This is the message in the user's PM with the bot

    # Always answer the callback query
    try: await query.answer()
    except Exception as e: logger.warning(f"Failed to answer pm_unmute callback query: {e}")

    data = query.data # Should be in format "pmunmute_attempt_{user_id}"
    logger.info(f"PM Unmute Callback: Data='{data}', UserID={user.id}")

    # Check if the button clicked belongs to the user who clicked it (sanity check)
    parts = data.split("_")
    if len(parts) < 3:
         logger.error(f"Invalid callback data format for pmunmute: {data}")
         try: await query.edit_message_text(getattr(patterns, 'INVALID_DURATION_FROM_BUTTON_ERROR', 'Invalid button data.'), reply_markup=None) # Re-use generic pattern
         except Exception: pass
         return
    try: user_id_from_callback = int(parts[2])
    except ValueError:
         logger.error(f"Invalid user_id in pmunmute callback data: {data}")
         try: await query.edit_message_text(getattr(patterns, 'INVALID_DURATION_FROM_BUTTON_ERROR', 'Invalid user ID in button data.'), reply_markup=None)
         except Exception: pass
         return

    if user.id != user_id_from_callback:
        logger.warning(f"User {user.id} tried to use PM unmute button for user {user_id_from_callback}. Ignoring.")
        # Silently ignore or send a PM: "You can only use your own unmute button."
        await send_message_safe(context, user.id, getattr(patterns, 'UNMUTE_CANNOT_UNMUTE_OTHERS_ERROR', 'Cannot unmute others.'))
        return

    # Retrieve the group ID and message ID from user_data
    unmute_group_id = context.user_data.get('unmute_group_id')
    unmute_message_id = context.user_data.get('unmute_message_id')

    if unmute_group_id is None or unmute_message_id is None:
        logger.error(f"PM Unmute Callback: Missing unmute_group_id or unmute_message_id in user_data for user {user.id}.")
        try: await query.edit_message_text("Error: Could not find context for unmute request. Please try starting the unmute process from the group again.", reply_markup=None)
        except Exception: pass
        return

    # Debounce attempt
    unmute_debounce_key = f"unmute_attempt_{user.id}_{unmute_group_id}"
    if unmute_debounce_key in unmute_attempt_cache:
         # Send debounce message directly in PM (message is available)
         try: await message.edit_text(getattr(patterns, 'UNMUTE_ATTEMPT_DEBOUNCE_ERROR', 'Wait before retrying unmute.'), reply_markup=message.reply_markup)
         except Exception: pass
         logger.debug(f"Debounced PM unmute attempt for user {user.id} in chat {unmute_group_id}.")
         return
    unmute_attempt_cache[unmute_debounce_key] = True # Mark attempt in cache


    # Edit PM message to show "Attempting..."
    try:
        await query.edit_message_text(getattr(patterns, 'PM_UNMUTE_ATTEMPTING', 'Attempting to unmute...'), reply_markup=None)
    except Exception as e:
        logger.warning(f"Failed to edit PM message {message.message_id} for user {user.id} to 'Attempting...': {e}")

    # Attempt to unmute using the refactored function
    unmute_successful, failure_reason = await attempt_unmute_user(context, user.id, unmute_group_id, unmute_message_id, is_pm_flow=True)


    # --- Update messages based on result ---
    if unmute_successful:
        # Update PM message to show success
        unmute_success_msg_pm = getattr(patterns, 'PM_UNMUTE_SUCCESS', 'Success!').format(
            user_mention=user.mention_html(), # Mention in PM
            group_name=await get_chat_name(context, unmute_group_id)
        )
        try: await message.edit_text(unmute_success_msg_pm, parse_mode=ParseMode.HTML, reply_markup=None)
        except Exception as e: logger.warning(f"Failed to edit PM success message for {user.id}: {e}")

        # Update original group message (if available)
        unmute_success_msg_group = getattr(patterns, 'UNMUTE_SUCCESS_MESSAGE_GROUP', '{user_mention} unmuted.').format(user_mention=user.mention_html())
        try:
            await context.bot.edit_message_text(
                chat_id=unmute_group_id,
                message_id=unmute_message_id,
                text=unmute_success_msg_group,
                parse_mode=ParseMode.HTML,
                reply_markup=None # Remove buttons
            )
        except Exception as e:
            logger.warning(f"Failed to edit original group message {unmute_message_id} in {unmute_group_id} after unmute success for {user.id}: {e}. Message might be gone or bot lacks edit permission.")


        logger.info(f"PM Unmute Callback: User {user.id} successfully unmuted in group {unmute_group_id}.")
        # Clear user_data associated with this unmute flow
        if 'unmute_group_id' in context.user_data: del context.user_data['unmute_group_id']
        if 'unmute_message_id' in context.user_data: del context.user_data['unmute_message_id']


    else: # Unmute failed
        # Build error messages for PM
        error_messages = []
        pm_buttons_retry = [] # Buttons for the retry message

        if failure_reason == "subscription_required":
             # is_user_subscribed should have already sent PM guidance if needed (passing chat_id_of_mute_button).
             # We need to tell the user to check their PM for details and click the verify button there.
             # The 'Attempt Unmute Again' button should link back to this callback after they verify.
             # The simplest approach is to just show the retry button and let them follow the previous guidance.
             error_messages.append(getattr(patterns, 'PM_UNMUTE_FAIL_CHECKS_CHANNEL', 'You need to join the verification channel first.')) # NEW PATTERN NEEDED
             # Add Verify Join button (always needed if channel check is needed) - Link back to PM verify flow
             pm_buttons_retry.append([InlineKeyboardButton(getattr(patterns, 'VERIFY_JOIN_BUTTON_TEXT', 'Verify Join'), callback_data=f"verify_join_pm")])
             # Add the "Attempt Unmute Again" button to retry the whole process
             pm_buttons_retry.append([InlineKeyboardButton(getattr(patterns, 'PM_UNMUTE_RETRY_BUTTON_TEXT', 'Attempt Unmute Again'), callback_data=f"pmunmute_attempt_{user.id}")])

        elif failure_reason and failure_reason.startswith("profile_issue_"):
             problematic_field = failure_reason.replace("profile_issue_", "").replace("_", " ")
             error_messages.append(getattr(patterns, 'PM_UNMUTE_INSTRUCTIONS_PROFILE', 'Fix profile: {field}').format(field=problematic_field))
             # Add the "Attempt Unmute Again" button
             pm_buttons_retry.append([InlineKeyboardButton(getattr(patterns, 'PM_UNMUTE_RETRY_BUTTON_TEXT', 'Attempt Unmute Again'), callback_data=f"pmunmute_attempt_{user.id}")])

        elif failure_reason == "bot_no_permission":
             error_messages.append(getattr(patterns, 'PM_UNMUTE_FAIL_PERMS', 'I lack permissions to unmute you in {group_name}.').format(group_name=await get_chat_name(context, unmute_group_id)))

        elif failure_reason and failure_reason.startswith("bad_request_"):
             error_text = failure_reason.replace("bad_request_", "")
             error_messages.append(getattr(patterns, 'PM_UNMUTE_FAIL_BADREQUEST', 'An unexpected issue prevents unmute ({error}).').format(group_name=await get_chat_name(context, unmute_group_id), error=error_text))

        elif failure_reason == "user_not_in_group":
             error_messages.append("You are no longer in the group where you were muted. I cannot unmute you there.") # No specific pattern for this yet

        else: # Unknown error
             error_messages.append(getattr(patterns, 'PM_UNMUTE_FAIL_UNKNOWN', 'An unexpected error occurred during unmute ({error}).').format(group_name=await get_chat_name(context, unmute_group_id), error=failure_reason or getattr(patterns, 'UNKNOWN_TEXT', 'unknown')))


        # Construct final failure message for PM
        fail_message_pm_intro = getattr(patterns, 'PM_UNMUTE_FAIL_INTRO', 'Could not unmute you in {group_name} yet.').format(group_name=await get_chat_name(context, unmute_group_id)) # NEW PATTERN NEEDED
        fail_message_pm = fail_message_pm_intro + "\n\n" + "\n".join(error_messages)


        # Update PM message to show failure and retry/guidance buttons
        try:
             await message.edit_text(fail_message_pm, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(pm_buttons_retry) if pm_buttons_retry else None, disable_web_page_preview=True)
        except Exception as e:
             logger.warning(f"Failed to edit PM failure message for {user.id}: {e}")
             # Fallback: Send a new message if edit fails
             try: await send_message_safe(context, user.id, fail_message_pm, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(pm_buttons_retry) if pm_buttons_retry else None, disable_web_page_preview=True)
             except Exception as e_fallback: logger.error(f"Failed to send fallback PM failure message: {e_fallback}")


        logger.info(f"PM Unmute Callback: User {user.id} failed to unmute in group {unmute_group_id}. Reason: {failure_reason}.")
        # Do NOT clear user_data if unmute failed, the user might retry.

    return # Handled this callback
# --- END ADDITION: pm_unmute_callback_handler function ---


# --- Job Queue Setup ---
async def load_and_schedule_timed_broadcasts(application: Application):
    """Loads timed broadcasts from DB and schedules them with JobQueue."""
    if not application.job_queue:
        logger.warning("JobQueue not available. Cannot load or schedule timed broadcasts.")
        return

    # Select markup_json from the DB <-- MODIFIED
    stored_jobs = await db_fetchall("SELECT job_name, target_type, message_text, interval_seconds, next_run_time, markup_json FROM timed_broadcasts")
    logger.info(f"Found {len(stored_jobs)} timed broadcast(s) in DB to potentially schedule.")
    for job_details in stored_jobs:
        job_name = job_details.get('job_name')
        target_type = job_details.get('target_type')
        message_text = job_details.get('message_text')
        interval_seconds = job_details.get('interval_seconds')
        next_run_time_db = job_details.get('next_run_time') # This is a float (unix timestamp)
        markup_json = job_details.get('markup_json') # Get markup JSON <-- ADDED


        if not all([job_name, target_type, message_text, interval_seconds is not None, next_run_time_db is not None]):
             logger.error(f"Skipping timed broadcast from DB '{job_name}': Incomplete data. Removing from DB.")
             if job_name: await remove_timed_broadcast_from_db(job_name)
             continue

        # Check if job already running (e.g. due to multiple restarts quickly or JobQueue persistence)
        current_jobs_with_name = application.job_queue.get_jobs_by_name(job_name)
        if current_jobs_with_name:
            logger.info(f"Timed broadcast job '{job_name}' is already scheduled. Skipping re-scheduling from DB.")
            settings["active_timed_broadcasts"][job_name] = True # Ensure it's marked active in settings
            continue

        # Calculate 'first' delay for JobQueue.
        # next_run_time_db is the stored next execution time (unix timestamp).
        # 'first' should be the delay from now until that time. Ensure it's not negative.
        delay_until_next_run = max(0, float(next_run_time_db) - time.time())

        # Construct job data (exclude next_run_time as JobQueue manages it)
        job_data = {"target_type": target_type, "message_text": message_text}
        if markup_json: # Add markup_json to job_data if present <-- ADDED
             job_data['markup'] = markup_json

        # Schedule the repeating job
        application.job_queue.run_repeating(
            timed_broadcast_job_callback,
            interval=interval_seconds,
            first=delay_until_next_run, # Schedule based on stored next run time
            data=job_data,
            name=job_name
        )
        settings["active_timed_broadcasts"][job_name] = True # Mark as active in global settings
        logger.info(f"Scheduled timed broadcast '{job_name}' from DB. Interval: {format_duration(interval_seconds)}, Next run in: {format_duration(int(delay_until_next_run))}.")

    if stored_jobs: logger.info("Finished loading and scheduling timed broadcasts from DB.")
    else: logger.info("No timed broadcasts found in DB to schedule.")

# --- Error Handling ---
# In on_error handler
async def on_error(update: object | None, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(context.error, NetworkError):
        logger.warning(f"NetworkError encountered: {context.error}. Bot will retry automatically.")
    """Handler for bot errors."""
    logger.error(msg=getattr(patterns, 'ERROR_HANDLER_EXCEPTION', 'Error: {error}').format(error=context.error), exc_info=context.error)

    if isinstance(context.error, InvalidToken):
        logger.critical(getattr(patterns, 'ERROR_HANDLER_INVALID_TOKEN', 'Invalid token.'), exc_info=True)
        # Consider notifying super admins before exiting
        for admin_id in AUTHORIZED_USERS:
            await send_message_safe(context, admin_id, getattr(patterns, 'ERROR_HANDLER_INVALID_TOKEN', 'Invalid token.'))
        os._exit(1) # Force exit if token is bad

    elif isinstance(context.error, Forbidden):
        error_msg = getattr(patterns, 'ERROR_HANDLER_FORBIDDEN', 'Forbidden error: {error}').format(error=context.error)
        logger.error(error_msg)
        # Check if the error is related to a specific chat (group/channel)
        chat_id: Optional[int] = None
        if update and isinstance(update, Update):
            if update.effective_chat:
                chat_id = update.effective_chat.id
            elif update.callback_query and update.callback_query.message and update.callback_query.message.chat:
                 chat_id = update.callback_query.message.chat.id
            elif update.chat_member and update.chat_member.chat:
                 chat_id = update.chat_member.chat.id


        if chat_id is not None and chat_id < 0: # Group or channel chat
            logger.info(f"Encountered Forbidden error in group/channel {chat_id}. Checking bot status and may remove from DB.")
            # Attempt to verify bot status and remove group from DB if necessary
            try:
                # Check if bot is still in the chat using a robust method
                chat_member = await context.bot.get_chat_member(chat_id, context.bot.id)
                if chat_member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED]:
                    await remove_group_from_db(chat_id)
                    logger.warning(getattr(patterns, 'ERROR_HANDLER_FORBIDDEN_IN_GROUP_REMOVED', 'Forbidden in group {chat_id}, removed.').format(chat_id=chat_id))
                else:
                     # Bot is still in the chat but got Forbidden. Log warning.
                     logger.warning(f"Bot encountered Forbidden error in {chat_id} but is still a member/admin. May lack specific permissions.")
            except Exception as e_check:
                 logger.warning(f"Could not confirm bot status in group {chat_id} after Forbidden error: {e_check}. Removing from DB as precaution.")
                 await remove_group_from_db(chat_id)
                 logger.warning(getattr(patterns, 'ERROR_HANDLER_FORBIDDEN_IN_GROUP_REMOVED', 'Forbidden in group {chat_id}, removed.').format(chat_id=chat_id))

    # For other error types, the general error logging is sufficient, but you can add specific handling here.
    # e.g., isinstance(context.error, BadRequest), isinstance(context.error, TimedOut), etc.

    # Optional: Notify super admins about errors, but be careful not to flood them.
    # Basic debouncing or rate limiting for admin notifications might be needed.
    # error_message_for_admin = f"Bot Error: {context.error!s}\nUpdate: {update}"
    # for admin_id in AUTHORIZED_USERS:
    #     await send_message_safe(context, admin_id, error_message_for_admin[:4000])

# --- Main Bot Execution ---

def main():
    global TOKEN, DATABASE_NAME, SHUTTING_DOWN
    load_config()
    setup_logging()

    # Apply configurable logger levels
    for logger_name, level_str in specific_logger_levels.items():
        level = getattr(logging, level_str, None)
        if level is not None:
            try:
                logging.getLogger(logger_name).setLevel(level)
                logger.info(f"Set logging level for '{logger_name}' to {level_str}.")
            except Exception as e:
                logger.warning(f"Could not set logging level for '{logger_name}' to {level_str}: {e}")
        else:
            logger.warning(f"Invalid logging level '{level_str}' for logger '{logger_name}'.")

    if not TOKEN:
        logger.critical(
            getattr(patterns, 'TOKEN_NOT_LOADED_MESSAGE', 'Token not loaded.'),
            exc_info=True,
        )
        return

    # Apply nest_asyncio for environments like Termux
    try:
        import nest_asyncio
        nest_asyncio.apply()
        logger.debug("nest_asyncio applied.")
    except ImportError:
        logger.warning("nest_asyncio not installed. Install it if needed.")
    except Exception as e:
        logger.warning(f"Failed to apply nest_asyncio: {e}.")

    # Filter asyncio deprecation warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="asyncio")

    # Manage event loop
    loop = None
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError as e:
        if "There is no current event loop in thread" in str(e):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            logger.debug("Created and set a new event loop.")
        else:
            raise

    try:
        # Initialize database
        if loop:
            loop.run_until_complete(init_db(DATABASE_NAME))
        else:
            logger.critical("No event loop for database initialization. Exiting.")
            return

        # Build Application with custom request
        custom_request = HTTPXRequest(connect_timeout=10.0, read_timeout=10.0)
        application = Application.builder().token(TOKEN).request(custom_request).build()
        application.start_time_epoch = time.time()

        # Register handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(
            CallbackQueryHandler(pm_unmute_callback_handler, pattern=r"^pmunmute_attempt_\d+$")
        )
        application.add_handler(CommandHandler("checkallbios", check_all_bios_command))
        application.add_handler(CommandHandler("help", help_command_handler))
        application.add_handler(CommandHandler("setpunish", set_punish_command))
        application.add_handler(CommandHandler("setduration", set_duration_command))
        application.add_handler(CommandHandler("setdurationprofile", set_duration_profile_command))
        application.add_handler(CommandHandler("setdurationmessage", set_duration_message_command))
        application.add_handler(CommandHandler("setdurationmention", set_duration_mention_command))
        application.add_handler(CommandHandler("freepunish", freepunish_command))
        application.add_handler(CommandHandler("unfreepunish", unfreepunish_command))
        application.add_handler(CommandHandler("gfreepunish", gfreepunish_command))
        application.add_handler(CommandHandler("gunfreepunish", gunfreepunish_command))
        application.add_handler(CommandHandler("clearcache", clear_cache_command))
        application.add_handler(CommandHandler("checkbio", check_bio_command))
        application.add_handler(CommandHandler("setchannel", set_channel_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("disable", disable_command))
        application.add_handler(CommandHandler("enable", enable_command))
        application.add_handler(CommandHandler("maintenance", maintenance_command))
        application.add_handler(CommandHandler("unmuteall", unmuteall_command))
        application.add_handler(CommandHandler("gunmuteall", gunmuteall_command))
        application.add_handler(CommandHandler("broadcast", broadcast_command))
        application.add_handler(CommandHandler("bcastall", bcastall_command))
        application.add_handler(CommandHandler("bcastself", bcastself_command))
        application.add_handler(CommandHandler("stopbroadcast", stop_broadcast_command))
        application.add_handler(
            MessageHandler(filters.CONTACT & filters.ChatType.PRIVATE, handle_contact_for_command)
        )
        application.add_handler(
            MessageHandler(
                filters.FORWARDED & filters.ChatType.PRIVATE,
                handle_forwarded_message_for_command,
            )
        )
        application.add_handler(
            MessageHandler(
                filters.TEXT & (~filters.COMMAND) & filters.ChatType.GROUPS,
                handle_message,
            )
        )
        application.add_handler(
            MessageHandler(
                filters.CAPTION & (~filters.COMMAND) & filters.ChatType.GROUPS,
                handle_message,
            )
        )
        application.add_handler(
            MessageHandler(
                filters.FORWARDED
                & filters.ChatType.PRIVATE
                & filters.User(user_id=AUTHORIZED_USERS)
                & ~filters.COMMAND,
                handle_forwarded_channel_message,
            )
        )
        application.add_handler(CallbackQueryHandler(callbackquery_handler))
        application.add_handler(
            ChatMemberHandler(new_chat_members_handler, ChatMemberHandler.CHAT_MEMBER)
        )
        application.add_error_handler(on_error)

        # Schedule jobs
        if application.job_queue:
            cache_cleanup_interval_s = CACHE_TTL_SECONDS * 2 if CACHE_TTL_SECONDS > 0 else 3600
            application.job_queue.run_repeating(
                cleanup_caches_job,
                interval=cache_cleanup_interval_s,
                first=10,
            )
            logger.info(
                getattr(
                    patterns,
                    'CACHE_CLEANUP_JOB_SCHEDULED_MESSAGE',
                    'Cache cleanup scheduled.',
                ).format(interval=format_duration(cache_cleanup_interval_s))
            )
            loop.run_until_complete(load_and_schedule_timed_broadcasts(application))
        else:
            logger.warning(
                getattr(patterns, 'JOBQUEUE_NOT_AVAILABLE_MESSAGE', 'JobQueue not available.')
            )

        logger.info(
            getattr(patterns, 'BOT_AWAKENS_MESSAGE', 'Bot awakens.').format(TG_VER=TG_VER)
        )
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            timeout=30,
            close_loop=False,
        )

    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt. Initiating shutdown...")
        SHUTTING_DOWN = True
    except InvalidToken:
        logger.critical("Invalid Bot Token. Exiting.")
        SHUTTING_DOWN = True
    except Exception as e:
        logger.critical(f"Critical error during startup or polling: {e}", exc_info=True)
        SHUTTING_DOWN = True
    finally:
        logger.info("Shutting down...")
        if 'application' in locals() and application.running:
            logger.info("Stopping application...")
            try:
                if loop and not loop.is_closed():
                    loop.run_until_complete(application.stop())
                    logger.info("Application stopped.")
                    loop.run_until_complete(application.shutdown())
                    logger.info("Application shut down.")
                else:
                    logger.warning("Event loop unavailable for application stop/shutdown.")
            except Exception as e_shutdown:
                logger.error(f"Error during application shutdown: {e_shutdown}", exc_info=True)

        logger.info("Closing database connection pool...")
        try:
            if loop and not loop.is_closed():
                loop.run_until_complete(close_db_pool())
                logger.info("Database pool closed.")
            else:
                logger.warning("Event loop unavailable for database pool closure.")
        except Exception as e_db_close:
            logger.error(f"Error closing database pool: {e_db_close}", exc_info=True)

        try:
            if loop and not loop.is_closed():
                logger.info("Cleaning up event loop...")
                tasks = [
                    t for t in asyncio.all_tasks(loop=loop)
                    if t is not asyncio.current_task(loop=loop)
                ]
                if tasks:
                    logger.info(f"Cancelling {len(tasks)} tasks...")
                    for task in tasks:
                        task.cancel()
                    loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                    logger.info("Tasks cancelled.")
                loop.run_until_complete(loop.shutdown_asyncgens())
                logger.info("Async generators shut down.")
                loop.close()
                logger.info("Event loop closed.")
            else:
                logger.debug("Event loop already closed or not created.")
        except Exception as e_loop_cleanup:
            logger.error(f"Error during loop cleanup: {e_loop_cleanup}", exc_info=True)

        logger.info(
            getattr(patterns, 'BOT_RESTS_MESSAGE', 'Bot rests. Farewell!')
        )

if __name__ == "__main__":
    try:
        main()
    except Exception as e_top:
        logger.critical(f"Top-level unhandled exception: {e_top}", exc_info=True)
        LOG_FILE_PATH = "bot.log"
        if LOG_FILE_PATH:
            try:
                with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
                    f.write(f"\n--- CRITICAL FAILURE AT {datetime.now()} ---\n")
                    import traceback
                    traceback.print_exc(file=f)
                    f.write(f"--- END CRITICAL FAILURE ---\n")
            except Exception as e_log_final:
                print(f"Failed to write final error to log: {e_log_final}")