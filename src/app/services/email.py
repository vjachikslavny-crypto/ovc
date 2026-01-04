from __future__ import annotations

import logging

from app.models.user import User

logger = logging.getLogger(__name__)


def send_verification_email(user: User, link: str) -> None:
    logger.info("OVC email mock: verify %s via %s", user.email, link)


def send_password_reset(user: User, link: str) -> None:
    logger.info("OVC email mock: reset %s via %s", user.email, link)

