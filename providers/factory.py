"""Call provider factory — swap provider via config only."""

import logging

from config import get_settings
from providers.call_provider import CallProvider
from providers.desktop_call_provider import DesktopCallProvider
from providers.future_telephony_provider import TelephonyCallProvider

logger = logging.getLogger(__name__)


def get_call_provider() -> CallProvider:
    """
    Return the configured call provider.

    To migrate to telephony, change CALL_PROVIDER=telephony in .env.
    No other code needs to change.
    """
    settings = get_settings()
    if settings.call_provider == "telephony":
        logger.info("Using TelephonyCallProvider")
        return TelephonyCallProvider()
    logger.info("Using DesktopCallProvider (development simulator)")
    return DesktopCallProvider()
