# database_ops.py
import aiosqlite
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple, List, Any
import json
import re
import asyncio
from logging import getLogger
from telegram.ext import ContextTypes  # Added for ContextTypes in deactivate_expired_restrictions_job

# --- Logger Setup ---
logger = logging.getLogger(__name__)

# --- Global Variables ---
db_pool: Optional[aiosqlite.Connection] = None
SHUTTING_DOWN: bool = False
BAD_ACTOR_EXPIRY_SECONDS: int = 0  # Default: Permanent (0 seconds)

# --- Configuration Defaults ---
DEFAULT_PUNISH_ACTION: str = "mute"
DEFAULT_PUNISH_DURATION_PROFILE_SECONDS: int = 0
DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS: int = 3600  # 1 hour
DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS: int = 0
DEFAULT_LANGUAGE_CODE: str = "en"

# --- Time Unit Constants ---
SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
DAY = 24 * HOUR

# --- Database Connection Management ---

async def init_db(
    db_path: str = "bards_sentinel_async.db",
    default_punish_action: str = DEFAULT_PUNISH_ACTION,
    default_punish_durations: Dict[str, int] = None,
    default_lang_code: str = DEFAULT_LANGUAGE_CODE,
) -> None:
    """Initialize the SQLite database connection and schema."""
    global db_pool
    try:
        if db_pool is not None:
            logger.warning("Database pool already initialized.")
            return

        # Set default punish durations
        default_punish_durations = default_punish_durations or {
            "profile": DEFAULT_PUNISH_DURATION_PROFILE_SECONDS,
            "message": DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS,
            "mention_profile": DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS,
        }
        p_action = default_punish_action
        dur_profile = default_punish_durations.get("profile", DEFAULT_PUNISH_DURATION_PROFILE_SECONDS)
        dur_message = default_punish_durations.get("message", DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS)
        dur_mention = default_punish_durations.get("mention_profile", DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS)
        lang_code = default_lang_code

        # Initialize connection
        db_pool = await aiosqlite.connect(db_path, isolation_level=None)
        db_pool.row_factory = aiosqlite.Row
        logger.info(f"Database connection initialized at {db_path}")

        # Enable WAL mode and foreign keys
        await db_pool.execute("PRAGMA journal_mode=WAL;")
        await db_pool.execute("PRAGMA foreign_keys=ON;")

        # Create schema
        await db_pool.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS groups (
                group_id INTEGER PRIMARY KEY,
                group_name TEXT,
                added_at TEXT DEFAULT (datetime('now')),
                punish_action TEXT DEFAULT '{p_action}',
                punish_duration_profile INTEGER DEFAULT {dur_profile},
                punish_duration_message INTEGER DEFAULT {dur_message},
                punish_duration_mention_profile INTEGER DEFAULT {dur_mention},
                language_code TEXT DEFAULT '{lang_code}'
            );

            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                interacted_at TEXT DEFAULT (datetime('now')),
                has_started_bot INTEGER DEFAULT 0 CHECK (has_started_bot IN (0, 1)),
                language_code TEXT DEFAULT '{lang_code}'
            );

            CREATE TABLE IF NOT EXISTS exempt_users (
                user_id INTEGER,
                chat_id INTEGER,
                PRIMARY KEY (user_id, chat_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (chat_id) REFERENCES groups(group_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS feature_control (
                feature_name TEXT PRIMARY KEY,
                is_enabled INTEGER DEFAULT 1 CHECK (is_enabled IN (0, 1))
            );

            CREATE TABLE IF NOT EXISTS bad_actors (
                user_id INTEGER PRIMARY KEY,
                reason TEXT,
                added_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS timed_broadcasts (
                job_name TEXT PRIMARY KEY,
                target_type TEXT NOT NULL,
                target_id INTEGER,
                message_text TEXT NOT NULL,
                interval_seconds INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                next_run_time REAL NOT NULL,
                first_run_time INTEGER,
                active INTEGER NOT NULL DEFAULT 1,
                markup_json TEXT,
                FOREIGN KEY (target_id) REFERENCES groups(group_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS unmute_attempts (
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                attempt_timestamp REAL NOT NULL,
                PRIMARY KEY (user_id, chat_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (chat_id) REFERENCES groups(group_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS group_admin_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                changer_user_id INTEGER,
                old_status TEXT,
                new_status TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (chat_id) REFERENCES groups(group_id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (changer_user_id) REFERENCES users(user_id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS bot_restrictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                restriction_type TEXT NOT NULL,
                applied_at TEXT NOT NULL,
                expires_at TEXT,
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                reason TEXT,
                applied_by_admin_id INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (chat_id) REFERENCES groups(group_id) ON DELETE CASCADE,
                FOREIGN KEY (applied_by_admin_id) REFERENCES users(user_id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS observed_admin_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                sender_user_id INTEGER NOT NULL,
                command_text TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                detected_action_type TEXT,
                target_user_id INTEGER,
                duration_seconds INTEGER,
                parsed_reason TEXT,
                FOREIGN KEY (chat_id) REFERENCES groups(group_id) ON DELETE CASCADE,
                FOREIGN KEY (sender_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (target_user_id) REFERENCES users(user_id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS command_cooldowns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                command_name TEXT NOT NULL,
                last_used_timestamp TEXT NOT NULL,
                FOREIGN KEY (chat_id) REFERENCES groups(group_id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_bot_restrictions_chat_type_active ON bot_restrictions (chat_id, restriction_type, is_active);
            CREATE INDEX IF NOT EXISTS idx_bot_restrictions_user_chat_type_active ON bot_restrictions (user_id, chat_id, restriction_type, is_active);
            CREATE INDEX IF NOT EXISTS idx_bot_restrictions_expiry ON bot_restrictions (expires_at);
            CREATE INDEX IF NOT EXISTS idx_observed_admin_actions_chat_sender ON observed_admin_actions (chat_id, sender_user_id);
            CREATE INDEX IF NOT EXISTS idx_observed_admin_actions_target_user ON observed_admin_actions (target_user_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_command_cooldowns_chat_user_cmd ON command_cooldowns (chat_id, user_id, command_name);
            """
        )

        # Initialize feature_control
        default_features = [
            ("maintenance_mode_active", 0),
            ("link_detection", 1),
            ("bad_actor_check", 1),
            ("message_processing", 1),
        ]
        for feature_name, is_enabled in default_features:
            await db_pool.execute(
                "INSERT OR IGNORE INTO feature_control (feature_name, is_enabled) VALUES (?, ?)",
                (feature_name, is_enabled)
            )
            logger.debug(f"Initialized feature_control: {feature_name} = {is_enabled}")

        # Verify foreign key integrity
        async with db_pool.execute("PRAGMA foreign_key_check;") as cursor:
            violations = await cursor.fetchall()
            if violations:
                logger.warning(f"Foreign key violations detected: {violations}")

        await db_pool.commit()
        logger.info("Database initialized successfully.")

    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)
        if db_pool is not None:
            await db_pool.close()
        db_pool = None
        raise

async def close_db_pool() -> None:
    """Close the database connection pool."""
    global db_pool, SHUTTING_DOWN
    SHUTTING_DOWN = True
    if db_pool is not None:
        try:
            async with db_pool.cursor() as cursor:
                await cursor.execute("PRAGMA wal_checkpoint(FULL)")
            logger.info("Database WAL checkpoint performed before closing.")
            await db_pool.close()
            logger.info("Database connection pool closed.")
            db_pool = None
        except Exception as e:
            logger.error(f"Error closing database pool: {e}", exc_info=True)
    else:
        logger.warning("Database pool was already closed or never initialized.")

# --- Database Operation Wrappers ---

async def db_execute(sql: str, params: Tuple = ()) -> Optional[aiosqlite.Cursor]:
    """Execute an SQL statement with parameters."""
    global db_pool, SHUTTING_DOWN
    if SHUTTING_DOWN:
        return None
    if db_pool is None:
        logger.error("DB pool not initialized for db_execute")
        raise ConnectionError("Database pool not initialized")
    try:
        cursor = await db_pool.execute(sql, params)
        return cursor
    except aiosqlite.ProgrammingError as e:
        logger.error(f"DB programming error executing: {e} for SQL: {sql} with params: {params}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"DB execute error: {e} for SQL: {sql} with params: {params}", exc_info=True)
        raise

async def db_fetchone(sql: str, params: Tuple = ()) -> Optional[aiosqlite.Row]:
    """Fetch one row from the database."""
    global db_pool, SHUTTING_DOWN
    if SHUTTING_DOWN:
        return None
    if db_pool is None:
        logger.error("DB pool not initialized for db_fetchone")
        raise ConnectionError("Database pool not initialized")
    try:
        async with db_pool.cursor() as cursor:
            await cursor.execute(sql, params)
            return await cursor.fetchone()
    except aiosqlite.ProgrammingError as e:
        logger.error(f"DB programming error fetching one: {e} for SQL: {sql} with params: {params}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"DB fetchone error: {e} for SQL: {sql} with params: {params}", exc_info=True)
        raise

async def db_fetchall(sql: str, params: Tuple = ()) -> List[aiosqlite.Row]:
    """Fetch all rows from the database."""
    global db_pool, SHUTTING_DOWN
    if SHUTTING_DOWN:
        return []
    if db_pool is None:
        logger.error("DB pool not initialized for db_fetchall")
        raise ConnectionError("Database pool not initialized")
    try:
        async with db_pool.cursor() as cursor:
            await cursor.execute(sql, params)
            return await cursor.fetchall()
    except aiosqlite.ProgrammingError as e:
        logger.error(f"DB programming error fetching all: {e} for SQL: {sql} with params: {params}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"DB fetchall error: {e} for SQL: {sql} with params: {params}", exc_info=True)
        raise

# --- Database Interaction Functions ---

async def add_group(
    group_id: int,
    group_name: str,
    added_at: Optional[str] = None,
    lang_code: Optional[str] = None,
) -> None:
    """Add or update a group in the database."""
    added_at = added_at or datetime.now(timezone.utc).isoformat()
    effective_lang_code = lang_code or DEFAULT_LANGUAGE_CODE
    await db_execute(
        """INSERT OR IGNORE INTO groups (group_id, group_name, added_at, punish_action, punish_duration_profile, punish_duration_message, punish_duration_mention_profile, language_code)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            group_id,
            group_name,
            added_at,
            DEFAULT_PUNISH_ACTION,
            DEFAULT_PUNISH_DURATION_PROFILE_SECONDS,
            DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS,
            DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS,
            effective_lang_code,
        ),
    )
    await db_execute(
        """UPDATE groups SET group_name = ?, language_code = ? WHERE group_id = ?""",
        (group_name, effective_lang_code, group_id),
    )
    logger.debug(f"Added/Updated group {group_id} ('{group_name}') in DB.")

async def remove_group_from_db(group_id: int) -> None:
    """Remove a group and its related data from the database."""
    async with db_pool.execute("BEGIN") as cursor:
        await db_execute("DELETE FROM groups WHERE group_id = ?", (group_id,))
        await db_execute("DELETE FROM exempt_users WHERE chat_id = ?", (group_id,))
        await db_execute("DELETE FROM bot_restrictions WHERE chat_id = ?", (group_id,))
        await db_execute("DELETE FROM observed_admin_actions WHERE chat_id = ?", (group_id,))
        await db_execute("DELETE FROM command_cooldowns WHERE chat_id = ?", (group_id,))
        await db_execute(
            "DELETE FROM timed_broadcasts WHERE target_type = 'specific_group' AND target_id = ?",
            (group_id,),
        )
    logger.debug(f"Removed group {group_id} and related data from DB.")

async def add_user(
    user_id: int,
    username: str = "",
    first_name: str = "",
    last_name: str = "",
    interacted_at: Optional[str] = None,
    has_started_bot: bool = False,
    lang_code: Optional[str] = None,
) -> None:
    """Add or update a user in the database."""
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    interacted_at = interacted_at or datetime.now(timezone.utc).isoformat()
    effective_lang_code = lang_code or DEFAULT_LANGUAGE_CODE
    username_cleaned = username or None
    first_name_cleaned = first_name or None
    last_name_cleaned = last_name or None

    await db_execute(
        """INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, interacted_at, has_started_bot, language_code)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            username_cleaned,
            first_name_cleaned,
            last_name_cleaned,
            interacted_at,
            1 if has_started_bot else 0,
            effective_lang_code,
        ),
    )

    update_sql = "UPDATE users SET username = ?, first_name = ?, last_name = ?, interacted_at = ?"
    update_params: List[Any] = [username_cleaned, first_name_cleaned, last_name_cleaned, interacted_at]
    if has_started_bot:
        update_sql += ", has_started_bot = 1"
    if lang_code is not None:
        update_sql += ", language_code = ?"
        update_params.append(effective_lang_code)
    update_sql += " WHERE user_id = ?"
    update_params.append(user_id)

    await db_execute(update_sql, tuple(update_params))
    logger.debug(f"Processed user {user_id} ('{username}'): Inserted/Updated in DB.")

async def mark_user_started_bot(user_id: int, lang_code: Optional[str] = None) -> None:
    """Mark a user as having started the bot."""
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    interacted_at = datetime.now(timezone.utc).isoformat()
    effective_lang_code = lang_code or DEFAULT_LANGUAGE_CODE
    await db_execute(
        """INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, interacted_at, has_started_bot, language_code)
           VALUES (?, '', '', '', ?, 1, ?)""",
        (user_id, interacted_at, effective_lang_code),
    )
    update_sql = "UPDATE users SET has_started_bot = 1, interacted_at = ?"
    update_params: List[Any] = [interacted_at]
    if lang_code is not None:
        update_sql += ", language_code = ?"
        update_params.append(effective_lang_code)
    update_sql += " WHERE user_id = ?"
    update_params.append(user_id)
    await db_execute(update_sql, tuple(update_params))
    logger.debug(f"Marked user {user_id} as having started the bot.")

async def get_group_punish_action(group_id: int) -> str:
    """Get the punish action for a group."""
    row = await db_fetchone("SELECT punish_action FROM groups WHERE group_id = ?", (group_id,))
    return row["punish_action"] if row and row["punish_action"] else DEFAULT_PUNISH_ACTION

async def set_group_punish_action_async(group_id: int, group_name: str, action: str) -> None:
    """Set the punish action for a group."""
    await add_group(group_id, group_name)
    await db_execute("UPDATE groups SET punish_action = ? WHERE group_id = ?", (action, group_id))
    logger.debug(f"Set punish action for group {group_id} to {action}")

async def get_group_punish_duration_for_trigger(group_id: int, trigger_type: str) -> int:
    """Get the punish duration for a specific trigger type in a group."""
    column_map = {
        "profile": ("punish_duration_profile", DEFAULT_PUNISH_DURATION_PROFILE_SECONDS),
        "message": ("punish_duration_message", DEFAULT_PUNISH_DURATION_MESSAGE_SECONDS),
        "mention_profile": ("punish_duration_mention_profile", DEFAULT_PUNISH_DURATION_MENTION_PROFILE_SECONDS),
    }
    if trigger_type not in column_map:
        logger.warning(f"Unknown trigger type '{trigger_type}' for group {group_id}.")
        return 0
    column_name, default_duration = column_map[trigger_type]
    row = await db_fetchone(f"SELECT {column_name} FROM groups WHERE group_id = ?", (group_id,))
    return row[column_name] if row and row[column_name] is not None else default_duration

async def set_group_punish_duration_for_trigger_async(
    group_id: int, group_name: str, trigger_type: str, duration_s: int
) -> None:
    """Set the punish duration for a specific trigger type in a group."""
    column_map = {
        "profile": "punish_duration_profile",
        "message": "punish_duration_message",
        "mention_profile": "punish_duration_mention_profile",
    }
    if trigger_type not in column_map:
        logger.warning(f"Unknown trigger type '{trigger_type}' for group {group_id}.")
        return
    column_name = column_map(trigger_type)
    await add_group(group_id, group_name)
    await db_execute(f"UPDATE groups SET {column_name} = ? WHERE group_id = ?", (duration_s, group_id))
    logger.debug(f"Set punish duration for '{trigger_type}' in group {group_id} to {duration_s}s")

async def set_all_group_punish_durations_async(group_id: int, group_name: str, duration_s: int) -> None:
    """Set punish durations for all trigger types in a group."""
    await add_group(group_id, group_name)
    await db_execute(
        """UPDATE groups SET punish_duration_profile = ?, punish_duration_message = ?, punish_duration_mention_profile = ?
           WHERE group_id = ?""",
        (duration_s, duration_s, duration_s, group_id),
    )
    logger.debug(f"Set all punish durations in group {group_id} to {duration_s}s")

async def add_group_user_exemption(group_id: int, user_id: int) -> None:
    """Add a user exemption for a specific group."""
    await db_execute(
        "INSERT OR IGNORE INTO exempt_users (chat_id, user_id) VALUES (?, ?)",
        (group_id, user_id),
    )
    logger.debug(f"Added exemption for user {user_id} in group {group_id}.")

async def remove_group_user_exemption(group_id: int, user_id: int) -> bool:
    """Remove a user exemption for a specific group."""
    cursor = await db_execute(
        "DELETE FROM exempt_users WHERE chat_id = ? AND user_id = ?",
        (group_id, user_id),
    )
    if cursor:
        logger.debug(f"Removed exemption for user {user_id} in group {group_id}. Rows deleted: {cursor.rowcount}")
        return cursor.rowcount > 0
    logger.warning("Failed to remove exemption due to shutdown or error.")
    return False

async def is_user_exempt_in_group(group_id: int, user_id: int) -> bool:
    """Check if a user is exempt in a specific group."""
    row = await db_fetchone(
        "SELECT 1 FROM exempt_users WHERE chat_id = ? AND user_id = ?",
        (group_id, user_id),
    )
    return bool(row)

async def get_feature_state(feature_name: str, default: bool = True) -> bool:
    """Get the enabled state of a feature."""
    row = await db_fetchone(
        "SELECT is_enabled FROM feature_control WHERE feature_name = ?",
        (feature_name,),
    )
    return bool(row["is_enabled"]) if row and row["is_enabled"] is not None else default

async def set_feature_state(feature_name: str, is_enabled: bool) -> None:
    """Set the enabled state of a feature."""
    await db_execute(
        """INSERT OR REPLACE INTO feature_control (feature_name, is_enabled)
           VALUES (?, ?)""",
        (feature_name, 1 if is_enabled else 0),
    )
    logger.debug(f"Set feature '{feature_name}' state to {is_enabled}.")

async def get_all_groups_from_db(batch_size: int = 100) -> List[int]:
    """Retrieve all group IDs from the database."""
    rows = await db_fetchall("SELECT group_id FROM groups")
    return [row["group_id"] for row in rows] if rows else []

async def get_all_users_from_db(started_only: bool = False, batch_size: int = 500) -> List[int]:
    """Retrieve all user IDs from the database."""
    sql = "SELECT user_id FROM users" + (" WHERE has_started_bot = 1" if started_only else "")
    rows = await db_fetchall(sql)
    return [row["user_id"] for row in rows] if rows else []

async def get_all_groups_count() -> int:
    """Get the total count of groups."""
    row = await db_fetchone("SELECT COUNT(*) FROM groups")
    return row[0] if row else 0

async def get_all_users_count(started_only: bool = False) -> int:
    """Get the total count of users."""
    sql = "SELECT COUNT(*) FROM users" + (" WHERE has_started_bot = 1" if started_only else "")
    row = await db_fetchone(sql)
    return row[0] if row else 0

async def add_unmute_attempt(user_id: int, chat_id: int) -> None:
    """Record an unmute attempt timestamp."""
    now_timestamp = time.time()
    await db_execute(
        """INSERT OR REPLACE INTO unmute_attempts (user_id, chat_id, attempt_timestamp)
           VALUES (?, ?, ?)""",
        (user_id, chat_id, now_timestamp),
    )
    logger.debug(f"Recorded unmute attempt for user {user_id} in chat {chat_id}.")

async def get_last_unmute_attempt_time(user_id: int, chat_id: int) -> Optional[float]:
    """Fetch the timestamp of the last unmute attempt."""
    row = await db_fetchone(
        "SELECT attempt_timestamp FROM unmute_attempts WHERE user_id = ? AND chat_id = ?",
        (user_id, chat_id),
    )
    return float(row["attempt_timestamp"]) if row and row["attempt_timestamp"] is not None else None

async def add_bad_actor(user_id: int, reason: str) -> None:
    """Add a user to the bad_actors list."""
    added_at = datetime.now(timezone.utc).isoformat()
    await db_execute(
        """INSERT OR REPLACE INTO bad_actors (user_id, reason, added_at)
           VALUES (?, ?, ?)""",
        (user_id, reason[:1000], added_at),
    )
    logger.debug(f"Added/Updated bad actor {user_id} in DB.")

async def is_bad_actor(user_id: int) -> bool:
    """Check if a user is a bad actor with expiry."""
    row = await db_fetchone("SELECT added_at FROM bad_actors WHERE user_id = ?", (user_id,))
    if not row:
        return False
    if BAD_ACTOR_EXPIRY_SECONDS <= 0:
        logger.debug(f"User {user_id} is a permanent bad actor.")
        return True
    try:
        added_at = datetime.fromisoformat(row["added_at"]).astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        time_difference = (now - added_at).total_seconds()
        if time_difference <= BAD_ACTOR_EXPIRY_SECONDS:
            expiry_time = added_at + timedelta(seconds=BAD_ACTOR_EXPIRY_SECONDS)
            time_left = (expiry_time - now).total_seconds()
            logger.debug(
                f"User {user_id} is a temporary bad actor (expires at {expiry_time.isoformat()}). Time left: {format_duration(int(time_left))}."
            )
            return True
        await db_execute("DELETE FROM bad_actors WHERE user_id = ?", (user_id,))
        logger.info(f"Removed expired bad actor {user_id} from DB.")
        return False
    except ValueError:
        logger.warning(f"Invalid added_at date for user {user_id}. Treating as permanent.")
        return True
    except Exception as e:
        logger.error(f"Error checking bad actor status for {user_id}: {e}", exc_info=True)
        return False

async def add_timed_broadcast_to_db(
    job_name: str,
    target_type: str,
    message_text: str,
    interval_seconds: int,
    next_run_time: float,
    markup_json: Optional[str] = None,
    target_id: Optional[int] = None,
) -> None:
    """Add or update a timed broadcast configuration."""
    created_at = datetime.now(timezone.utc).isoformat()
    effective_markup_json = markup_json if markup_json else None
    await db_execute(
        """INSERT OR REPLACE INTO timed_broadcasts (job_name, target_type, target_id, message_text, interval_seconds, created_at, next_run_time, markup_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            job_name,
            target_type,
            target_id,
            message_text,
            interval_seconds,
            created_at,
            next_run_time,
            effective_markup_json,
        ),
    )
    logger.debug(f"Added/Updated timed broadcast '{job_name}' in DB.")

async def remove_timed_broadcast_from_db(job_name: str) -> None:
    """Remove a timed broadcast configuration."""
    cursor = await db_execute("DELETE FROM timed_broadcasts WHERE job_name = ?", (job_name,))
    logger.debug(
        f"{'Removed' if cursor and cursor.rowcount > 0 else 'Not found'} timed broadcast '{job_name}'."
    )

async def get_all_timed_broadcasts_from_db() -> List[aiosqlite.Row]:
    """Retrieve all active timed broadcasts from the database."""
    return await db_fetchall(
        "SELECT job_name, target_type, message_text, interval_seconds, first_run_time FROM timed_broadcasts WHERE active = 1"
    )

async def log_action_db(
    action_type: str,
    target_user_id: Optional[int],
    chat_id: Optional[int],
    reason: str,
    duration_seconds: Optional[int] = None,
    sender_user_id: Optional[int] = None,
    command_text: Optional[str] = None,
) -> None:
    """Log bot or admin actions."""
    timestamp_iso = datetime.now(timezone.utc).isoformat()
    effective_chat_id = int(chat_id) if chat_id is not None else None
    effective_target_user_id = int(target_user_id) if target_user_id is not None else None
    effective_sender_user_id = int(sender_user_id) if sender_user_id is not None else None
    await db_execute(
        """INSERT INTO observed_admin_actions (chat_id, sender_user_id, command_text, timestamp, detected_action_type, target_user_id, duration_seconds, parsed_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            effective_chat_id,
            effective_sender_user_id,
            command_text or f"Bot Action: {action_type}",
            timestamp_iso,
            action_type.lower(),
            effective_target_user_id,
            duration_seconds,
            reason[:1000],
        ),
    )
    logger.debug(f"Logged action '{action_type}' for user {effective_target_user_id} in chat {effective_chat_id}.")

async def deactivate_expired_restrictions_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deactivate expired bot restrictions in the database."""
    global db_pool, SHUTTING_DOWN
    logger.info("Running job: Deactivating expired restrictions...")
    
    if SHUTTING_DOWN:
        logger.warning("Cannot deactivate expired restrictions: Bot is shutting down")
        return
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
            async with db_pool.execute(
                f"UPDATE bot_restrictions SET is_active = 0 WHERE id IN ({','.join('?' * len(ids_to_deactivate))})",
                ids_to_deactivate,
            ):
                await db_pool.commit()  # Ensure changes are committed
            logger.info(f"Deactivated {len(ids_to_deactivate)} expired restrictions.")
            
            # Notify Telegram if context is available
            if hasattr(context, 'bot'):
                for restriction in expired_restrictions:
                    try:
                        await context.bot.send_message(
                            chat_id=restriction["chat_id"],
                            text=f"User {restriction['user_id']} restriction ({restriction['restriction_type']}) has expired and was deactivated."
                        )
                    except Exception as e:
                        logger.error(f"Failed to notify chat {restriction['chat_id']} for user {restriction['user_id']}: {e}")
        else:
            logger.debug("No expired restrictions found to deactivate.")
    except Exception as e:
        logger.error(f"Error in deactivate_expired_restrictions_job: {e}", exc_info=True)
        await db_pool.rollback()  # Rollback on error

# --- Utility Functions ---

def parse_duration(duration_str: str) -> Optional[int]:
    """Parse a duration string into seconds."""
    if not isinstance(duration_str, str):
        return None
    duration_str = duration_str.strip().lower()
    if duration_str in ("0", "inf", "permanent"):
        return 0
    regex = re.compile(r"^(\d+)(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)$")
    match = regex.match(duration_str)
    if not match:
        return None
    value, unit = match.groups()
    try:
        value = int(value)
        if value < 0:
            return None
        unit_multipliers = {
            's': SECOND,
            'm': MINUTE,
            'h': HOUR,
            'd': DAY,
        }
        return value * unit_multipliers.get(unit[0], None)
    except (ValueError, TypeError):
        return None

def format_duration(seconds: int) -> str:
    """Format seconds into a human-readable string."""
    if seconds < 0:
        return "N/A"
    if seconds == 0:
        return "Permanent"
    units = [
        ("d", DAY),
        ("h", HOUR),
        ("m", MINUTE),
        ("s", SECOND),
    ]
    parts = []
    remaining = seconds
    for unit, unit_seconds in units:
        if remaining >= unit_seconds:
            value = remaining // unit_seconds
            parts.append(f"{value}{unit}")
            remaining %= unit_seconds
    return " ".join(parts) or f"{seconds}s"

async def get_user_language_code(user_id: int) -> Optional[str]:
    """Get the language code for a user."""
    row = await db_fetchone("SELECT language_code FROM users WHERE user_id = ?", (user_id,))
    return row["language_code"] if row else None

async def set_user_language_code(user_id: int, lang_code: str) -> None:
    """Set the language code for a user."""
    await db_execute("UPDATE users SET language_code = ? WHERE user_id = ?", (lang_code, user_id))
    logger.debug(f"Set language code for user {user_id} to {lang_code}")

async def vacuum_db() -> None:
    """Vacuum the database to optimize space."""
    if db_pool is None:
        logger.error("Cannot vacuum database: db_pool is None")
        return
    try:
        await db_pool.execute("VACUUM")
        logger.info("Database vacuumed successfully.")
    except Exception as e:
        logger.error(f"Error vacuuming database: {e}", exc_info=True)