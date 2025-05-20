import re

# --- Configuration Variables ---
MIN_USERNAME_LENGTH = 5
DEFAULT_CONFIG = {
    "BAD_ACTOR_EXPIRY_SECONDS": "86400",  # 1 day
    "UNMUTE_RATE_LIMIT_SECONDS": "300",   # 5 minutes
    "UNMUTE_ME_RATE_LIMIT_SECONDS": "3600",  # 1 hour
    "BULK_COMMAND_COOLDOWN_SECONDS": "3600",  # 1 hour
    "UNMUTEALL_TARGET_BOT_MUTES_ONLY": "True",
    "GUNMUTEALL_TARGET_BOT_MUTES_ONLY": "True",
    "UNBANALL_TARGET_BOT_BANS_ONLY": "True",
}
LANGUAGES = {
    "english": {"name": "English", "flag": "🇺🇸", "strings": {}},
    "español": {"name": "Español", "flag": "🇪🇸", "strings": {}},
    "hindi": {"name": "हिन्दी", "flag": "🇮🇳", "strings": {}},
}
LANG_CALLBACK_PREFIX = "setlang_"
LANG_PAGE_SIZE = 6

# Define dialogue list constants
MESSAGE_CONTENT_DIALOGUES_LIST = "MESSAGE_CONTENT_DIALOGUES_LIST"
MENTION_VIOLATION_DIALOGUES_LIST = "MENTION_VIOLATION_DIALOGUES_LIST"
SENDER_PROFILE_VIOLATION_REASON = "SENDER_PROFILE_VIOLATION_REASON"
MESSAGE_CONTENT_DIALOGUES_LIST = "MESSAGE_CONTENT_DIALOGUES_LIST"
MENTION_VIOLATION_DIALOGUES_LIST = "MENTION_VIOLATION_DIALOGUES_LIST"
MESSAGE_VIOLATION_REASON = "MESSAGE_VIOLATION_REASON"
MENTIONED_USER_PROFILE_VIOLATION_REASON = "MENTIONED_USER_PROFILE_VIOLATION_REASON"
NEW_USER_PROFILE_VIOLATION_REASON = "NEW_USER_PROFILE_VIOLATION_REASON"
MESSAGE_CONTENT_DIALOGUES_LIST = "MESSAGE_CONTENT_DIALOGUES_LIST"
MENTION_VIOLATION_DIALOGUES_LIST = "MENTION_VIOLATION_DIALOGUES_LIST"
SENDER_IS_BAD_ACTOR_REASON = "SENDER_IS_BAD_ACTOR_REASON"
SENDER_PROFILE_VIOLATION_REASON = "SENDER_PROFILE_VIOLATION_REASON"

# --- Prohibited Links ---
PROHIBITED_LINKS = [
    "xvideos.com",
    "pornhub.com",
    "bit.ly/scam",
]

# --- Bot Mention Pattern ---
BOT_MENTION_PATTERN = re.compile(r"@[a-zA-Z0-9_]+[Bb][Oo][Tt]\b", re.IGNORECASE)

# --- URL Patterns ---
PATTERNS_SPECIFIC_URLS = [
    r"https?://(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,6}(?:[/?#][^\s<>\"']*)?",
    r"ftp://(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,6}(?:[/?#][^\s<>\"']*)?",
    r"ipfs://[a-zA-Z0-9]+(?:/[^\s<>\"']*)?",
    r"magnet:\?[^\s<>\"']+",
    r"\bwww\d{0,3}\.(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,6}(?:[/?#][^\s<>\"']*)?\b",
    r"https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?::\d+)?(?:/[^\s<>\"']*)?",
]
PATTERNS_TELEGRAM_LINKS = [
    r"\b(?:t\.me|telegram\.me|telegram\.dog)/[a-zA-Z0-9_]{5,32}(?:[/?][^\s]*)?\b",
    r"\b(?:t\.me|telegram\.me|telegram\.dog)/(?:joinchat/[a-zA-Z0-9_/\-]+|\+[a-zA-Z0-9_/\-]+)\b",
    r"\b(?:t\.me|telegram\.me|telegram\.dog)/[a-zA-Z0-9_]{5,32}\?(?:start|startgroup|startchannel|admin)=[^\s]*\b",
    r"\btg://resolve\?domain=[a-zA-Z0-9_]{5,32}(?:&(?:start|startgroup|admin)=[^\s]*)?\b",
    r"\b@[a-zA-Z0-9_]{5,32}\b",
]
COMMON_EVASION_TLDS = r"(?:com|net|org|info|biz|ru|de|uk|co|io|gg|me|xyz|club|site|online|shop|store|app|dev|live|stream|icu|top|buzz|guru)"
PATTERNS_EVASION_DOT = [
    r"\b[a-zA-Z0-9\-]+(?:\s*\[?\(?\s*(?:dot|d0t|\.|\u2024|\u002E)\s*\)?\]?|\s+(?:dot|d0t)\s+)[a-zA-Z0-9\-]+\." + COMMON_EVASION_TLDS + r"\b",
    r"\b[a-zA-Z0-9\-]+(?:\s*(?:%2E|%252E)\s*)[a-zA-Z0-9\-]+\." + COMMON_EVASION_TLDS + r"\b",
]
PATTERNS_ENCODED_URLS = [
    r"(?:data:[^\s;]+;base64,|(?:[A-Za-z0-9+/=]{20,}))",
]
FORBIDDEN_PATTERNS_LIST = PATTERNS_SPECIFIC_URLS + PATTERNS_TELEGRAM_LINKS + PATTERNS_EVASION_DOT + PATTERNS_ENCODED_URLS
PROHIBITED_URL_PATTERNS = [
    re.compile(pattern, re.IGNORECASE | re.UNICODE)
    for pattern in FORBIDDEN_PATTERNS_LIST
]

# --- Prohibited Keywords ---
PROHIBITED_KEYWORDS = [
    "join now", "click here", "sell", "crypto", "bitcoin", "invest", "trading", 
    "free money", "lottery", "giveaway",
]

# --- Forbidden Patterns ---
FORBIDDEN_WORDS = [
    r"\bb[i1!𝒊𝕚]\W*o+\b",  # bio
    r"\bs[e3]l{2,}\b",     # sell
    r"\bpro+\s*file+\b",   # profile
    r"\bch[i1!]\W*ld\b",   # child
    r"\bg\W*r\W*o\W*u\W*p\b",  # group
    r"\bchan+el+\b",       # channel
    r"\bcr[yу][pр][tт][o0]\b",  # crypto
    r"\bb[i1!][tт][cс][o0][i1!][nи]\b",  # bitcoin
    r"ब\W*ा\W*इ\W*यो",     # बायो (bio)
    r"ग\W*र\W*ू\W*प",      # ग्रूप (group)
    r"प\W*र\W*ो\W*फ\W*ा\W*ई\W*ल",  # प्रोफाइल (profile)
    r"च\W*ै\W*न\W*ल",     # चैनल (channel)
    r"\bبدون\W*سانسور\b",  # بدون سانسور (uncensored in Persian)
    r"\bممنوع\b",          # ممنوع (forbidden in Persian)
    r"\bغير\W*محجوب\b",   # غير محجوب (unblocked in Arabic)
    r"\bзаработок\b",      # заработок (earnings in Russian)
    r"\bбез\W*цензуры\b",  # без цензуры (uncensored in Russian)
]
WHITELIST_PATTERNS = [
    r"\bbio(?:tech|logy|graphy|informatics|medical|engineering)\b",
    r"\bprofile\s*(pic|picture|photo|link|url|settings|configuration)\b",
    r"\bn[o0]\W*b[i1!𝒊𝕚]o\b",
    r"\bb[i1!𝒊𝕚]o\W*dekh\W*kar\W*kya\W*karoge\b",
    r"बायो\W*देख\W*कर\W*क्या\W*करोगे\b",
]
SUSPICIOUS_PATTERNS = [
    re.compile(pattern, re.IGNORECASE | re.UNICODE)
    for pattern in FORBIDDEN_WORDS
] + [
    re.compile(r"\b\d{5,}\b", re.IGNORECASE),
    re.compile(r"[^\w\s]{5,}", re.IGNORECASE),
    re.compile(r"(?:💰|🚀|🎁){3,}", re.UNICODE),
    re.compile(r"https?://[^\s<>\"']+\.(?:exe|apk|bat|zip|rar)\b", re.IGNORECASE),
]

# --- Fast Payout Keywords ---
FAST_PAYOUT_KEYWORDS = [
    "quick money", "fast cash", "instant payout", "earn now", "make money fast", "cashout quick",
]
FAST_PAYOUT_REGEX = re.compile(r"\b(payout|earn|cash|money)\s+\w+\b", re.IGNORECASE)


# --- User-Facing Text Strings ---
LANGUAGE_STRINGS = {
    "PUNISHMENT_MESSAGE_SENDER_ENGLISH": {
        "english": "<b>{user_mention}</b> has been {action_taken} due to {reason_detail}. {dialogue}",
        "hindi": "<b>{user_mention}</b> को {reason_detail} के कारण {action_taken} किया गया है। {dialogue}"
    },
    "START_MESSAGE_PRIVATE_BASE": {
        "english": "👋 Greetings from Bard's Sentinel!\n\nI employ advanced pattern recognition to safeguard your Telegram groups.",
        "hindi": "👋 बार्ड्स सेंटिनल से नमस्ते!\n\nमैं आपके टेलीग्राम समूहों को सुरक्षित रखने के लिए उन्नत पैटर्न पहचान का उपयोग करता हूँ।"
    },
    "ADMIN_ONLY_COMMAND_MESSAGE": {
        "english": "❌ This command is restricted to admins only.",
        "hindi": "❌ यह कमांड केवल व्यवस्थापकों के लिए प्रतिबंधित है।"
    },
    "SUPER_ADMIN_ONLY_COMMAND_MESSAGE": {
        "english": "❌ This command is restricted to super admins only.",
        "hindi": "❌ यह कमांड केवल सुपर व्यवस्थापकों के लिए प्रतिबंधित है।"
    },
    "COMMAND_GROUP_ONLY_MESSAGE": {
        "english": "❌ This command can only be used in groups.",
        "hindi": "❌ यह कमांड केवल समूहों में उपयोग की जा सकती है।"
    },
    "LOGGING_SETUP_MESSAGE": {
        "english": "Logging setup complete. Level: {log_level}, File: {log_file_path}",
        "hindi": "लॉगिंग सेटअप पूर्ण। स्तर: {log_level}, फाइल: {log_file_path}"
    },
    "CONFIG_NOT_FOUND_MESSAGE": {
        "english": "❌ config.ini not found at {config_file_name}. Creating a template config file.",
        "hindi": "❌ config.ini {config_file_name} पर नहीं मिला। एक टेम्पलेट कॉन्फिग फाइल बना रहा है।"
    },
    "CONFIG_TEMPLATE_CREATED_MESSAGE": {
        "english": "Template config file created at {config_file_name}. Please set the bot token.",
        "hindi": "टेम्पलेट कॉन्फिग फाइल {config_file_name} पर बनाई गई। कृपया बॉट टोकन सेट करें।"
    },
    "CONFIG_TOKEN_NOT_SET_MESSAGE": {
        "english": "❌ Bot token not set in {config_file_name}.",
        "hindi": "❌ {config_file_name} में बॉट टोकन सेट नहीं किया गया।"
    },
    "CONFIG_LOAD_SUCCESS_MESSAGE": {
        "english": "Config loaded successfully from {config_file_name}.",
        "hindi": "{config_file_name} से कॉन्फिग सफलतापूर्वक लोड किया गया।"
    },
    "NO_AUTHORIZED_USERS_WARNING": {
        "english": "⚠️ No authorized users found in config.",
        "hindi": "⚠️ कॉन्फिग में कोई अधिकृत उपयोगकर्ता नहीं मिला।"
    },
    "CONFIG_LOAD_ERROR_MESSAGE": {
        "english": "❌ Error loading config from {config_file_name}: {error}",
        "hindi": "❌ {config_file_name} से कॉन्फिग लोड करने में त्रुटि: {error}"
    },
    "UNMUTE_ME_CMD_USAGE": {
        "english": "Usage: /unmuteme or reply to this message to request unmute.",
        "hindi": "उपयोग: /unmuteme या इस संदेश का जवाब देकर अनम्यूट का अनुरोध करें।"
    },
    "UNMUTE_ME_MULTIPLE_GROUPS_FOUND": {
        "english": "Multiple groups found. Please specify a group.",
        "hindi": "कई समूह मिले। कृपया एक समूह निर्दिष्ट करें।"
    },
    "UNMUTE_ME_GROUP_NOT_FOUND": {
        "english": "Group not found or bot is not in the group.",
        "hindi": "समूह नहीं मिला या बॉट समूह में नहीं है।"
    },
    "UNMUTE_ME_PROFILE_ISSUE_PM": {
        "english": "Cannot unmute due to profile issues. Please fix your profile.",
        "hindi": "प्रोफाइल समस्याओं के कारण अनम्यूट नहीं किया जा सकता। कृपया अपनी प्रोफाइल ठीक करें।"
    },
    "UNMUTE_ME_CHANNEL_ISSUE_PM": {
        "english": "Cannot unmute due to channel issues. Please resolve them.",
        "hindi": "चैनल समस्याओं के कारण अनम्यूट नहीं किया जा सकता। कृपया उन्हें हल करें।"
    },
    "UNMUTE_ME_FAIL_GROUP_CMD_NO_MUTE": {
        "english": "You are not muted in this group.",
        "hindi": "आप इस समूह में म्यूट नहीं हैं।"
    },
    "UNMUTE_ME_SUCCESS_GROUP_CMD": {
        "english": "Unmute request processed successfully.",
        "hindi": "अनम्यूट अनुरोध सफलतापूर्वक संसाधित किया गया।"
    },
    "UNMUTE_SUCCESS_MESSAGE_GROUP": {
        "english": "<b>{user_mention}</b> has been unmuted.",
        "hindi": "<b>{user_mention}</b> को अनम्यूट कर दिया गया है।"
    },
    "UNMUTE_ME_FAIL_GROUP_CMD_OTHER": {
        "english": "Failed to process unmute request: {error}",
        "hindi": "अनम्यूट अनुरोध संसाधित करने में विफल: {error}"
    },
    "UNMUTE_ME_RATE_LIMITED_PM": {
        "english": "You are rate-limited. Try again later.",
        "hindi": "आप रेट-सीमित हैं। बाद में पुनः प्रयास करें।"
    },
    "UNMUTE_ME_NO_MUTES_FOUND_PM": {
        "english": "No active mutes found for you.",
        "hindi": "आपके लिए कोई सक्रिय म्यूट नहीं मिला।"
    },
    "UNMUTE_ME_COMPLETED_PM": {
        "english": "Unmute process completed.",
        "hindi": "अनम्यूट प्रक्रिया पूर्ण।"
    },
    "UNMUTE_ME_ALL_BOT_MUTES_BUTTON": {
        "english": "Unmute in All Groups",
        "hindi": "सभी समूहों में अनम्यूट करें"
    },
    "LANG_BUTTON_SELECT_LANGUAGE": {
        "english": "Select Language",
        "hindi": "भाषा चुनें"
    },
    "HELP_BUTTON_TEXT": {
        "english": "Help",
        "hindi": "सहायता"
    },
    "ADD_BOT_TO_GROUP_BUTTON_TEXT": {
        "english": "Add Bot to Group",
        "hindi": "बॉट को समूह में जोड़ें"
    },
    "JOIN_VERIFICATION_CHANNEL_BUTTON_TEXT": {
        "english": "Join Verification Channel",
        "hindi": "सत्यापन चैनल में शामिल हों"
    },
    "VERIFY_JOIN_BUTTON_TEXT": {
        "english": "Verify Join",
        "hindi": "जुड़ने की पुष्टि करें"
    },
    "START_MESSAGE_ADMIN_CONFIG": {
        "english": "Admin configuration options available.",
        "hindi": "व्यवस्थापक कॉन्फिगरेशन विकल्प उपलब्ध हैं।"
    },
    "START_MESSAGE_CHANNEL_VERIFY_INFO": {
        "english": "Join the verification channel to proceed.",
        "hindi": "आगे बढ़ने के लिए सत्यापन चैनल में शामिल हों।"
    },
    "START_MESSAGE_HELP_PROMPT": {
        "english": "Use /help for assistance.",
        "hindi": "सहायता के लिए /help का उपयोग करें।"
    },
    "START_MESSAGE_GROUP": {
        "english": "Bot is active in this group.",
        "hindi": "बॉट इस समूह में सक्रिय है।"
    },
    "RELOAD_ADMIN_CACHE_SUCCESS": {
        "english": "Admin cache reloaded successfully.",
        "hindi": "व्यवस्थापक कैश सफलतापूर्वक पुनः लोड किया गया।"
    },
    "RELOAD_ADMIN_CACHE_FAIL_FORBIDDEN": {
        "english": "Failed to reload admin cache: Forbidden.",
        "hindi": "व्यवस्थापक कैश पुनः लोड करने में विफल: निषिद्ध।"
    },
    "RELOAD_ADMIN_CACHE_FAIL_BADREQUEST": {
        "english": "Failed to reload admin cache: Bad request.",
        "hindi": "व्यवस्थापक कैश पुनः लोड करने में विफल: खराब अनुरोध।"
    },
    "RELOAD_ADMIN_CACHE_FAIL_ERROR": {
        "english": "Failed to reload admin cache: {error}",
        "hindi": "व्यवस्थापक कैश पुनः लोड करने में विफल: {error}"
    },
    "COMMAND_COOLDOWN_MESSAGE": {
        "english": "Command on cooldown. Try again in {seconds} seconds.",
        "hindi": "कमांड कूलडाउन पर है। {seconds} सेकंड बाद पुनः प्रयास करें।"
    },
    "ADMIN_ONLY_COMMAND_MESSAGE_RELOAD": {
        "english": "❌ Reload command is restricted to admins only.",
        "hindi": "❌ पुनः लोड कमांड केवल व्यवस्थापकों के लिए प्रतिबंधित है।"
    },
    "GMUTE_USAGE": {
        "english": "Usage: /gmute <user_id> [duration] [reason]",
        "hindi": "उपयोग: /gmute <user_id> [अवधि] [कारण]"
    },
    "GBAN_USAGE": {
        "english": "Usage: /gban <user_id> [reason]",
        "hindi": "उपयोग: /gban <user_id> [कारण]"
    },
    "USER_NOT_FOUND_MESSAGE": {
        "english": "User not found.",
        "hindi": "उपयोगकर्ता नहीं मिला।"
    },
    "INVALID_DURATION_FORMAT_MESSAGE": {
        "english": "Invalid duration format. Use e.g., 1h, 30m, 1d.",
        "hindi": "अमान्य अवधि प्रारूप। उदाहरण के लिए, 1h, 30m, 1d का उपयोग करें।"
    },
    "CANNOT_ACTION_SUPER_ADMIN": {
        "english": "Cannot perform action on super admin.",
        "hindi": "सुपर व्यवस्थापक पर कार्रवाई नहीं की जा सकती।"
    },
    "GMUTE_NO_GROUPS": {
        "english": "No groups found to apply gmute.",
        "hindi": "gmute लागू करने के लिए कोई समूह नहीं मिला।"
    },
    "GBAN_NO_GROUPS": {
        "english": "No groups found to apply gban.",
        "hindi": "gban लागू करने के लिए कोई समूह नहीं मिला।"
    },
    "GMUTE_STARTED": {
        "english": "Started global mute for user {user_id}.",
        "hindi": "उपयोगकर्ता {user_id} के लिए वैश्विक म्यूट शुरू किया गया।"
    },
    "GBAN_STARTED": {
        "english": "Started global ban for user {user_id}.",
        "hindi": "उपयोगकर्ता {user_id} के लिए वैश्विक प्रतिबंध शुरू किया गया।"
    },
    "GMUTE_DEFAULT_REASON": {
        "english": "Global mute by admin.",
        "hindi": "व्यवस्थापक द्वारा वैश्विक म्यूट।"
    },
    "GBAN_DEFAULT_REASON": {
        "english": "Global ban by admin.",
        "hindi": "व्यवस्थापक द्वारा वैश्विक प्रतिबंध।"
    },
    "GMUTE_COMPLETED": {
        "english": "Global mute completed for user {user_id}.",
        "hindi": "उपयोगकर्ता {user_id} के लिए वैश्विक म्यूट पूर्ण।"
    },
    "GBAN_COMPLETED": {
        "english": "Global ban completed for user {user_id}.",
        "hindi": "उपयोगकर्ता {user_id} के लिए वैश्विक प्रतिबंध पूर्ण।"
    },
    "BULK_UNMUTE_STARTED_STATUS": {
        "english": "Started bulk unmute for {count} users.",
        "hindi": "{count} उपयोगकर्ताओं के लिए बल्क अनम्यूट शुरू किया गया।"
    },
    "BULK_UNMUTE_PROGRESS": {
        "english": "Bulk unmute progress: {completed}/{total}.",
        "hindi": "बल्क अनम्यूट प्रगति: {completed}/{total}।"
    },
    "BULK_UNMUTE_COMPLETE": {
        "english": "Bulk unmute completed for {count} users.",
        "hindi": "{count} उपयोगकर्ताओं के लिए बल्क अनम्यूट पूर्ण।"
    },
    "BULK_UNBAN_STARTED_STATUS": {
        "english": "Started bulk unban for {count} users.",
        "hindi": "{count} उपयोगकर्ताओं के लिए बल्क अनबैन शुरू किया गया।"
    },
    "BULK_UNBAN_PROGRESS": {
        "english": "Bulk unban progress: {completed}/{total}.",
        "hindi": "बल्क अनबैन प्रगति: {completed}/{total}।"
    },
    "BULK_UNBAN_COMPLETE": {
        "english": "Bulk unban completed for {count} users.",
        "hindi": "{count} उपयोगकर्ताओं के लिए बल्क अनबैन पूर्ण।"
    },
    "BULK_UNMUTE_NO_TARGETS": {
        "english": "No users to unmute.",
        "hindi": "अनम्यूट करने के लिए कोई उपयोगकर्ता नहीं।"
    },
    "BULK_UNBAN_NO_TARGETS": {
        "english": "No users to unban.",
        "hindi": "अनबैन करने के लिए कोई उपयोगकर्ता नहीं।"
    },
    "BULK_UNMUTE_NO_GROUPS_GLOBAL": {
        "english": "No groups found for bulk unmute.",
        "hindi": "बल्क अनम्यूट के लिए कोई समूह नहीं मिला।"
    },
    "BULK_UNBAN_NO_GROUPS_GLOBAL": {
        "english": "No groups found for bulk unban.",
        "hindi": "बल्क अनबैन के लिए कोई समूह नहीं मिला।"
    },
    "BULK_UNMUTE_STARTED_GLOBAL_STATUS": {
        "english": "Started global bulk unmute for {count} users.",
        "hindi": "{count} उपयोगकर्ताओं के लिए वैश्विक बल्क अनम्यूट शुरू किया गया।"
    },
    "BULK_UNBAN_STARTED_GLOBAL_STATUS": {
        "english": "Started global bulk unban for {count} users.",
        "hindi": "{count} उपयोगकर्ताओं के लिए वैश्विक बल्क अनबैन शुरू किया गया।"
    },
    "BULK_UNMUTE_ALL_TASKS_DISPATCHED_GLOBAL": {
        "english": "All bulk unmute tasks dispatched globally.",
        "hindi": "सभी बल्क अनम्यूट कार्य वैश्विक रूप से भेजे गए।"
    },
    "BULK_UNBAN_ALL_TASKS_DISPATCHED_GLOBAL": {
        "english": "All bulk unban tasks dispatched globally.",
        "hindi": "सभी बल्क अनबैन कार्य वैश्विक रूप से भेजे गए।"
    },
    "BCASTSELF_MESSAGE_TEMPLATE": {
        "english": "Broadcast: {message}",
        "hindi": "प्रसारण: {message}"
    },
    "BCASTSELF_USER_USAGE_ERROR_ARGS": {
        "english": "Usage: /bcastselfusers <message>",
        "hindi": "उपयोग: /bcastselfusers <संदेश>"
    },
    "BCASTSELF_GROUP_USAGE_ERROR_ARGS": {
        "english": "Usage: /bcastselfgroups <message>",
        "hindi": "उपयोग: /bcastselfgroups <संदेश>"
    },
    "BCASTSELF_COMBINED_USAGE_ERROR_ARGS": {
        "english": "Usage: /bcastselfcombined <message>",
        "hindi": "उपयोग: /bcastselfcombined <संदेश>"
    },
    "BCASTSELF_STARTED_MESSAGE": {
        "english": "Broadcast started to {count} recipients.",
        "hindi": "{count} प्राप्तकर्ताओं के लिए प्रसारण शुरू हुआ।"
    },
    "BCASTSELF_COMPLETE_MESSAGE": {
        "english": "Broadcast completed to {count} recipients.",
        "hindi": "{count} प्राप्तकर्ताओं के लिए प्रसारण पूर्ण।"
    },
    "BCAST_SCHEDULED_USERS": {
        "english": "Scheduled broadcast to {count} users.",
        "hindi": "{count} उपयोगकर्ताओं के लिए प्रसारण शेड्यूल किया गया।"
    },
    "BCAST_SCHEDULED_GROUPS": {
        "english": "Scheduled broadcast to {count} groups.",
        "hindi": "{count} समूहों के लिए प्रसारण शेड्यूल किया गया।"
    },
    "BCAST_SCHEDULED_COMBINED": {
        "english": "Scheduled broadcast to {user_count} users and {group_count} groups.",
        "hindi": "{user_count} उपयोगकर्ताओं और {group_count} समूहों के लिए प्रसारण शेड्यूल किया गया।"
    },
    "JOBQUEUE_NOT_AVAILABLE_MESSAGE": {
        "english": "Job queue not available for scheduling.",
        "hindi": "शेड्यूलिंग के लिए जॉब क्यू उपलब्ध नहीं है।"
    },
    "BCASTSELF_STARTED_MESSAGE_COMBINED": {
        "english": "Combined broadcast started to {user_count} users and {group_count} groups.",
        "hindi": "{user_count} उपयोगकर्ताओं और {group_count} समूहों के लिए संयुक्त प्रसारण शुरू हुआ।"
    },
    "BCASTSELF_COMPLETE_MESSAGE_COMBINED": {
        "english": "Combined broadcast completed to {user_count} users and {group_count} groups.",
        "hindi": "{user_count} उपयोगकर्ताओं और {group_count} समूहों के लिए संयुक्त प्रसारण पूर्ण।"
    },
    "DB_DUMP_CAPTION": {
        "english": "Database dump: {timestamp}",
        "hindi": "डेटाबेस डंप: {timestamp}"
    },
    "DB_DUMP_ADMIN_NOTIFICATION": {
        "english": "Database dump generated and sent to admin.",
        "hindi": "डेटाबेस डंप जनरेट किया गया और व्यवस्थापक को भेजा गया।"
    },
    "PERMANENT_TEXT": {
        "english": "Permanent",
        "hindi": "स्थायी"
    },
    "NOT_APPLICABLE": {
        "english": "Not applicable",
        "hindi": "लागू नहीं"
    },
    "LANG_BUTTON_PREV": {
        "english": "Previous",
        "hindi": "पिछला"
    },
    "LANG_BUTTON_NEXT": {
        "english": "Next",
        "hindi": "अगला"
    },
    "LANG_SELECT_PROMPT": {
        "english": "Please select a language.",
        "hindi": "कृपया एक भाषा चुनें।"
    },
    "LANG_UPDATED_USER": {
        "english": "Language updated to {language} for user.",
        "hindi": "उपयोगकर्ता के लिए भाषा {language} में अपडेट की गई।"
    },
    "LANG_UPDATED_GROUP": {
        "english": "Language updated to {language} for group.",
        "hindi": "समूह के लिए भाषा {language} में अपडेट की गई।"
    },
    "LANG_MORE_COMING_SOON": {
        "english": "More languages coming soon!",
        "hindi": "जल्द ही और भाषाएँ उपलब्ध होंगी!"
    },
    "NEW_USER_PROFILE_VIOLATION_REASON": {
        "english": "Profile {field} violation: {issue_type}",
        "hindi": "प्रोफाइल {field} उल्लंघन: {issue_type}"
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
    "BADREQUEST_TO_ACT_SENDER": {
        "english": "Bad request when attempting to {action} sender {user_id} in chat {chat_id}: {e}",
        "hindi": "चैट {chat_id} में प्रेषक {user_id} को {action} करने का प्रयास करते समय खराब अनुरोध: {e}"
    },
    "ERROR_ACTING_SENDER": {
        "english": "Error {action} sender {user_id} in chat {chat_id}: {e}",
        "hindi": "चैट {chat_id} में प्रेषक {user_id} को {action} करने में त्रुटि: {e}"
    },
    "NO_PERMS_TO_ACT_MENTION": {
        "english": "Bot lacks permission to act on mentioned user {user_id} (@{username}) in chat {chat_id}.",
        "hindi": "बॉट को चैट {chat_id} में उल्लेखित उपयोगकर्ता {user_id} (@{username}) पर कार्रवाई करने की अनुमति नहीं है।"
    },
    "BADREQUEST_TO_ACT_MENTION": {
        "english": "Bad request when attempting to act on mentioned user {user_id} (@{username}) in chat {chat_id}: {e}",
        "hindi": "चैट {chat_id} में उल्लेखित उपयोगकर्ता {user_id} (@{username}) पर कार्रवाई करने का प्रयास करते समय खराब अनुरोध: {e}"
    },
    "ERROR_ACTING_MENTION": {
        "english": "Error acting on mentioned user {user_id} (@{username}) in chat {chat_id}: {e}",
        "hindi": "चैट {chat_id} में उल्लेखित उपयोगकर्ता {user_id} (@{username}) पर कार्रवाई करने में त्रुटि: {e}"
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
    "PUNISHMENT_MESSAGE_SENDER": {
        "english": "<b>{user_mention}</b> has been {action_taken} due to {reason_detail}. {dialogue}",
        "hindi": "<b>{user_mention}</b> को {action_taken} कर दिया गया है क्योंकि {reason_detail}। {dialogue}",
    },
    "PUNISHMENT_MESSAGE_MENTIONED": {
        "english": "The following users were muted for profile issues: {user_list} (Duration: {duration})",
        "hindi": "निम्नलिखित उपयोगकर्ताओं को प्रोफाइल समस्याओं के लिए म्यूट कर दिया गया: {user_list} (अवधि: {duration})",
    },
    "PUNISHMENT_DURATION_APPEND": {
        "english": " for {duration}.",
        "hindi": " {duration} के लिए।",
    },
    "NO_PERMS_TO_ACT_SENDER": {
        "english": "Bot lacks permissions to {action} user {user_id} in chat {chat_id}.",
        "hindi": "बॉट के पास चैट {chat_id} में उपयोगकर्ता {user_id} को {action} करने की अनुमति नहीं है।",
    },
    "ACTION_DEBOUNCED_SENDER": {
        "english": "Action on user {user_id} in chat {chat_id} is debounced.",
        "hindi": "चैट {chat_id} में उपयोगकर्ता {user_id} पर कार्रवाई डिबाउंस की गई है।",
    },
    "NO_PERMS_TO_ACT_MENTION": {
        "english": "Bot lacks permissions to act on mentioned user {username} (ID: {user_id}) in chat {chat_id}.",
        "hindi": "बॉट के पास चैट {chat_id} में उल्लिखित उपयोगकर्ता {username} (ID: {user_id}) पर कार्रवाई करने की अनुमति नहीं है।",
    },
    "BOT_ERROR_NOTIFICATION": {
        "english": "🚨 Bot Error Alert 🚨\nError: {error}\nUpdate: {update}",
        "hindi": "🚨 बॉट त्रुटि चेतावनी 🚨\nत्रुटि: {error}\nअपडेट: {update}"
    },
    "NEW_USER_PROFILE_VIOLATION_REASON": {
        "english": "New user's profile ({field}) contains issues: {issue_type}",
        "hindi": "नए उपयोगकर्ता का प्रोफाइल ({field}) में समस्याएँ हैं: {issue_type}"
    },
    "NEW_USER_PROFILE_VIOLATION_DIALOGUE": {
        "english": "Hark, newcomer! Thy profile is marked with transgression!\nSpecifically in the {field}, showing issue: {issue_type}.\nAmend this flaw, or face the consequences set forth!",
        "hindi": "सुनो, नवागंतुक! तेरा प्रोफाइल उल्लंघन से चिह्नित है!\nविशेष रूप से {field} में, समस्या दिखाते हुए: {issue_type}।\nइस दोष को सुधारो, वरना निर्धारित परिणामों का सामना करो!"
    },
    "PUNISHMENT_MESSAGE_SENDER_ENGLISH": {
        "english": "<b>{user_mention}</b> has been {action_taken} due to {reason_detail}.\n{dialogue_english}",
        "hindi": "<b>{user_mention}</b> को {reason_detail} के कारण {action_taken} किया गया है।\n{dialogue_hindi}"
    },
    "PUNISHMENT_MESSAGE_SENDER_HINDI": {
        "english": "{dialogue_hindi}",  # For consistency in mixed-language groups
        "hindi": "{dialogue_hindi}"
    },
    "PUNISHMENT_MESSAGE_MENTIONED_USERS": {
        "english": "<b>{sender_mention}</b>'s message mentioned user(s) with problematic profiles ({muted_users_list}). Those users were muted for {mute_duration}.",
        "hindi": "<b>{sender_mention}</b> के संदेश में समस्याग्रस्त प्रोफाइल वाले उपयोगकर्ता(ओं) का उल्लेख किया गया ({muted_users_list})। उन उपयोगकर्ताओं को {mute_duration} के लिए म्यूट किया गया।"
    },
    "MAINTENANCE_MODE_MESSAGE": {
        "english": "🤖 Bot is currently under maintenance, like a knight polishing his armor. Please try again later.",
        "hindi": "🤖 बॉट वर्तमान में रखरखाव के अधीन है, जैसे एक शूरवीर अपने कवच को चमका रहा हो। कृपया बाद में पुनः प्रयास करें।"
    },
    "FEATURE_DISABLED_MESSAGE": {
        "english": "Alas, the scroll for the /{command_name} command is temporarily sealed for revisions.",
        "hindi": "हाय, /{command_name} कमांड के लिए स्क्रॉल अस्थायी रूप से संशोधन के लिए सील है।"
    },
    "BOT_ADDED_TO_GROUP_WELCOME_MESSAGE": {
        "english": "Hark, noble citizens! Bard's Sentinel ({bot_name}) joins this conclave, ready to aid in its defense.",
        "hindi": "सुनो, कुलीन नागरिकों! बार्ड्स सेंटिनल ({bot_name}) इस सभा में शामिल होता है, इसकी रक्षा के लिए तैयार।"
    },
    "JOBQUEUE_NOT_AVAILABLE_MESSAGE": {
        "english": "Alas, the realm's clockwork (JobQueue) falters. Scheduled tasks may not proceed.",
        "hindi": "हाय, राज्य का घड़ीतंत्र (जॉबक्यू) लड़खड़ाता है। निर्धारित कार्य आगे नहीं बढ़ सकते।"
    },
    "BOT_AWAKENS_MESSAGE": {
        "english": "Bard's Sentinel (PTB v{TG_VER}) awakens...",
        "hindi": "बार्ड्स सेंटिनल (PTB v{TG_VER}) जागृत होता है..."
    },
    "BOT_RESTS_MESSAGE": {
        "english": "Bard's Sentinel rests (Shutdown initiated). Farewell!",
        "hindi": "बार्ड्स सेंटिनल विश्राम करता है (शटडाउन शुरू)। अलविदा!"
    },
    "TOKEN_NOT_LOADED_MESSAGE": {
        "english": "Token not loaded. Cannot start the bot.",
        "hindi": "टोकन लोड नहीं हुआ। बॉट शुरू नहीं हो सकता।"
    },
    "CONFIG_NOT_FOUND_MESSAGE": {
        "english": "❌ config.ini not found at {config_file_name}. Creating a template config file.",
        "hindi": "❌ config.ini {config_file_name} पर नहीं मिला। एक टेम्पलेट कॉन्फिग फाइल बना रहा है।"
    },
    "CONFIG_TEMPLATE_CREATED_MESSAGE": {
        "english": "✅ config.ini template created at {config_file_name}. Please edit it with your Bot Token and settings.",
        "hindi": "✅ config.ini टेम्पलेट {config_file_name} पर बनाया गया। कृपया इसे अपने बॉट टोकन और सेटिंग्स के साथ संपादित करें।"
    },
    "CONFIG_TOKEN_NOT_SET_MESSAGE": {
        "english": "❌ Bot Token not set in {config_file_name}. Please edit the config file. Exiting.",
        "hindi": "❌ बॉट टोकन {config_file_name} में सेट नहीं है। कृपया कॉन्फिग फाइल संपादित करें। बाहर निकल रहा है।"
    },
    "CONFIG_LOAD_ERROR_MESSAGE": {
        "english": "Error loading or parsing {config_file_name}: {e}",
        "hindi": "{config_file_name} लोड करने या पार्स करने में त्रुटि: {e}"
    },
    "CONFIG_LOAD_SUCCESS_MESSAGE": {
        "english": "✅ Configuration loaded successfully.",
        "hindi": "✅ कॉन्फिगरेशन सफलतापूर्वक लोड हुआ।"
    },
    "NO_AUTHORIZED_USERS_WARNING": {
        "english": "⚠️ Warning: No authorized users configured in config.ini. Some commands may be unusable.",
        "hindi": "⚠️ चेतावनी: config.ini में कोई अधिकृत उपयोगकर्ता कॉन्फिगर नहीं हैं। कुछ कमांड उपयोग योग्य नहीं हो सकते।"
    },
    "LOGGING_SETUP_MESSAGE": {
        "english": "Logging setup complete. Level: {log_level}, File: {log_file_path}",
        "hindi": "लॉगिंग सेटअप पूर्ण। स्तर: {log_level}, फाइल: {log_file_path}"
    },
    "CACHE_CLEANUP_JOB_SCHEDULED_MESSAGE": {
        "english": "🧠 Cache cleanup scheduled every {interval}.",
        "hindi": "🧠 कैश सफाई हर {interval} पर निर्धारित।"
    },
    "CLEAR_CACHE_SUCCESS_MESSAGE": {
        "english": "Memory scrolls wiped! ({profile_cache_count} profile, {username_cache_count} username entries cleared).",
        "hindi": "स्मृति स्क्रॉल मिटाए गए! ({profile_cache_count} प्रोफाइल, {username_cache_count} उपयोगकर्ता नाम प्रविष्टियाँ साफ की गईं)।"
    },
    "USER_EXEMPT_SKIP_MESSAGE": {
        "english": "User {user_id} exempt in chat {chat_id} (Global: {is_globally_exempt}, Group: {is_group_exempt}). Skipping.",
        "hindi": "उपयोगकर्ता {user_id} चैट {chat_id} में छूट प्राप्त (वैश्विक: {is_globally_exempt}, समूह: {is_group_exempt})। छोड़ रहा है।"
    },
    "MESSAGE_PROCESSING_SKIPPED_MAINTENANCE": {
        "english": "Maintenance mode ON, skipping message processing.",
        "hindi": "रखरखाव मोड चालू, संदेश प्रसंस्करण छोड़ रहा है।"
    },
    "MESSAGE_PROCESSING_SKIPPED_FEATURE_OFF": {
        "english": "Message processing feature OFF, skipping message.",
        "hindi": "संदेश प्रसंस्करण सुविधा बंद, संदेश छोड़ रहा है।"
    },
    "FORBIDDEN_IN_GROUP_MESSAGE_HANDLER": {
        "english": "Forbidden error in handle_message for group {chat_id}: {e}",
        "hindi": "समूह {chat_id} के लिए handle_message में निषिद्ध त्रुटि: {e}"
    },
    "ERROR_IN_GROUP_MESSAGE_HANDLER": {
        "english": "Error in handle_message for group {chat_id}, user {user_id}: {e}",
        "hindi": "समूह {chat_id}, उपयोगकर्ता {user_id} के लिए handle_message में त्रुटि: {e}"
    },
    "ACTION_DEBOUNCED_SENDER": {
        "english": "Debounced action for sender {user_id} in chat {chat_id}",
        "hindi": "प्रेषक {user_id} के लिए चैट {chat_id} में डिबाउंस्ड कार्रवाई"
    },
    "ACTION_DEBOUNCED_MENTION": {
        "english": "Debounced action for mentioned user {user_id} in chat {chat_id}",
        "hindi": "उल्लिखित उपयोगकर्ता {user_id} के लिए चैट {chat_id} में डिबाउंस्ड कार्रवाई"
    },
    "NO_PERMS_TO_ACT_SENDER": {
        "english": "Bot lacks permissions to {action} sender {user_id} in chat {chat_id}.",
        "hindi": "बॉट को चैट {chat_id} में प्रेषक {user_id} को {action} करने की अनुमति नहीं है।"
    },
    "BADREQUEST_TO_ACT_SENDER": {
        "english": "BadRequest trying to {action} sender {user_id} in chat {chat_id}: {e}.",
        "hindi": "चैट {chat_id} में प्रेषक {user_id} को {action} करने में BadRequest: {e}।"
    },
    "ERROR_ACTING_SENDER": {
        "english": "Error {action}ing sender {user_id}: {e}",
        "hindi": "प्रेषक {user_id} को {action} करने में त्रुटि: {e}"
    },
    "NO_PERMS_TO_ACT_MENTION": {
        "english": "Bot lacks permissions to mute mentioned @{username} ({user_id}) in chat {chat_id}.",
        "hindi": "बॉट को चैट {chat_id} में उल्लिखित @{username} ({user_id}) को म्यूट करने की अनुमति नहीं है।"
    },
    "BADREQUEST_TO_ACT_MENTION": {
        "english": "BadRequest muting mentioned @{username} ({user_id}) in chat {chat_id}: {e}.",
        "hindi": "चैट {chat_id} में उल्लिखित @{username} ({user_id}) को म्यूट करने में BadRequest: {e}।"
    },
    "ERROR_ACTING_MENTION": {
        "english": "Error muting mentioned @{username} ({user_id}): {e}",
        "hindi": "उल्लिखित @{username} ({user_id}) को म्यूट करने में त्रुटि: {e}"
    },
    "ADDITIONAL_MENTIONS_MUTED_LOG": {
        "english": "ℹ️ In chat {chat_id}, sender {sender_mention} mentioned users with profile issues. The mentioned users were muted: {user_list}",
        "hindi": "ℹ️ चैट {chat_id} में, प्रेषक {sender_mention} ने प्रोफाइल समस्याओं वाले उपयोगकर्ताओं का उल्लेख किया। उल्लिखित उपयोगकर्ताओं को म्यूट किया गया: {user_list}"
    },
    "ERROR_HANDLER_EXCEPTION": {
        "english": "❌ An error occurred: {error}",
        "hindi": "❌ एक त्रुटि हुई: {error}"
    },
    "ERROR_HANDLER_INVALID_TOKEN": {
        "english": "CRITICAL ERROR: The bot token is invalid. The bot cannot start.",
        "hindi": "गंभीर त्रुटि: बॉट टोकन अमान्य है। बॉट शुरू नहीं हो सकता।"
    },
    "ERROR_HANDLER_FORBIDDEN": {
        "english": "Forbidden error encountered: {error}. Bot might be blocked, lack permissions, or was kicked from a chat.",
        "hindi": "निषिद्ध त्रुटि का सामना हुआ: {error}। बॉट अवरुद्ध हो सकता है, अनुमतियाँ नहीं हो सकतीं, या चैट से निकाला गया हो।"
    },
    "ERROR_HANDLER_FORBIDDEN_IN_GROUP_REMOVED": {
        "english": "Bot is forbidden in group {chat_id}. Removing the group from the database.",
        "hindi": "बॉट समूह {chat_id} में निषिद्ध है। डेटाबेस से समूह हटा रहा है।"
    },
    "UNMUTE_VIA_PM_BUTTON_TEXT": {
        "english": "✍️ Unmute via Bot PM",
        "hindi": "✍️ बॉट PM के माध्यम से म्यूट हटाएँ"
    },
    "PM_UNMUTE_RETRY_BUTTON_TEXT": {
        "english": "🔄 Attempt Unmute Again",
        "hindi": "🔄 फिर से म्यूट हटाने का प्रयास करें"
    },
    "PM_UNMUTE_READY_ATTEMPT_BUTTON_TEXT": {
        "english": "✅ Unmute Me Now",
        "hindi": "✅ अब मुझे म्यूट हटाएँ"
    },
    "HELP_BUTTON_TEXT": {
        "english": "Help & Usage",
        "hindi": "सहायता और उपयोग"
    },
    "ADD_BOT_TO_GROUP_BUTTON_TEXT": {
        "english": "➕ Add {bot_username} to a Group",
        "hindi": "➕ {bot_username} को समूह में जोड़ें"
    },
    "JOIN_VERIFICATION_CHANNEL_BUTTON_TEXT": {
        "english": "📜 Join Verification Channel",
        "hindi": "📜 सत्यापन चैनल में शामिल हों"
    },
    "VERIFY_JOIN_BUTTON_TEXT": {
        "english": "✅ Verify Channel Join",
        "hindi": "✅ चैनल जॉइन सत्यापित करें"
    },
    "UNMUTE_ME_BUTTON_TEXT": {
        "english": "🔓 Unmute Me",
        "hindi": "🔓 मुझे म्यूट हटाएँ"
    },
    "ADMIN_APPROVE_BUTTON_TEXT": {
        "english": "✅ Admin Approve & Exempt",
        "hindi": "✅ प्रशासक अनुमोदन और छूट"
    },
    "PROVE_ADMIN_BUTTON_TEXT": {
        "english": "🛡️ Proven I Am Admin",
        "hindi": "🛡️ सिद्ध करें कि मैं प्रशासक हूँ"
    },
    "PUNISH_ACTION_MUTE_BUTTON": {
        "english": "🔇 Mute",
        "hindi": "🔇 म्यूट"
    },
    "PUNISH_ACTION_KICK_BUTTON": {
        "english": "👢 Kick",
        "hindi": "👢 निकालें"
    },
    "PUNISH_ACTION_BAN_BUTTON": {
        "english": "🔨 Ban",
        "hindi": "🔨 प्रतिबंध"
    },
    "PUNISH_BATCH_OPERATIONS_BUTTON": {
        "english": "⚙️ Batch Operations",
        "hindi": "⚙️ बैच संचालन"
    },
    "PUNISH_BATCH_KICK_MUTED_BUTTON": {
        "english": "👢 Kick All Muted",
        "hindi": "👢 सभी म्यूट किए गए को निकालें"
    },
    "PUNISH_BATCH_BAN_MUTED_BUTTON": {
        "english": "🔨 Ban All Muted",
        "hindi": "🔨 सभी म्यूट किए गए पर प्रतिबंध लगाएँ"
    },
    "BACK_BUTTON_TEXT": {
        "english": "⬅️ Back",
        "hindi": "⬅️ वापस"
    },
    "DURATION_30M_BUTTON": {
        "english": "30 Minutes",
        "hindi": "30 मिनट"
    },
    "DURATION_1H_BUTTON": {
        "english": "1 Hour",
        "hindi": "1 घंटा"
    },
    "DURATION_1D_BUTTON": {
        "english": "1 Day",
        "hindi": "1 दिन"
    },
    "DURATION_PERMANENT_BUTTON": {
        "english": "Permanent",
        "hindi": "स्थायी"
    },
    "DURATION_CUSTOM_BUTTON": {
        "english": "📝 Custom Duration",
        "hindi": "📝 कस्टम अवधि"
    },
    "PM_UNMUTE_WELCOME": {
        "english": "👋 Greetings, {user_mention}! You were muted in {group_name}.\n\nTo get unmuted, please follow the steps below.",
        "hindi": "👋 नमस्ते, {user_mention}! आपको {group_name} में म्यूट किया गया था।\n\nम्यूट हटाने के लिए, कृपया नीचे दिए गए चरणों का पालन करें।"
    },
    "PM_UNMUTE_INSTRUCTIONS_SUBSCRIBE": {
        "english": "✅ **Step 1: Join the Verification Channel**\nYou need to be a member of our verification channel to use this bot. Please join here: <a href='{channel_link}'>Join Channel</a>. Once joined, return here.",
        "hindi": "✅ **चरण 1: सत्यापन चैनल में शामिल हों**\nइस बॉट का उपयोग करने के लिए आपको हमारे सत्यापन चैनल का सदस्य होना होगा। कृपया यहाँ शामिल हों: <a href='{channel_link}'>चैनल में शामिल हों</a>। शामिल होने के बाद यहाँ वापस आएँ।"
    },
    "PM_UNMUTE_INSTRUCTIONS_PROFILE": {
        "english": "✅ **Step 2: Fix Your Profile**\nYour Telegram profile (specifically your {field}) contains content that violates our rules. Please remove the problematic content.",
        "hindi": "✅ **चरण 2: अपनी प्रोफाइल ठीक करें**\nआपकी टेलीग्राम प्रोफाइल (विशेष रूप से आपका {field}) में ऐसी सामग्री है जो हमारे नियमों का उल्लंघन करती है। कृपया समस्याग्रस्त सामग्री हटाएँ।"
    },
    "PM_UNMUTE_INSTRUCTIONS_BOTH": {
        "english": "✅ **Steps 1 & 2: Join Channel & Fix Profile**\nYou need to be a member of our verification channel AND fix your profile ({field}). Please join here: <a href='{channel_link}'>Join Channel</a>.",
        "hindi": "✅ **चरण 1 और 2: चैनल में शामिल हों और प्रोफाइल ठीक करें**\nआपको हमारे सत्यापन चैनल का सदस्य होना होगा और अपनी प्रोफाइल ({field}) ठीक करनी होगी। कृपया यहाँ शामिल हों: <a href='{channel_link}'>चैनल में शामिल हों</a>।"
    },
    "PM_UNMUTE_ATTEMPTING": {
        "english": "⏳ Performing final checks and attempting to restore thy voice in the group...",
        "hindi": "⏳ अंतिम जाँच कर रहा हूँ और समूह में तुम्हारी आवाज़ बहाल करने का प्रयास कर रहा हूँ..."
    },
    "PM_UNMUTE_SUCCESS": {
        "english": "🎉 Success! Your voice has been restored in **{group_name}**.",
        "hindi": "🎉 सफलता! तुम्हारी आवाज़ **{group_name}** में बहाल कर दी गई है।"
    },
    "PM_UNMUTE_FAIL_INTRO": {
        "english": "Could not unmute {user_mention} in {group_name} yet.",
        "hindi": "अभी तक {user_mention} को {group_name} में म्यूट हटाने में असमर्थ।"
    },
    "PM_UNMUTE_FAIL_CHECKS_CHANNEL": {
        "english": "Target user needs to join the verification channel: {channel_link}",
        "hindi": "लक्षित उपयोगकर्ता को सत्यापन चैनल में शामिल होना होगा: {channel_link}"
    },
    "PM_UNMUTE_ALL_CHECKS_PASS": {
        "english": "All checks seem fine for the target user.",
        "hindi": "लक्षित उपयोगकर्ता के लिए सभी जाँच ठीक प्रतीत होती हैं।"
    },
    "PM_UNMUTE_FAIL_PERMS": {
        "english": "❌ I do not have the necessary permissions to unmute you in **{group_name}**. Please contact a group administrator.",
        "hindi": "❌ मेरे पास **{group_name}** में आपको म्यूट हटाने की आवश्यक अनुमतियाँ नहीं हैं। कृपया समूह प्रशासक से संपर्क करें।"
    },
    "PM_UNMUTE_FAIL_BADREQUEST": {
        "english": "❌ An unexpected Telegram issue prevented the unmute attempt in **{group_name}** ({error}). Please try again later or contact support.",
        "hindi": "❌ एक अप्रत्याशित टेलीग्राम समस्या ने **{group_name}** में म्यूट हटाने का प्रयास रोका ({error})। कृपया बाद में पुनः प्रयास करें या समर्थन से संपर्क करें।"
    },
    "PM_UNMUTE_FAIL_UNKNOWN": {
        "english": "❌ An unexpected error occurred during the unmute attempt in **{group_name}** ({error}). Please try again later.",
        "hindi": "❌ **{group_name}** में म्यूट हटाने के प्रयास के दौरान एक अप्रत्याशित त्रुटि हुई ({error})। कृपया बाद में पुनः प्रयास करें।"
    },
    "START_MESSAGE_PRIVATE_BASE": {
        "english": "👋 Greetings from Bard's Sentinel!\n\nI employ advanced pattern recognition and contextual analysis to safeguard your Telegram groups from undesirable links and promotional content within user profiles, messages, and mentions.\n\n",
        "hindi": "👋 बार्ड्स सेंटिनल से नमस्ते!\n\nमैं उन्नत पैटर्न पहचान और संदर्भ विश्लेषण का उपयोग करके आपके टेलीग्राम समूहों को अवांछित लिंक्स और उपयोगकर्ता प्रोफाइल, संदेशों, और उल्लेखों में प्रचार सामग्री से सुरक्षित रखता हूँ।\n\n"
    },
    "START_MESSAGE_ADMIN_CONFIG": {
        "english": "🔹 **To Begin:** Add me to your group and grant administrator privileges (essential: delete messages, ban/restrict users).\n🔹 **Configuration (Admins):** Use <code>/setpunish</code> in your group to select 'mute', 'kick', or 'ban'. Fine-tune mute durations with <code>/setduration</code> (for all violation types) or more specific commands like <code>/setdurationprofile</code>.\n",
        "hindi": "🔹 **शुरुआत करने के लिए:** मुझे अपने समूह में जोड़ें और प्रशासक विशेषाधिकार प्रदान करें (आवश्यक: संदेश हटाएँ, उपयोगकर्ताओं पर प्रतिबंध/प्रतिबंधित करें)।\n🔹 **कॉन्फिगरेशन (प्रशासक):** अपने समूह में <code>/setpunish</code> का उपयोग करके 'म्यूट', 'किक', या 'प्रतिबंध' चुनें। म्यूट अवधि को <code>/setduration</code> (सभी उल्लंघन प्रकारों के लिए) या अधिक विशिष्ट कमांड जैसे <code>/setdurationprofile</code> के साथ ठीक करें।\n"
    },
    "START_MESSAGE_CHANNEL_VERIFY_INFO": {
        "english": "🔹 **Verification (Optional):** If this bot instance requires it, join our designated channel (button below, if configured) and then tap 'Verify Me'.\n",
        "hindi": "🔹 **सत्यापन (वैकल्पिक):** यदि इस बॉट इंस्टेंस को इसकी आवश्यकता है, तो हमारे निर्दिष्ट चैनल में शामिल हों (नीचे बटन, यदि कॉन्फिगर किया गया हो) और फिर 'मुझे सत्यापित करें' पर टैप करें।\n"
    },
    "START_MESSAGE_HELP_PROMPT": {
        "english": "For a full list of user and admin commands, click 'Help & Usage'.",
        "hindi": "उपयोगकर्ता और प्रशासक कमांड की पूरी सूची के लिए, 'सहायता और उपयोग' पर क्लिक करें।"
    },
    "START_MESSAGE_GROUP": {
        "english": "🤖 Bard's Sentinel (@{bot_username}) is active here. Type /help@{bot_username} for commands or /start@{bot_username} for info.",
        "hindi": "🤖 बार्ड्स सेंटिनल (@{bot_username}) यहाँ सक्रिय है। कमांड के लिए /help@{bot_username} या जानकारी के लिए /start@{bot_username} टाइप करें।"
    },
    "HELP_COMMAND_TEXT_PRIVATE": {
        "english": "📜 <b>Bard's Sentinel - Scroll of Guidance</b> 📜\n\nI diligently scan messages, user profiles (name, bio), and @mentions for problematic content, taking action based on each group's specific configuration. My vigilance is powered by advanced pattern recognition.\n\n<b>Key Capabilities:</b>\n✔️ Detects unwanted links and keywords in usernames, first/last names, bios, messages, and captions.\n✔️ Scans profiles of @mentioned users, muting them if their profile is also problematic (duration configurable by admins).\n✔️ Group administrators can customize actions (mute, kick, ban) via <code>/setpunish</code>.\n✔️ Group administrators can set a general mute duration using <code>/setduration</code>, or specify durations for different violation types:\n    - <code>/setdurationprofile</code> (for user's own profile violations)\n    - <code>/setdurationmessage</code> (for violations in a sent message)\n    - <code>/setdurationmention</code> (for muting a mentioned user due to their profile)\n✔️ Group administrators can exempt specific users from checks within their group using <code>/freepunish</code> and <code>/unfreepunish</code>.\n✔️ If you are muted, remove any offending content from your profile (name, username, bio), ensure you are subscribed to any required verification channel, and then click the 'Unmute Me' button on the notification message or initiate the process via PM.\n\n<b>Administrator Commands (for use in your group):</b>\n▪️ <code>/setpunish [mute|kick|ban]</code> - Choose the action for rule violations in this group. (Interactive if no arguments provided).\n▪️ <code>/setduration [duration]</code> - Sets a blanket mute duration for ALL types of violations (profile, message, mention-profile). E.g., <code>30m</code>, <code>1h</code>, <code>2d</code>, or <code>0</code> for permanent. (Interactive if no arguments).\n▪️ <code>/setdurationprofile [duration]</code> - Mute duration specifically for user profile violations.\n▪️ <code>/setdurationmessage [duration]</code> - Mute duration specifically for message content violations.\n▪️ <code>/setdurationmention [duration]</code> - Mute duration for a mentioned user whose profile is problematic.\n▪️ <code>/freepunish [user_id_or_reply]</code> - Exempt a user from checks specifically within this group.\n▪️ <code>/unfreepunish [user_id_or_reply]</code> - Remove a user's group-specific exemption.\n\n<b>Super Administrator Commands (can be used in any chat):</b>\n▪️ <code>/gfreepunish [user_id or @username]</code> - Grant a user global immunity from punishments across all groups.\n▪️ <code>/gunfreepunish [user_id or @username]</code> - Remove a user's global immunity.\n▪️ <code>/clearcache</code> - Clear bot caches (profile and username lookups).\n▪️ <code>/checkbio [user_id or reply]</code> - Check a user's Telegram profile fields for forbidden content.\n▪️ <code>/setchannel [ID/username|clear]</code> - Set or clear the verification channel requirement.\n▪️ <code>/stats</code> - Show bot statistics and operational status.\n▪️ <code>/disable [feature_name]</code> - Disable a specific bot feature (e.g., message_processing, chat_member_processing).\n▪️ <code>/enable [feature_name]</code> - Enable a specific bot feature.\n▪️ <code>/maintenance [on|off]</code> - Turn maintenance mode on or off (disables most functions).\n▪️ <code>/unmuteall [group_id]</code> - Attempt to unmute all users known to the bot in a specific group. Use with caution.\n▪️ <code>/gunmuteall</code> - Attempt to unmute all users known to the bot in all known groups. Use with extreme caution.\n▪️ <code>/broadcast [target_id] [interval] <message></code> - Send a message to all groups or a specific one (optionally repeating).\n▪️ <code>/bcastall [interval] <message></code> - Send a message to all groups and all users who started PM (optionally repeating).\n▪️ <code>/bcastself [interval]</code> - Send a self-promotion message to all users who started PM (optionally repeating).\n▪️ <code>/stopbroadcast [job_name]</code> - Stop a scheduled timed broadcast job. Use <code>/stopbroadcast</code> alone to list jobs.\n\n<i>Note: Durations are specified like <code>30m</code> (minutes), <code>2h</code> (hours), <code>7d</code> (days). Use <code>0</code> for a permanent mute. Invalid duration means no mute.</i>\n\nFor support, contact: @YourAdminUsername",
        "hindi": "📜 <b>बार्ड्स सेंटिनल - मार्गदर्शन का स्क्रॉल</b> 📜\n\nमैं संदेशों, उपयोगकर्ता प्रोफाइल (नाम, बायो), और @उल्लेखों में समस्याग्रस्त सामग्री के लिए सावधानीपूर्वक स्कैन करता हूँ, प्रत्येक समूह की विशिष्ट कॉन्फिगरेशन के आधार पर कार्रवाई करता हूँ। मेरी सतर्कता उन्नत पैटर्न पहचान द्वारा संचालित है।\n\n<b>प्रमुख क्षमताएँ:</b>\n✔️ उपयोगकर्ता नाम, प्रथम/अंतिम नाम, बायो, संदेशों, और कैप्शन में अवांछित लिंक्स और कीवर्ड का पता लगाता है।\n✔️ @उल्लिखित उपयोगकर्ताओं की प्रोफाइल स्कैन करता है, यदि उनकी प्रोफाइल भी समस्याग्रस्त है तो उन्हें म्यूट करता है (प्रशासकों द्वारा कॉन्फिगर करने योग्य अवधि)।\n✔️ समूह प्रशासक <code>/setpunish</code> के माध्यम से कार्रवाइयाँ (म्यूट, किक, प्रतिबंध) अनुकूलित कर सकते हैं।\n✔️ समूह प्रशासक <code>/setduration</code> का उपयोग करके सामान्य म्यूट अवधि सेट कर सकते हैं, या विभिन्न उल्लंघन प्रकारों के लिए अवधि निर्दिष्ट कर सकते हैं:\n    - <code>/setdurationprofile</code> (उपयोगकर्ता की स्वयं की प्रोफाइल उल्लंघनों के लिए)\n    - <code>/setdurationmessage</code> (भेजे गए संदेश में उल्लंघनों के लिए)\n    - <code>/setdurationmention</code> (उल्लिखित उपयोगकर्ता की प्रोफाइल के कारण म्यूट करने के लिए)\n✔️ समूह प्रशासक <code>/freepunish</code> और <code>/unfreepunish</code> का उपयोग करके अपने समूह में विशिष्ट उपयोगकर्ताओं को जाँच से छूट दे सकते हैं।\n✔️ यदि आप म्यूट हैं, तो अपनी प्रोफाइल (नाम, उपयोगकर्ता नाम, बायो) से आपत्तिजनक सामग्री हटाएँ, सुनिश्चित करें कि आप किसी भी आवश्यक सत्यापन चैनल के सदस्य हैं, और फिर अधिसूचना संदेश पर 'मुझे म्यूट हटाएँ' बटन क्लिक करें या PM के माध्यम से प्रक्रिया शुरू करें।\n\n<b>प्रशासक कमांड (आपके समूह में उपयोग के लिए):</b>\n▪️ <code>/setpunish [mute|kick|ban]</code> - इस समूह में नियम उल्लंघनों के लिए कार्रवाई चुनें। (कोई तर्क न दिए जाने पर इंटरैक्टिव)।\n▪️ <code>/setduration [duration]</code> - सभी प्रकार के उल्लंघनों (प्रोफाइल, संदेश, उल्लेख-प्रोफाइल) के लिए एक सामान्य म्यूट अवधि सेट करता है। उदाहरण: <code>30m</code>, <code>1h</code>, <code>2d</code>, या <code>0</code> स्थायी के लिए। (कोई तर्क न दिए जाने पर इंटरैक्टिव)।\n▪️ <code>/setdurationprofile [duration]</code> - विशेष रूप से उपयोगकर्ता प्रोफाइल उल्लंघनों के लिए म्यूट अवधि।\n▪️ <code>/setdurationmessage [duration]</code> - विशेष रूप से संदेश सामग्री उल्लंघनों के लिए म्यूट अवधि।\n▪️ <code>/setdurationmention [duration]</code> - उल्लिखित उपयोगकर्ता की समस्याग्रस्त प्रोफाइल के लिए म्यूट अवधि।\n▪️ <code>/freepunish [user_id_or_reply]</code> - इस समूह में विशेष रूप से एक उपयोगकर्ता को जाँच से छूट दें।\n▪️ <code>/unfreepunish [user_id_or_reply]</code> - एक उपयोगकर्ता की समूह-विशिष्ट छूट हटाएँ।\n\n<b>सुपर प्रशासक कमांड (किसी भी चैट में उपयोग किए जा सकते हैं):</b>\n▪️ <code>/gfreepunish [user_id or @username]</code> - सभी समूहों में एक उपयोगकर्ता को वैश्विक दंड से छूट प्रदान करें।\n▪️ <code>/gunfreepunish [user_id or @username]</code> - एक उपयोगकर्ता की वैश्विक छूट हटाएँ।\n▪️ <code>/clearcache</code> - बॉट कैश (प्रोफाइल और उपयोगकर्ता नाम लुकअप) साफ करें।\n▪️ <code>/checkbio [user_id or reply]</code> - एक उपयोगकर्ता के टेलीग्राम प्रोफाइल फ़ील्ड्स में निषिद्ध सामग्री की जाँच करें।\n▪️ <code>/setchannel [ID/username|clear]</code> - सत्यापन चैनल आवश्यकता सेट करें या साफ करें।\n▪️ <code>/stats</code> - बॉट सांख्यिकी और संचालन स्थिति दिखाएँ।\n▪️ <code>/disable [feature_name]</code> - एक विशिष्ट बॉट सुविधा अक्षम करें (उदा., message_processing, chat_member_processing)।\n▪️ <code>/enable [feature_name]</code> - एक विशिष्ट बॉट सुविधा सक्षम करें।\n▪️ <code>/maintenance [on|off]</code> - रखरखाव मोड चालू या बंद करें (अधिकांश कार्य अक्षम करता है)।\n▪️ <code>/unmuteall [group_id]</code> - एक विशिष्ट समूह में बॉट के लिए ज्ञात सभी उपयोगकर्ताओं को म्यूट हटाने का प्रयास करें। सावधानी से उपयोग करें।\n▪️ <code>/gunmuteall</code> - सभी ज्ञात समूहों में बॉट के लिए ज्ञात सभी उपयोगकर्ताओं को म्यूट हटाने का प्रयास करें। अत्यधिक सावधानी से उपयोग करें।\n▪️ <code>/broadcast [target_id] [interval] <message></code> - सभी समूहों या एक विशिष्ट समूह में संदेश भेजें (वैकल्पिक रूप से दोहराते हुए)।\n▪️ <code>/bcastall [interval] <message></code> - सभी समूहों और सभी उपयोगकर्ताओं को जो PM शुरू कर चुके हैं, संदेश भेजें (वैकल्पिक रूप से दोहराते हुए)।\n▪️ <code>/bcastself [interval]</code> - PM शुरू करने वाले सभी उपयोगकर्ताओं को एक स्व-प्रचार संदेश भेजें (वैकल्पिक रूप से दोहराते हुए)।\n▪️ <code>/stopbroadcast [job_name]</code> - एक निर्धारित समयबद्ध प्रसारण कार्य रोकें। सक्रिय कार्यों को सूचीबद्ध करने के लिए अकेले <code>/stopbroadcast</code> का उपयोग करें।\n\n<i>नोट: अवधि जैसे <code>30m</code> (मिनट), <code>2h</code> (घंटे), <code>7d</code> (दिन) निर्दिष्ट की जाती हैं। स्थायी म्यूट के लिए <code>0</code> का उपयोग करें। अमान्य अवधि का मतलब कोई म्यूट नहीं।</i>\n\nसमर्थन के लिए, संपर्क करें: @YourAdminUsername"
    },
    "HELP_COMMAND_TEXT_GROUP": {
        "english": "🛡️ Bard's Sentinel Help 🛡️\nFor a detailed scroll of commands and usage instructions, please <a href=\"https://t.me/{bot_username}?start=help\">start a private chat with me</a>.\n\nQuick admin commands: <code>/setpunish</code>, <code>/setduration</code>, <code>/freepunish [user_id_or_reply]</code>.",
        "hindi": "🛡️ बार्ड्स सेंटिनल सहायता 🛡️\nकमांड और उपयोग निर्देशों के विस्तृत स्क्रॉल के लिए, कृपया <a href=\"https://t.me/{bot_username}?start=help\">मेरे साथ निजी चैट शुरू करें</a>।\n\nत्वरित प्रशासक कमांड: <code>/setpunish</code>, <code>/setduration</code>, <code>/freepunish [user_id_or_reply]</code>।"
    },
    "SET_PUNISH_PROMPT": {
        "english": "Choose the action for rule violations in this group (current: {current_action}):",
        "hindi": "इस समूह में नियम उल्लंघनों के लिए कार्रवाई चुनें (वर्तमान: {current_action}):"
    },
    "SET_PUNISH_INVALID_ACTION": {
        "english": "Invalid action '{action}'. Please choose 'mute', 'kick', or 'ban'.",
        "hindi": "अमान्य कार्रवाई '{action}'। कृपया 'म्यूट', 'किक', या 'प्रतिबंध' चुनें।"
    },
    "SET_PUNISH_SUCCESS": {
        "english": "Punishment action set to {action}.",
        "hindi": "दंड कार्रवाई {action} पर सेट की गई।"
    },
    "SET_DURATION_ALL_PROMPT": {
        "english": "Set a blanket mute duration for ALL violation types (profile, message, mention-profile).\nCurrent example (profile duration): {current_profile_duration}.\nChoose new duration (e.g. 30m, 1h, 0 for perm):",
        "hindi": "सभी उल्लंघन प्रकारों (प्रोफाइल, संदेश, उल्लेख-प्रोफाइल) के लिए एक सामान्य म्यूट अवधि सेट करें।\nवर्तमान उदाहरण (प्रोफाइल अवधि): {current_profile_duration}।\nनई अवधि चुनें (उदा. 30m, 1h, 0 स्थायी के लिए):"
    },
    "SET_DURATION_PROFILE_PROMPT": {
        "english": "Set mute duration specifically for 'profile' issues (current: {current_duration}):",
        "hindi": "विशेष रूप से 'प्रोफाइल' समस्याओं के लिए म्यूट अवधि सेट करें (वर्तमान: {current_duration}):"
    },
    "SET_DURATION_MESSAGE_PROMPT": {
        "english": "Set mute duration specifically for 'message' issues (current: {current_duration}):",
        "hindi": "विशेष रूप से 'संदेश' समस्याओं के लिए म्यूट अवधि सेट करें (वर्तमान: {current_duration}):"
    },
    "SET_DURATION_MENTION_PROMPT": {
        "english": "Set mute duration specifically for 'mention profile' issues (current: {current_duration}):",
        "hindi": "विशेष रूप से 'उल्लेख प्रोफाइल' समस्याओं के लिए म्यूट अवधि सेट करें (वर्तमान: {current_duration}):"
    },
    "SET_DURATION_GENERIC_PROMPT": {
        "english": "Set punishment duration for {trigger_type}. Current: {current_duration}.",
        "hindi": "{trigger_type} के लिए दंड अवधि सेट करें। वर्तमान: {current_duration}।"
    },
    "DURATION_CUSTOM_PROMPT_CB": {
        "english": "Enter the custom duration for {scope_type}.\nUse formats like <code>30m</code> (minutes), <code>2h</code> (hours), <code>2d</code> (days), or <code>0</code> for permanent.\nExample: <code>/{command_name} 12h</code>",
        "hindi": "{scope_type} के लिए कस्टम अवधि दर्ज करें।\n<code>30m</code> (मिनट), <code>2h</code> (घंटे), <code>2d</code> (दिन), या <code>0</code> स्थायी के लिए जैसे प्रारूपों का उपयोग करें।\nउदाहरण: <code>/{command_name} 12h</code>"
    },
    "INVALID_DURATION_FORMAT_MESSAGE": {
        "english": "Invalid duration format '{duration_str}'. Use formats like '30m', '1h', '2d', or '0' for permanent.",
        "hindi": "अमान्य अवधि प्रारूप '{duration_str}'। '30m', '1h', '2d', या '0' स्थायी के लिए जैसे प्रारूपों का उपयोग करें।"
    },
    "SET_DURATION_ALL_SUCCESS": {
        "english": "All mute durations (profile, message, mention-profile) in this group set to: {duration_formatted}.",
        "hindi": "इस समूह में सभी म्यूट अवधियाँ (प्रोफाइल, संदेश, उल्लेख-प्रोफाइल) सेट की गईं: {duration_formatted}।"
    },
    "SET_DURATION_PROFILE_SUCCESS": {
        "english": "Mute duration for profile issues set to: {duration_formatted}.",
        "hindi": "प्रोफाइल समस्याओं के लिए म्यूट अवधि सेट की गई: {duration_formatted}।"
    },
    "SET_DURATION_MESSAGE_SUCCESS": {
        "english": "Mute duration for message content issues set to: {duration_formatted}.",
        "hindi": "संदेश सामग्री समस्याओं के लिए म्यूट अवधि सेट की गई: {duration_formatted}।"
    },
    "SET_DURATION_MENTION_SUCCESS": {
        "english": "Mute duration for mentioned user profile issues set to: {duration_formatted}.",
        "hindi": "उल्लिखित उपयोगकर्ता प्रोफाइल समस्याओं के लिए म्यूट अवधि सेट की गई: {duration_formatted}।"
    },
    "SET_DURATION_GENERIC_SUCCESS": {
        "english": "{trigger_type} duration set to {duration_formatted}.",
        "hindi": "{trigger_type} अवधि सेट की गई: {duration_formatted}।"
    },
    "INVALID_DURATION_FROM_BUTTON_ERROR": {
        "english": "Received an invalid duration value from the button.",
        "hindi": "बटन से अमान्य अवधि मान प्राप्त हुआ।"
    },
    "FREEPUNISH_USAGE_MESSAGE": {
        "english": "Usage: <code>/freepunish [user_id or reply]</code> - Exempt a user from checks in this group.",
        "hindi": "उपयोग: <code>/freepunish [user_id or reply]</code> - इस समूह में एक उपयोगकर्ता को जाँच से छूट दें।"
    },
    "USER_NOT_FOUND_MESSAGE": {
        "english": "Could not find a user matching '{identifier}'.",
        "hindi": "'{identifier}' से मेल खाने वाला उपयोगकर्ता नहीं मिला।"
    },
    "INVALID_USER_ID_MESSAGE": {
        "english": "Invalid User ID provided.",
        "hindi": "अमान्य उपयोगकर्ता ID प्रदान किया गया।"
    },
    "FREEPUNISH_SUCCESS_MESSAGE": {
        "english": "✅ User {user_id} is now exempted from automated punishments in this group.",
        "hindi": "✅ उपयोगकर्ता {user_id} अब इस समूह में स्वचालित दंडों से छूट प्राप्त है।"
    },
    "UNFREEPUNISH_USAGE_MESSAGE": {
        "english": "Usage: <code>/unfreepunish [user_id or reply]</code> - Remove a user's exemption in this group.",
        "hindi": "उपयोग: <code>/unfreepunish [user_id or reply]</code> - इस समूह में एक उपयोगकर्ता की छूट हटाएँ।"
    },
    "UNFREEPUNISH_SUCCESS_MESSAGE": {
        "english": "✅ User {user_id}'s exemption from automated punishments in this group has been removed.",
        "hindi": "✅ उपयोगकर्ता {user_id} की इस समूह में स्वचालित दंडों से छूट हटा दी गई है।"
    },
    "GFREEPUNISH_USAGE_MESSAGE": {
        "english": "👑 Usage: <code>/gfreepunish [user_id or @username]</code> - Grant a user global immunity from punishments.",
        "hindi": "👑 उपयोग: <code>/gfreepunish [user_id or @username]</code> - एक उपयोगकर्ता को वैश्विक दंडों से छूट प्रदान करें।"
    },
    "GFREEPUNISH_SUCCESS_MESSAGE": {
        "english": "👑 ✅ User {user_id} has been granted global immunity from punishments.",
        "hindi": "👑 ✅ उपयोगकर्ता {user_id} को वैश्विक दंडों से छूट प्रदान की गई है।"
    },
    "GUNFREEPUNISH_USAGE_MESSAGE": {
        "english": "👑 🔓 Usage: <code>/gunfreepunish [user_id or @username]</code> - Remove a user's global immunity.",
        "hindi": "👑 🔓 उपयोग: <code>/gunfreepunish [user_id or @username]</code> - एक उपयोगकर्ता की वैश्विक छूट हटाएँ।"
    },
    "GUNFREEPUNISH_SUCCESS_MESSAGE": {
        "english": "👑 ✅ User {user_id}'s global immunity has been removed.",
        "hindi": "👑 ✅ उपयोगकर्ता {user_id} की वैश्विक छूट हटा दी गई है।"
    },
    "GUNFREEPUNISH_NOT_IMMUNE_MESSAGE": {
        "english": "👑 ℹ️ User {user_id} is not currently globally immune.",
        "hindi": "👑 ℹ️ उपयोगकर्ता {user_id} वर्तमान में वैश्विक रूप से प्रतिरक्षित नहीं है।"
    },
    "CLEAR_CACHE_SUCCESS_MESSAGE": {
        "english": "🧠 Cache cleared. Profile entries: {profile_cache_count}, Username entries: {username_cache_count}.",
        "hindi": "🧠 कैश साफ किया गया। प्रोफाइल प्रविष्टियाँ: {profile_cache_count}, उपयोगकर्ता नाम प्रविष्टियाँ: {username_cache_count}।"
    },
    "CHECKBIO_USAGE_MESSAGE": {
        "english": "🔍 Usage: <code>/checkbio [user_id or reply]</code> - Check a user's Telegram profile fields for forbidden content (Super Admins only).",
        "hindi": "🔍 उपयोग: <code>/checkbio [user_id or reply]</code> - एक उपयोगकर्ता के टेलीग्राम प्रोफाइल फ़ील्ड्स में निषिद्ध सामग्री की जाँच करें (केवल सुपर प्रशासक)।"
    },
    "CHECKBIO_RESULT_HEADER": {
        "english": "🔍 <b>Profile Check for User {user_id} (@{username})</b>",
        "hindi": "🔍 <b>उपयोगकर्ता {user_id} (@{username}) के लिए प्रोफाइल जाँच</b>"
    },
    "BIO_IS_BLANK_MESSAGE": {
        "english": "<i>Bio is blank.</i>",
        "hindi": "<i>बायो खाली है।</i>"
    },
    "CHECKBIO_RESULT_PROBLEM_DETAILS": {
        "english": "\n  - Issue in <b>{field}</b> ({issue_type})",
        "hindi": "\n  - <b>{field}</b> में समस्या ({issue_type})"
    },
    "CHECKBIO_ERROR_MESSAGE": {
        "english": "❌ An error occurred while checking bio for user {user_id}: {error}",
        "hindi": "❌ उपयोगकर्ता {user_id} के लिए बायो जाँचते समय त्रुटि हुई: {error}"
    },
    "SET_CHANNEL_PROMPT": {
        "english": "➡️ Forward a message from the verification channel, or reply with its ID/username to set it.\nTo clear the verification channel requirement, use <code>/setchannel clear</code>.",
        "hindi": "➡️ सत्यापन चैनल से एक संदेश अग्रेषित करें, या इसके ID/उपयोगकर्ता नाम के साथ उत्तर दें।\nसत्यापन चैनल आवश्यकता को साफ करने के लिए, <code>/setchannel clear</code> का उपयोग करें।"
    },
    "SET_CHANNEL_CLEARED_MESSAGE": {
        "english": "✅ Verification channel requirement cleared.",
        "hindi": "✅ सत्यापन चैनल आवश्यकता साफ की गई।"
    },
    "SET_CHANNEL_NOT_A_CHANNEL_ERROR": {
        "english": "❌ '{identifier}' is not a valid channel ID/username or could not be accessed. (Type: {type})",
        "hindi": "❌ '{identifier}' एक मान्य चैनल ID/उपयोगकर्ता नाम नहीं है या इसे एक्सेस नहीं किया जा सका। (प्रकार: {type})"
    },
    "SET_CHANNEL_BOT_NOT_ADMIN_ERROR": {
        "english": "❌ I need to be an administrator in the channel to check members.",
        "hindi": "❌ मुझे सदस्यों की जाँच के लिए चैनल में प्रशासक होना होगा।"
    },
    "SET_CHANNEL_SUCCESS_MESSAGE": {
        "english": "✅ Verification channel set to <b>{channel_title}</b> (ID: <code>{channel_id}</code>).",
        "hindi": "✅ सत्यापन चैनल <b>{channel_title}</b> (ID: <code>{channel_id}</code>) पर सेट किया गया।"
    },
    "SET_CHANNEL_INVITE_LINK_APPEND": {
        "english": "\n🔗 Invite Link: {invite_link}",
        "hindi": "\n🔗 आमंत्रण लिंक: {invite_link}"
    },
    "SET_CHANNEL_NO_INVITE_LINK_APPEND": {
        "english": "\n🔗 Could not get invite link.",
        "hindi": "\n🔗 आमंत्रण लिंक प्राप्त नहीं हो सका।"
    },
    "SET_CHANNEL_BADREQUEST_ERROR": {
        "english": "❌ Failed to access channel '{identifier}' due to a Telegram error: {error}",
        "hindi": "❌ टेलीग्राम त्रुटि के कारण चैनल '{identifier}' तक पहुँचने में विफल: {error}"
    },
"SET_CHANNEL_FORBIDDEN_ERROR": {
        "english": "❌ Access to channel '{identifier}' is forbidden: {error}",
        "hindi": "❌ चैनल '{identifier}' तक पहुँच निषिद्ध है: {error}"
    },
    "SET_CHANNEL_UNEXPECTED_ERROR": {
        "english": "❌ An unexpected error occurred while setting the channel: {error}",
        "hindi": "❌ चैनल सेट करते समय एक अप्रत्याशित त्रुटि हुई: {error}"
    },
    "SET_CHANNEL_FORWARD_NOT_CHANNEL_ERROR": {
        "english": "❌ The forwarded message was not from a channel.",
        "hindi": "❌ अग्रेषित संदेश एक चैनल से नहीं था।"
    },
    "STATS_COMMAND_MESSAGE": {
        "english": """📊 <b>Bard's Sentinel Stats</b> 📊
Groups in Database: <code>{groups_count}</code>
Total Users Known: <code>{total_users_count}</code>
Users who Started PM: <code>{started_users_count}</code>
Bad Actors (Known): <code>{bad_actors_count}</code>
Verification Channel ID: <code>{verification_channel_id}</code>
Maintenance Mode: <b>{maintenance_mode_status}</b>
Cache Sizes: Profile={profile_cache_size}, Username={username_cache_size}
Uptime: <code>{uptime_formatted}</code>
PTB Version: <code>{ptb_version}</code>""",
        "hindi": """📊 <b>बार्ड्स सेंटिनल आँकड़े</b> 📊
डेटाबेस में समूह: <code>{groups_count}</code>
कुल ज्ञात उपयोगकर्ता: <code>{total_users_count}</code>
PM शुरू करने वाले उपयोगकर्ता: <code>{started_users_count}</code>
ज्ञात दुष्ट: <code>{bad_actors_count}</code>
सत्यापन चैनल ID: <code>{verification_channel_id}</code>
रखरखाव मोड: <b>{maintenance_mode_status}</b>
कैश आकार: प्रोफाइल={profile_cache_size}, उपयोगकर्ता नाम={username_cache_size}
अपटाइम: <code>{uptime_formatted}</code>
PTB संस्करण: <code>{ptb_version}</code>"""
    },
    "DISABLE_COMMAND_USAGE_MESSAGE": {
        "english": "👑 Usage: <code>/disable [feature_name]</code> - Disable a bot feature.",
        "hindi": "👑 उपयोग: <code>/disable [feature_name]</code> - एक बॉट सुविधा अक्षम करें।"
    },
    "DISABLE_COMMAND_CRITICAL_ERROR": {
        "english": "🚫 Cannot disable the critical feature '{feature_name}'.",
        "hindi": "🚫 महत्वपूर्ण सुविधा '{feature_name}' को अक्षम नहीं किया जा सकता।"
    },
    "DISABLE_COMMAND_SUCCESS_MESSAGE": {
        "english": "✅ Feature '{feature_name}' disabled.",
        "hindi": "✅ सुविधा '{feature_name}' अक्षम की गई।"
    },
    "ENABLE_COMMAND_USAGE_MESSAGE": {
        "english": "👑 Usage: <code>/enable [feature_name]</code> - Enable a bot feature.",
        "hindi": "👑 उपयोग: <code>/enable [feature_name]</code> - एक बॉट सुविधा सक्षम करें।"
    },
    "ENABLE_COMMAND_SUCCESS_MESSAGE": {
        "english": "✅ Feature '{feature_name}' enabled.",
        "hindi": "✅ सुविधा '{feature_name}' सक्षम की गई।"
    },
    "MAINTENANCE_COMMAND_USAGE_MESSAGE": {
        "english": "👑 Usage: <code>/maintenance [on|off]</code> - Turn maintenance mode ON or OFF. Current state: <b>{current_state}</b>",
        "hindi": "👑 उपयोग: <code>/maintenance [on|off]</code> - रखरखाव मोड चालू या बंद करें। वर्तमान स्थिति: <b>{current_state}</b>"
    },
    "MAINTENANCE_COMMAND_SUCCESS_MESSAGE": {
        "english": "✅ Maintenance mode {state}. The bot {action}.",
        "hindi": "✅ रखरखाव मोड {state}। बॉट {action}।"
    },
    "BROADCAST_USAGE_MESSAGE": {
        "english": "👑 Usage: <code>/broadcast [target_id (optional)] [interval (e.g., 30m, 2h, 1d, optional)] <message_text></code>\nIf target_id is omitted, broadcasts to all groups.\nInterval schedules a repeating broadcast.",
        "hindi": "👑 उपयोग: <code>/broadcast [target_id (वैकल्पिक)] [interval (उदा., 30m, 2h, 1d, वैकल्पिक)] <message_text></code>\nयदि target_id छोड़ा जाता है, तो सभी समूहों में प्रसारण करता है।\nअंतराल एक दोहराने वाला प्रसारण निर्धारित करता है।"
    },
    "BROADCAST_NO_MESSAGE_ERROR": {
        "english": "❌ Please provide message text for the broadcast.",
        "hindi": "❌ कृपया प्रसारण के लिए संदेश टेक्स्ट प्रदान करें।"
    },
    "BROADCAST_STARTED_MESSAGE": {
        "english": "Initiating broadcast with auto-detected format: '{format}'...",
        "hindi": "ऑटो-डिटेक्टेड प्रारूप के साथ प्रसारण शुरू: '{format}'..."
    },
    "BROADCAST_COMPLETE_MESSAGE": {
        "english": "✅ Broadcast complete. Sent to {sent_count} chats, failed for {failed_count} chats.",
        "hindi": "✅ प्रसारण पूर्ण। {sent_count} चैट में भेजा गया, {failed_count} चैट के लिए विफल।"
    },
    "BCASTALL_USAGE_MESSAGE": {
        "english": "👑 Usage: <code>/bcastall [interval (e.g., 30m, 2h, 1d, optional)] <message_text></code>\nBroadcasts to ALL known groups and ALL users who started the bot. Interval schedules a repeating broadcast.",
        "hindi": "👑 उपयोग: <code>/bcastall [interval (उदा., 30m, 2h, 1d, वैकल्पिक)] <message_text></code>\nसभी ज्ञात समूहों और सभी उपयोगकर्ताओं को जो बॉट शुरू किए, प्रसारण करता है। अंतराल दोहराने वाला प्रसारण निर्धारित करता है।"
    },
    "BCASTALL_STARTED_MESSAGE": {
        "english": "Initiating universal broadcast to all groups and all users who started the bot PM...",
        "hindi": "सभी समूहों और सभी उपयोगकर्ताओं को जो बॉट PM शुरू किए, यूनिवर्सल प्रसारण शुरू..."
    },
    "BCASTALL_COMPLETE_MESSAGE": {
        "english": "✅ Universal broadcast complete.\nGroups - Sent: {sent_groups}, Failed: {failed_groups}\nUsers (PM) - Sent: {sent_users}, Failed: {failed_users}",
        "hindi": "✅ यूनिवर्सल प्रसारण पूर्ण।\nसमूह - भेजे गए: {sent_groups}, विफल: {failed_groups}\nउपयोगकर्ता (PM) - भेजे गए: {sent_users}, विफल: {failed_users}"
    },
    "BCASTSELF_USAGE_MESSAGE": {
        "english": "👑 Usage: <code>/bcastself [interval (e.g., 30m, 2h, 1d, optional)]</code>\nSends a self-promotion message to all users who started the bot PM. Interval schedules a repeating broadcast.",
        "hindi": "👑 उपयोग: <code>/bcastself [interval (उदा., 30m, 2h, 1d, वैकल्पिक)]</code>\nसभी उपयोगकर्ताओं को जो बॉट PM शुरू किए, स्व-प्रचार संदेश भेजता है। अंतराल दोहराने वाला प्रसारण निर्धारित करता है।"
    },
    "BCASTSELF_MESSAGE_TEMPLATE": {
        "english": "🛡️ <b>Bard's Sentinel at Your Service!</b> 🛡️\n\nKeep your Telegram groups clean and focused with my advanced protection against unwanted links and spam in user profiles, messages, and mentions.\n\n✅ Automated scanning & customizable actions (mute, kick, ban).\n✅ Granular control over mute durations.\n✅ Exempt trusted users.\n✅ Optional channel subscription for user verification.\n\nGive your community the peace of mind it deserves!\n\n<a href=\"https://t.me/{bot_username}?startgroup=true\">Click here to add Bard's Sentinel to your group!</a>\n\nFor help, type /start in a private chat with me.",
        "hindi": "🛡️ <b>बार्ड्स सेंटिनल आपकी सेवा में!</b> 🛡️\n\nअपने टेलीग्राम समूहों को अवांछित लिंक्स और उपयोगकर्ता प्रोफाइल, संदेशों, और उल्लेखों में स्पैम से उन्नत सुरक्षा के साथ स्वच्छ और केंद्रित रखें।\n\n✅ स्वचालित स्कैनिंग और अनुकूलन योग्य कार्रवाइयाँ (म्यूट, किक, प्रतिबंध)।\n✅ म्यूट अवधि पर बारीक नियंत्रण।\n✅ विश्वसनीय उपयोगकर्ताओं को छूट।\n✅ उपयोगकर्ता सत्यापन के लिए वैकल्पिक चैनल सदस्यता।\n\nअपने समुदाय को वह शांति दें जो वह हकदार है!\n\n<a href=\"https://t.me/{bot_username}?startgroup=true\">यहाँ क्लिक करें बार्ड्स सेंटिनल को अपने समूह में जोड़ने के लिए!</a>\n\nसहायता के लिए, मेरे साथ निजी चैट में /start टाइप करें।"
    },
    "BCASTSELF_STARTED_MESSAGE": {
        "english": "Initiating self-promotion broadcast to all users who started the bot PM...",
        "hindi": "सभी उपयोगकर्ताओं को जो बॉट PM शुरू किए, स्व-प्रचार प्रसारण शुरू..."
    },
    "BCASTSELF_COMPLETE_MESSAGE": {
        "english": "Self-promotion broadcast complete. Sent to {sent_count} users, failed for {failed_count} users.",
        "hindi": "स्व-प्रचार प्रसारण पूर्ण। {sent_count} उपयोगकर्ताओं को भेजा गया, {failed_count} उपयोगकर्ताओं के लिए विफल।"
    },
    "STOP_BROADCAST_USAGE": {
        "english": "👑 Usage: <code>/stopbroadcast [job_name]</code>\nUse <code>/stopbroadcast</code> alone to list active jobs.",
        "hindi": "👑 उपयोग: <code>/stopbroadcast [job_name]</code>\nसक्रिय जॉब्स की सूची के लिए अकेले <code>/stopbroadcast</code> का उपयोग करें।"
    },
    "STOP_BROADCAST_NOT_FOUND": {
        "english": "❌ No active timed broadcast found with the name '<code>{job_name}</code>'. It might have finished or was already stopped.",
        "hindi": "❌ '<code>{job_name}</code>' नाम के साथ कोई सक्रिय समयबद्ध प्रसारण नहीं मिला। यह समाप्त हो चुका हो या पहले ही रुक गया हो।"
    },
    "STOP_BROADCAST_SUCCESS": {
        "english": "✅ Timed broadcast '<code>{job_name}</code>' has been stopped and removed.",
        "hindi": "✅ समयबद्ध प्रसारण '<code>{job_name}</code>' रुक गया और हटा दिया गया।"
    },
    "UNMUTEALL_USAGE_MESSAGE": {
        "english": "👑 Usage: <code>/unmuteall [group_id]</code>\n<b>Warning:</b> This attempts to grant send permissions to all users I know in that group. It may affect users not muted by me. There is no undo.",
        "hindi": "👑 उपयोग: <code>/unmuteall [group_id]</code>\n<b>चेतावनी:</b> यह मेरे द्वारा ज्ञात सभी उपयोगकर्ताओं को उस समूह में भेजने की अनुमति देने का प्रयास करता है। यह उन उपयोगकर्ताओं को प्रभावित कर सकता है जो मेरे द्वारा म्यूट नहीं किए गए। कोई पूर्ववत नहीं है।"
    },
    "UNMUTEALL_INVALID_GROUP_ID": {
        "english": "❌ Invalid Group ID provided.",
        "hindi": "❌ अमान्य समूह ID प्रदान किया गया।"
    },
    "UNMUTEALL_STARTED_MESSAGE": {
        "english": "🔓 Unmute All started for group <code>{group_id}</code>...",
        "hindi": "🔓 समूह <code>{group_id}</code> के लिए सभी म्यूट हटाना शुरू..."
    },
    "UNMUTEALL_COMPLETE_MESSAGE": {
        "english": "✅ Unmute All for group <code>{group_id}</code> complete.\nSuccessfully unmuted (or permissions set): {unmuted_count}\nFailed attempts: {failed_count}\nUsers likely not in group: {not_in_group_count}",
        "hindi": "✅ समूह <code>{group_id}</code> के लिए सभी म्यूट हटाना पूर्ण।\nसफलतापूर्वक म्यूट हटाए गए (या अनुमतियाँ सेट): {unmuted_count}\nविफल प्रयास: {failed_count}\nउपयोगकर्ता संभवतः समूह में नहीं: {not_in_group_count}"
    },
    "GUNMUTEALL_USAGE_MESSAGE": {
        "english": "👑 Usage: <code>/gunmuteall</code> - Attempt to unmute all known users in all known groups (Super Admins only).",
        "hindi": "👑 उपयोग: <code>/gunmuteall</code> - सभी ज्ञात समूहों में सभी ज्ञात उपयोगकर्ताओं को म्यूट हटाने का प्रयास करें (केवल सुपर एडमिन)।"
    },
    "GUNMUTEALL_STARTED_MESSAGE": {
        "english": "👑 🔓 Initiating global unmute process for ALL known users in ALL known groups. This will take significant time and is IRREVERSIBLE for users affected. Proceeding...",
        "hindi": "👑 🔓 सभी ज्ञात समूहों में सभी ज्ञात उपयोगकर्ताओं के लिए वैश्विक म्यूट हटाने की प्रक्रिया शुरू। इसमें काफी समय लगेगा और प्रभावित उपयोगकर्ताओं के लिए अपरिवर्तनीय है। आगे बढ़ रहा है..."
    },
    "GUNMUTEALL_NO_DATA_MESSAGE": {
        "english": "ℹ️ No group or user data found in the database to perform global unmute all.",
        "hindi": "ℹ️ वैश्विक सभी म्यूट हटाने के लिए डेटाबेस में कोई समूह या उपयोगकर्ता डेटा नहीं मिला।"
    },
    "GUNMUTEALL_COMPLETE_MESSAGE": {
        "english": "👑 ✅ Global Unmute All complete across {groups_count} groups (approx).\nTotal successful unmute operations: {total_unmuted_ops}\nTotal failed/skipped operations: {total_failed_ops}",
        "hindi": "👑 ✅ {groups_count} समूहों में वैश्विक सभी म्यूट हटाना पूर्ण (लगभग)।\nकुल सफल म्यूट हटाने के ऑपरेशन: {total_unmuted_ops}\nकुल विफल/छोड़े गए ऑपरेशन: {total_failed_ops}"
    },
    "BULK_UNMUTE_STARTED_STATUS": {
        "english": "🔓 Commencing mass liberation in realm {group_id_display} for {target_count} souls (Bot silences only: {target_bot_mutes_only})...\nProgress: 0/{target_count} (Success: 0, Failed: 0, Skipped: 0)",
        "hindi": "🔓 {group_id_display} क्षेत्र में {target_count} आत्माओं के लिए सामूहिक मुक्ति शुरू (केवल बॉट म्यूट: {target_bot_mutes_only})...\nप्रगति: 0/{target_count} (सफल: 0, विफल: 0, छोड़ा: 0)"
    },
    "BULK_UNMUTE_PROGRESS": {
        "english": "Progress: {processed_count}/{total_count} (Success: {success_count}, Failed: {fail_count}, Skipped: {skipped_count})",
        "hindi": "प्रगति: {processed_count}/{total_count} (सफल: {success_count}, विफल: {fail_count}, छोड़ा: {skipped_count})"
    },
    "BULK_UNMUTE_COMPLETE": {
        "english": "✅ Mass liberation in realm {group_id_display} complete. Success: {success_count}, Failed: {fail_count}, Skipped: {skipped_count} (Total: {total_users}).",
        "hindi": "✅ {group_id_display} क्षेत्र में सामूहिक मुक्ति पूर्ण। सफल: {success_count}, विफल: {fail_count}, छोड़ा: {skipped_count} (कुल: {total_users})।"
    },
    "BULK_UNBAN_STARTED_STATUS": {
        "english": "🔓 Commencing mass restoration in realm {group_id_display} for {target_count} souls (Bot bans only: {target_bot_mutes_only})...\nProgress: 0/{target_count} (Success: 0, Failed: 0, Skipped: 0)",
        "hindi": "🔓 {group_id_display} क्षेत्र में {target_count} आत्माओं के लिए सामूहिक बहाली शुरू (केवल बॉट प्रतिबंध: {target_bot_mutes_only})...\nप्रगति: 0/{target_count} (सफल: 0, विफल: 0, छोड़ा: 0)"
    },
    "BULK_UNBAN_PROGRESS": {
        "english": "Progress: {processed_count}/{total_count} (Success: {success_count}, Failed: {fail_count}, Skipped: {skipped_count})",
        "hindi": "प्रगति: {processed_count}/{total_count} (सफल: {success_count}, विफल: {fail_count}, छोड़ा: {skipped_count})"
    },
    "BULK_UNBAN_COMPLETE": {
        "english": "✅ Mass restoration in realm {group_id_display} complete. Success: {success_count}, Failed: {fail_count}, Skipped: {skipped_count} (Total: {total_users}).",
        "hindi": "✅ {group_id_display} क्षेत्र में सामूहिक बहाली पूर्ण। सफल: {success_count}, विफल: {fail_count}, छोड़ा: {skipped_count} (कुल: {total_users})।"
    },
    "BULK_UNMUTE_NO_TARGETS": {
        "english": "No souls found to liberate in this realm under current decrees.",
        "hindi": "वर्तमान आदेशों के तहत इस क्षेत्र में मुक्त करने के लिए कोई आत्माएँ नहीं मिलीं।"
    },
    "BULK_UNBAN_NO_TARGETS": {
        "english": "No souls found to restore in this realm under current decrees.",
        "hindi": "वर्तमान आदेशों के तहत इस क्षेत्र में बहाल करने के लिए कोई आत्माएँ नहीं मिलीं।"
    },
    "BULK_UNMUTE_NO_GROUPS_GLOBAL": {
        "english": "No realms known to enact global liberation.",
        "hindi": "वैश्विक मुक्ति लागू करने के लिए कोई क्षेत्र ज्ञात नहीं।"
    },
    "BULK_UNBAN_NO_GROUPS_GLOBAL": {
        "english": "No realms known to enact global restoration.",
        "hindi": "वैश्विक बहाली लागू करने के लिए कोई क्षेत्र ज्ञात नहीं।"
    },
    "BULK_UNMUTE_STARTED_GLOBAL_STATUS": {
        "english": "🔓 Commencing global liberation across {group_count} realms...",
        "hindi": "🔓 {group_count} क्षेत्रों में वैश्विक मुक्ति शुरू..."
    },
    "BULK_UNBAN_STARTED_GLOBAL_STATUS": {
        "english": "🔓 Commencing global restoration across {group_count} realms...",
        "hindi": "🔓 {group_count} क्षेत्रों में वैश्विक बहाली शुरू..."
    },
    "BULK_UNMUTE_ALL_TASKS_DISPATCHED_GLOBAL": {
        "english": "Dispatched liberation decrees for {group_count} realms.",
        "hindi": "{group_count} क्षेत्रों के लिए मुक्ति आदेश भेजे गए।"
    },
    "BULK_UNBAN_ALL_TASKS_DISPATCHED_GLOBAL": {
        "english": "Dispatched restoration decrees for {group_count} realms.",
        "hindi": "{group_count} क्षेत्रों के लिए बहाली आदेश भेजे गए।"
    },
    "BULK_OP_ABORTED_NO_PERMS": {
        "english": "❌ Bulk operation aborted in group {group_id}: Bot lacks necessary permissions.",
        "hindi": "❌ समूह {group_id} में सामूहिक ऑपरेशन रद्द: बॉट के पास आवश्यक अनुमतियाँ नहीं हैं।"
    },
    "BCASTSELFREWARDS": {
        "english": "🎁 Exciting rewards await! Join now and claim your exclusive benefits!",
        "hindi": "🎁 रोमांचक पुरस्कार आपका इंतजार कर रहे हैं! अभी शामिल हों और अपने विशेष लाभ प्राप्त करें!"
    },
    "BCASTSELFPROMO": {
        "english": "🚀 Elevate your Telegram experience with Bard's Sentinel! Add me to your group for top-notch protection.",
        "hindi": "🚀 बार्ड्स सेंटिनल के साथ अपने टेलीग्राम अनुभव को उन्नत करें! शीर्ष सुरक्षा के लिए मुझे अपने समूह में जोड़ें।"
    },
    "BCASTSELFUPDATE": {
        "english": "🛠️ Bard's Sentinel has been upgraded! Enjoy enhanced features and improved performance.",
        "hindi": "🛠️ बार्ड्स सेंटिनल को अपग्रेड किया गया है! उन्नत सुविधाओं और बेहतर प्रदर्शन का आनंद लें।"
    },
    "DB_DUMP_CAPTION": {
        "english": "Sacred archive from {date} (Scroll: {file_name})",
        "hindi": "{date} से पवित्र संग्रह (स्क्रॉल: {file_name})"
    },
    "DB_DUMP_ADMIN_NOTIFICATION": {
        "english": "The archive grows heavy ({db_size_mb}MB), exceeding divine limits ({db_max_size_mb}MB). Preserved in channel {dump_channel_id}. Purge may be needed.",
        "hindi": "संग्रह भारी हो गया ({db_size_mb}MB), दैवीय सीमाओं ({db_max_size_mb}MB) को पार कर गया। चैनल {dump_channel_id} में संरक्षित। शुद्धिकरण की आवश्यकता हो सकती है।"
    },
    
    "ADMIN_ONLY_COMMAND_MESSAGE": {
        "english": "❌ This command is restricted to admins only.",
        "hindi": "❌ यह कमांड केवल व्यवस्थापकों के लिए प्रतिबंधित है।"
    },
    "SUPER_ADMIN_ONLY_COMMAND_MESSAGE": {
        "english": "❌ This command is restricted to super admins only.",
        "hindi": "❌ यह कमांड केवल सुपर व्यवस्थापकों के लिए प्रतिबंधित है।"
    },
    "COMMAND_GROUP_ONLY_MESSAGE": {
        "english": "❌ This command can only be used in groups.",
        "hindi": "❌ यह कमांड केवल समूहों में उपयोग की जा सकती है।"
    },
    "UNMUTE_ME_CMD_USAGE": {
        "english": "👑 Usage: <code>/unmute_me [group_id (optional)]</code>\nRequest to be unmuted in a group.",
        "hindi": "👑 उपयोग: <code>/unmute_me [group_id (वैकल्पिक)]</code>\nसमूह में म्यूट हटाने का अनुरोध करें।"
    },
    "UNMUTE_ME_MULTIPLE_GROUPS_FOUND": {
        "english": "⚠️ Multiple groups found. Please specify a group_id: {group_list}",
        "hindi": "⚠️ एक से अधिक समूह मिले। कृपया group_id निर्दिष्ट करें: {group_list}"
    },
    "UNMUTE_ME_GROUP_NOT_FOUND": {
        "english": "❌ Group not found or invalid group_id provided.",
        "hindi": "❌ समूह नहीं मिला या अमान्य group_id प्रदान किया गया।"
    },
    "UNMUTE_ME_PROFILE_ISSUE_PM": {
        "english": "❌ Cannot unmute due to profile issues: {details}",
        "hindi": "❌ प्रोफ़ाइल समस्याओं के कारण म्यूट हटाया नहीं जा सकता: {details}"
    },
    "UNMUTE_ME_CHANNEL_ISSUE_PM": {
        "english": "❌ Please join the verification channel {channel_link} to proceed with unmute.",
        "hindi": "❌ म्यूट हटाने के लिए कृपया सत्यापन चैनल {channel_link} में शामिल हों।"
    },
    "UNMUTE_ME_FAIL_GROUP_CMD_NO_MUTE": {
        "english": "ℹ️ You are not muted in group {group_name}.",
        "hindi": "ℹ️ आप समूह {group_name} में म्यूट नहीं हैं।"
    },
    "UNMUTE_ME_SUCCESS_GROUP_CMD": {
        "english": "✅ Successfully unmuted in group {group_name}.",
        "hindi": "✅ समूह {group_name} में सफलतापूर्वक म्यूट हटाया गया।"
    },
    "UNMUTE_SUCCESS_MESSAGE_GROUP": {
        "english": "✅ User {user_id} unmuted in group {group_name}.",
        "hindi": "✅ उपयोगकर्ता {user_id} को समूह {group_name} में म्यूट हटाया गया।"
    },
    "UNMUTE_ME_FAIL_GROUP_CMD_OTHER": {
        "english": "❌ Failed to unmute in group {group_name}: {error}",
        "hindi": "❌ समूह {group_name} में म्यूट हटाने में विफल: {error}"
    },
    "UNMUTE_ME_RATE_LIMITED_PM": {
        "english": "⏳ Unmute request rate-limited. Try again after {time_remaining} seconds.",
        "hindi": "⏳ म्यूट हटाने का अनुरोध सीमित है। {time_remaining} सेकंड बाद पुनः प्रयास करें।"
    },
    "UNMUTE_ME_NO_MUTES_FOUND_PM": {
        "english": "ℹ️ No active mutes found for you in any groups.",
        "hindi": "ℹ️ आपके लिए किसी भी समूह में कोई सक्रिय म्यूट नहीं मिला।"
    },
    "UNMUTE_ME_COMPLETED_PM": {
        "english": "✅ Unmute request processed. You have been unmuted in {group_count} groups.",
        "hindi": "✅ म्यूट हटाने का अनुरोध संसाधित। आपको {group_count} समूहों में म्यूट हटाया गया है।"
    },
    "UNMUTE_ME_ALL_BOT_MUTES_BUTTON": {
        "english": "🔓 Unmute Me in All Groups",
        "hindi": "🔓 मुझे सभी समूहों में म्यूट हटाएँ"
    },
    "LANG_BUTTON_SELECT_LANGUAGE": {
        "english": "🌐 Select Language",
        "hindi": "🌐 भाषा चुनें"
    },
    "RELOAD_ADMIN_CACHE_SUCCESS": {
        "english": "✅ Admin cache reloaded successfully for group {group_id}.",
        "hindi": "✅ समूह {group_id} के लिए व्यवस्थापक कैश सफलतापूर्वक पुनः लोड किया गया।"
    },
    "RELOAD_ADMIN_CACHE_FAIL_FORBIDDEN": {
        "english": "❌ Failed to reload admin cache for group {group_id}: Access forbidden.",
        "hindi": "❌ समूह {group_id} के लिए व्यवस्थापक कैश पुनः लोड करने में विफल: पहुँच निषिद्ध।"
    },
    "RELOAD_ADMIN_CACHE_FAIL_BADREQUEST": {
        "english": "❌ Failed to reload admin cache for group {group_id}: Bad request.",
        "hindi": "❌ समूह {group_id} के लिए व्यवस्थापक कैश पुनः लोड करने में विफल: खराब अनुरोध।"
    },
    "RELOAD_ADMIN_CACHE_FAIL_ERROR": {
        "english": "❌ Failed to reload admin cache for group {group_id}: {error}",
        "hindi": "❌ समूह {group_id} के लिए व्यवस्थापक कैश पुनः लोड करने में विफल: {error}"
    },
    "COMMAND_COOLDOWN_MESSAGE": {
        "english": "⏳ Command on cooldown. Please wait {time_remaining} seconds.",
        "hindi": "⏳ कमांड कूलडाउन पर है। कृपया {time_remaining} सेकंड प्रतीक्षा करें।"
    },
    "ADMIN_ONLY_COMMAND_MESSAGE_RELOAD": {
        "english": "❌ Reload command is restricted to admins only.",
        "hindi": "❌ पुनः लोड कमांड केवल व्यवस्थापकों के लिए प्रतिबंधित है।"
    },
    "GMUTE_USAGE": {
        "english": "👑 Usage: <code>/gmute [user_id] [duration (e.g., 30m, 2h, 1d)] [reason (optional)]</code>\nGlobally mute a user across all groups.",
        "hindi": "👑 उपयोग: <code>/gmute [user_id] [duration (उदा., 30m, 2h, 1d)] [reason (वैकल्पिक)]</code>\nसभी समूहों में उपयोगकर्ता को वैश्विक रूप से म्यूट करें।"
    },
    "GBAN_USAGE": {
        "english": "👑 Usage: <code>/gban [user_id] [duration (e.g., 30m, 2h, 1d)] [reason (optional)]</code>\nGlobally ban a user across all groups.",
        "hindi": "👑 उपयोग: <code>/gban [user_id] [duration (उदा., 30m, 2h, 1d)] [reason (वैकल्पिक)]</code>\nसभी समूहों में उपयोगकर्ता को वैश्विक रूप से प्रतिबंधित करें।"
    },
    "CANNOT_ACTION_SUPER_ADMIN": {
        "english": "🚫 Cannot perform action on super admin {user_id}.",
        "hindi": "🚫 सुपर व्यवस्थापक {user_id} पर कार्रवाई नहीं की जा सकती।"
    },
    "GMUTE_NO_GROUPS": {
        "english": "❌ No groups found to perform global mute.",
        "hindi": "❌ वैश्विक म्यूट करने के लिए कोई समूह नहीं मिला।"
    },
    "GBAN_NO_GROUPS": {
        "english": "❌ No groups found to perform global ban.",
        "hindi": "❌ वैश्विक प्रतिबंध करने के लिए कोई समूह नहीं मिला।"
    },
    "GMUTE_STARTED": {
        "english": "🔇 Initiating global mute for user {user_id} across {group_count} groups...",
        "hindi": "🔇 उपयोगकर्ता {user_id} के लिए {group_count} समूहों में वैश्विक म्यूट शुरू..."
    },
    "GBAN_STARTED": {
        "english": "🚫 Initiating global ban for user {user_id} across {group_count} groups...",
        "hindi": "🚫 उपयोगकर्ता {user_id} के लिए {group_count} समूहों में वैश्विक प्रतिबंध शुरू..."
    },
    "GMUTE_DEFAULT_REASON": {
        "english": "Global mute by admin.",
        "hindi": "व्यवस्थापक द्वारा वैश्विक म्यूट।"
    },
    "GBAN_DEFAULT_REASON": {
        "english": "Global ban by admin.",
        "hindi": "व्यवस्थापक द्वारा वैश्विक प्रतिबंध।"
    },
    "GMUTE_COMPLETED": {
        "english": "✅ Global mute completed for user {user_id}. Success: {success_count}, Failed: {failed_count}.",
        "hindi": "✅ उपयोगकर्ता {user_id} के लिए वैश्विक म्यूट पूर्ण। सफल: {success_count}, विफल: {failed_count}।"
    },
    "GBAN_COMPLETED": {
        "english": "✅ Global ban completed for user {user_id}. Success: {success_count}, Failed: {failed_count}.",
        "hindi": "✅ उपयोगकर्ता {user_id} के लिए वैश्विक प्रतिबंध पूर्ण। सफल: {success_count}, विफल: {failed_count}।"
    },
    "BCASTSELF_USER_USAGE_ERROR_ARGS": {
        "english": "❌ Invalid arguments for /bcastself user broadcast. Usage: <code>/bcastself user [interval]</code>",
        "hindi": "❌ उपयोगकर्ता प्रसारण के लिए अमान्य तर्क। उपयोग: <code>/bcastself user [interval]</code>"
    },
    "BCASTSELF_GROUP_USAGE_ERROR_ARGS": {
        "english": "❌ Invalid arguments for /bcastself group broadcast. Usage: <code>/bcastself group [interval]</code>",
        "hindi": "❌ समूह प्रसारण के लिए अमान्य तर्क। उपयोग: <code>/bcastself group [interval]</code>"
    },
    "BCASTSELF_COMBINED_USAGE_ERROR_ARGS": {
        "english": "❌ Invalid arguments for /bcastself combined broadcast. Usage: <code>/bcastself combined [interval]</code>",
        "hindi": "❌ संयुक्त प्रसारण के लिए अमान्य तर्क। उपयोग: <code>/bcastself combined [interval]</code>"
    },
    "BCAST_SCHEDULED_USERS": {
        "english": "✅ Broadcast to users scheduled with interval {interval}. Job name: {job_name}",
        "hindi": "✅ उपयोगकर्ताओं के लिए प्रसारण {interval} अंतराल के साथ निर्धारित। जॉब नाम: {job_name}"
    },
    "BCAST_SCHEDULED_GROUPS": {
        "english": "✅ Broadcast to groups scheduled with interval {interval}. Job name: {job_name}",
        "hindi": "✅ समूहों के लिए प्रसारण {interval} अंतराल के साथ निर्धारित। जॉब नाम: {job_name}"
    },
    "BCAST_SCHEDULED_COMBINED": {
        "english": "✅ Combined broadcast to users and groups scheduled with interval {interval}. Job name: {job_name}",
        "hindi": "✅ उपयोगकर्ताओं और समूहों के लिए संयुक्त प्रसारण {interval} अंतराल के साथ निर्धारित। जॉब नाम: {job_name}"
    },
    "BCASTSELF_STARTED_MESSAGE_COMBINED": {
        "english": "Initiating combined self-promotion broadcast to all users and groups...",
        "hindi": "सभी उपयोगकर्ताओं और समूहों के लिए संयुक्त स्व-प्रचार प्रसारण शुरू..."
    },
    "BCASTSELF_COMPLETE_MESSAGE_COMBINED": {
        "english": "✅ Combined self-promotion broadcast complete. Users - Sent: {sent_users}, Failed: {failed_users}; Groups - Sent: {sent_groups}, Failed: {failed_groups}",
        "hindi": "✅ संयुक्त स्व-प्रचार प्रसारण पूर्ण। उपयोगकर्ता - भेजे गए: {sent_users}, विफल: {failed_users}; समूह - भेजे गए: {sent_groups}, विफल: {failed_groups}"
    },
    "PERMANENT_TEXT": {
        "english": "Permanent",
        "hindi": "स्थायी"
    },
    "NOT_APPLICABLE": {
        "english": "N/A",
        "hindi": "लागू नहीं"
    },
    "LANG_BUTTON_PREV": {
        "english": "⬅️ Previous",
        "hindi": "⬅️ पिछला"
    },
    "LANG_BUTTON_NEXT": {
        "english": "➡️ Next",
        "hindi": "➡️ अगला"
    },
    "LANG_SELECT_PROMPT": {
        "english": "🌐 Please select your preferred language:",
        "hindi": "🌐 कृपया अपनी पसंदीदा भाषा चुनें:"
    },
    "LANG_UPDATED_USER": {
        "english": "✅ Language updated to {language} for you.",
        "hindi": "✅ आपके लिए भाषा {language} में अपडेट की गई।"
    },
    "LANG_UPDATED_GROUP": {
        "english": "✅ Language updated to {language} for this group.",
        "hindi": "✅ इस समूह के लिए भाषा {language} में अपडेट की गई।"
    },
    "LANG_MORE_COMING_SOON": {
        "english": "ℹ️ More languages coming soon!",
        "hindi": "ℹ️ जल्द ही और भाषाएँ उपलब्ध होंगी!"
    },
}

LANGUAGE_STRINGS[SENDER_PROFILE_VIOLATION_REASON] = {
    "english": "Sender's profile ({field}) contains issues: {issue_type}",
    "hindi": "प्रेषक का प्रोफाइल ({field}) में समस्याएँ हैं: {issue_type}"
}
LANGUAGE_STRINGS[MESSAGE_VIOLATION_REASON] = {
    "english": "Message contains forbidden content: {message_issue_type}",
    "hindi": "संदेश में निषिद्ध सामग्री है: {message_issue_type}"
}
LANGUAGE_STRINGS[MENTIONED_USER_PROFILE_VIOLATION_REASON]= {
    "english": "Mentioned user(s) profile violation: {users_summary}",
    "hindi": "उल्लिखित उपयोगकर्ता(ओं) का प्रोफाइल उल्लंघन: {users_summary}"
}
LANGUAGE_STRINGS[NEW_USER_PROFILE_VIOLATION_REASON] = {
    "english": "New user's profile ({field}) contains issues: {issue_type}",
    "hindi": "नए उपयोगकर्ता का प्रोफाइल ({field}) में समस्याएँ हैं: {issue_type}"
}
LANGUAGE_STRINGS[SENDER_IS_BAD_ACTOR_REASON] = {
    "english": "Thou art marked a knave for vile deeds past, and thus art shunned!",
    "hindi": "तू पूर्व के घृणित कर्मों हेतु दुष्ट ठहराया गया, अतः तुझे बहिष्कृत किया जाता है!"
}
LANGUAGE_STRINGS["MENTION_VIOLATION_REASON"] = {
    "english": "Mentioned user(s) profile violation: {users_summary}",
    "hindi": "उल्लिखित उपयोगकर्ता(ओं) का प्रोफाइल उल्लंघन: {users_summary}"
}
LANGUAGE_STRINGS["BIO_LINK_VIOLATION_REASON"] = {
    "english": "Bio contains forbidden links: {issue_type}",
    "hindi": "बायो में निषिद्ध लिंक्स हैं: {issue_type}"
}
LANGUAGE_STRINGS["BIO_LINK_DIALOGUES_LIST"] = [
    {
        "english": (
            "O reckless knave, thy bio doth betray!\n"
            "With vile links that spread corruption’s seed.\n"
            "Purge this filth, or face our righteous wrath,\n"
            "For purity we guard with iron will."
        ),
        "hindi": (
            "हे लापरवाह दुष्ट, तेरा बायो धोखा देता!\n"
            "घृणित लिंक्स जो भ्रष्टाचार के बीज बोते।\n"
            "इस मैल को साफ कर, वरना हमारे धर्मी क्रोध का सामना कर,\n"
            "क्योंकि हम पवित्रता की रक्षा लौह इच्छा से करते हैं।"
        )
    },
    {
        "english": (
            "Fie upon thee, whose bio bears foul links,\n"
            "A herald of deceit and base intent.\n"
            "Remove these chains, or be cast out anon,\n"
            "Our group shall stand untainted and pure."
        ),
        "hindi": (
            "धिक्कार है तुझ पर, जिसका बायो घृणित लिंक्स रखता,\n"
            "धोखे और नीच इरादों का संदेशवाहक।\n"
            "इन जंजीरों को हटाओ, नहीं तो जल्द बाहर फेंका जाओगे,\n"
            "हमारा समूह शुद्ध और निर्मल रहेगा।"
        )
    },
    {
        "english": (
            "O foul betrayer, thy bio doth proclaim\n"
            "A siren’s call to chaos and deceit.\n"
            "Cut these ties, or suffer swift expulsion,\n"
            "For here no villain’s shadow shall abide."
        ),
        "hindi": (
            "हे घृणित धोखेबाज, तेरा बायो घोषणा करता है\n"
            "अराजकता और छल का सायरन कॉल।\n"
            "इन बंधनों को काट, नहीं तो त्वरित निष्कासन सह,\n"
            "क्योंकि यहाँ किसी खलनायक की छाया नहीं टिकेगी।"
        )
    },
    {
        "english": (
            "Thy bio, a plague upon our sacred trust,\n"
            "Spreading venom with each cursed link.\n"
            "Cleanse thyself, or be forever shunned,\n"
            "For purity’s sake, we cast thee out."
        ),
        "hindi": (
            "तेरा बायो, हमारे पवित्र विश्वास पर प्लेग है,\n"
            "हर शापित लिंक से विष फैलाता।\n"
            "अपने आप को साफ कर, नहीं तो सदा के लिए बहिष्कृत हो,\n"
            "पवित्रता के लिए, हम तुझे बाहर फेंक देते हैं।"
        )
    },
    {
        "english": (
            "O knave, whose bio doth corrupt the pure,\n"
            "With links that sow the seeds of ruin.\n"
            "Purge this filth, or face eternal scorn,\n"
            "Our sentinel shall guard this hallowed ground."
        ),
        "hindi": (
            "हे दुष्ट, जिसका बायो शुद्ध को भ्रष्ट करता,\n"
            "ऐसे लिंक्स जो विनाश के बीज बोते।\n"
            "इस मैल को साफ कर, नहीं तो सदा के लिए तिरस्कार सह,\n"
            "हमारा प्रहरी इस पवित्र भूमि की रक्षा करेगा।"
        )
    },
    {
        "english": (
            "Thou art a traitor, thy bio stained with lies,\n"
            "A serpent’s tongue that poisons all who read.\n"
            "Be cleansed, or be forever cast aside,\n"
            "For here we tolerate no venomous creed."
        ),
        "hindi": (
            "तू एक द्रोही है, तेरा बायो झूठ से दागदार,\n"
            "एक सांप की जीभ जो पढ़ने वालों को ज़हरीला बनाती।\n"
            "साफ हो जा, नहीं तो सदा के लिए बाहर फेंक दिया जाएगा,\n"
            "क्योंकि यहाँ हम विषैले विश्वास को सहन नहीं करते।"
        )
    },
    {
        "english": (
            "Thy bio, a canvas stained with forbidden marks!\n"
            "Each link, a chain to realms we disavow.\n"
            "Scrape clean this taint, or be forever banned,\n"
            "From our domain, where virtue holds the sway."
        ),
        "hindi": (
            "तेरा बायो, निषिद्ध निशानों से सना हुआ कैनवास!\n"
            "हर लिंक, उन लोकों की श्रृंखला जिसे हम अस्वीकार करते हैं।\n"
            "इस दाग को साफ कर, वरना सदा के लिए प्रतिबंधित हो,\n"
            "हमारे क्षेत्र से, जहाँ सदाचार का राज चलता है।"
        )
    },
    {
        "english": (
            "Alas, thy bio speaks of dark intent!\n"
            "Through wicked links, corruption finds its way.\n"
            "Sever these ties, or feel the righteous sword,\n"
            "That guards our peace and keeps the shadows back."
        ),
        "hindi": (
            "हाय, तेरा बायो दुष्ट इरादों की बात करता है!\n"
            "दुष्ट लिंक्स के माध्यम से, भ्रष्टाचार अपना रास्ता पाता है।\n"
            "इन बंधनों को तोड़, वरना धर्मी तलवार को महसूस कर,\n"
            "जो हमारी शांति की रक्षा करती है और छायाओं को दूर रखती है।"
        )
    },
    # Four New Dialogues
    {
        "english": (
            "Woe unto thee, whose bio weaves a snare!\n"
            "Links of treachery that imperil our kin.\n"
            "Cast off this guile, or face exile’s despair,\n"
            "For our bastion stands firm ‘gainst thy sin."
        ),
        "hindi": (
            "हाय तुझ पर, जिसका बायो जाल बुनता है!\n"
            "विश्वासघात के लिंक्स जो हमारे कुटुंब को संकट में डालते।\n"
            "इस छल को त्याग, वरना निर्वासन की निराशा का सामना कर,\n"
            "क्योंकि हमारा गढ़ तेरे पाप के खिलाफ अडिग खड़ा है।"
        )
    },
    {
        "english": (
            "Thy bio’s script, a harbinger of woe,\n"
            "With links that tempt the soul to darksome end.\n"
            "Purge this evil, or be struck by our decree,\n"
            "For righteousness prevails where thou dost bend."
        ),
        "hindi": (
            "तेरा बायो का लेख, संकट का दूत,\n"
            "लिंक्स जो आत्मा को अंधेरे अंत की ओर लुभाते।\n"
            "इस बुराई को साफ कर, वरना हमारे फरमान से प्रहारित हो,\n"
            "क्योंकि धर्म जहाँ तू झुकता है वहाँ विजय पाता है।"
        )
    },
    {
        "english": (
            "O shadowed soul, thy bio’s mark is dire,\n"
            "Links aflame with treachery’s dark fire.\n"
            "Quench this flame, or face our stern rebuke,\n"
            "For sanctity’s light shall ne’er be forsook."
        ),
        "hindi": (
            "हे छायादार आत्मा, तेरे बायो का निशान भयंकर,\n"
            "लिंक्स विश्वासघात की काली आग से जलते।\n"
            "इस ज्वाला को बुझा, वरना हमारे कठोर निषेध का सामना कर,\n"
            "क्योंकि पवित्रता का प्रकाश कभी त्यागा नहीं जाएगा।"
        )
    },
    {
        "english": (
            "Thou vile scribe, thy bio doth offend,\n"
            "With chains of links that virtuous hearts rend.\n"
            "Cleanse thy words, or be cast from our grace,\n"
            "For justice reigns in this our sacred place."
        ),
        "hindi": (
            "हे नीच लेखक, तेरा बायो अपमान करता है,\n"
            "लिंक्स की जंजीरों से जो सच्चरित्र हृदयों को चीरते।\n"
            "अपने शब्द साफ कर, वरना हमारी कृपा से बहिष्कृत हो,\n"
            "क्योंकि न्याय हमारे इस पवित्र स्थान में राज करता है।"
        )
    },
]


LANGUAGE_STRINGS[MESSAGE_CONTENT_DIALOGUES_LIST] = [
    {
        "english": "Hearken, user! Thy message holds foul words, a blight upon this noble chat.\nCleanse thy tongue, lest thou be silenced by our decree!",
        "hindi": "ध्यान दो, उपयोगकर्ता! तुम्हारे संदेश में अपशब्द हैं, इस महान चैट पर एक धब्बा।\nअपनी ज़बान साफ करो, वरना हमारी आज्ञा से चुप करा दिए जाओगे!"
    },
]
LANGUAGE_STRINGS[MENTION_VIOLATION_DIALOGUES_LIST] = [
    {
        "english": "Thy mention of knaves with foul profiles brings shame! Their silence is our decree.",
        "hindi": "दुष्ट प्रोफाइल वाले व्यक्तियों का उल्लेख शर्मिंदगी लाता है! उनकी चुप्पी हमारा आदेश है।"
    },
]

LANGUAGE_STRINGS.update({
    "BOT_AWAKENS_MESSAGE": {
        "english": "Bard's Sentinel (PTB v{TG_VER}) awakens...",
        "hindi": "बार्ड्स सेंटिनल (PTB v{TG_VER}) जागृत होता है..."
    },
    "CACHE_CLEANUP_JOB_SCHEDULED_MESSAGE": {
        "english": "🧠 Cache cleanup scheduled every {interval}.",
        "hindi": "🧠 कैश सफाई हर {interval} पर निर्धारित।"
    }
})

