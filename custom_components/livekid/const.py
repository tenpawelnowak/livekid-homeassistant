"""Constants for the LiveKid integration."""

from datetime import timedelta

DOMAIN = "livekid"
CONF_TOKEN = "token"
SCAN_INTERVAL = timedelta(minutes=15)
DEFAULT_CURRENCY = "PLN"
EVENT_MESSAGE = "livekid_message"
EVENT_NEWS = "livekid_news"
