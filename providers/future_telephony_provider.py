"""Future telephony provider stub — replace DesktopCallProvider via config only."""

import logging

from providers.call_provider import (
    CallContext,
    CallProvider,
    CallResult,
    CallResultStatus,
)

logger = logging.getLogger(__name__)


class TelephonyCallProvider(CallProvider):
    """
    Placeholder for future Twilio/Exotel/Plivo integration.

    When ready, implement real telephony here. No other code should change.
    """

    def __init__(self) -> None:
        logger.warning(
            "TelephonyCallProvider is not yet implemented. "
            "Set CALL_PROVIDER=desktop in .env for development."
        )

    async def initiate_call(self, context: CallContext) -> CallResult:
        raise NotImplementedError(
            "TelephonyCallProvider is not implemented. "
            "Use CALL_PROVIDER=desktop for development."
        )

    async def hang_up(self) -> None:
        pass

    def is_available(self) -> bool:
        return False
