import logging
from abc import ABC, abstractmethod

from questr.settings import settings

logger = logging.getLogger(__name__)


class BaseEmailService(ABC):
    @abstractmethod
    async def send_verification_email(
        self, to_email: str, token: str
    ) -> bool:
        """Send verification email. Returns True on success."""
        ...


class SmtpEmailService(BaseEmailService):
    """Email service using SMTP (e.g., Mailpit for local dev)."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        from_email: str,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_email = from_email

    async def send_verification_email(
        self, to_email: str, token: str
    ) -> bool:
        import aiosmtplib
        from email.message import EmailMessage

        verification_url = (
            f'POST /api/v1/auth/verify-email '
            f"with body: {{'token': '{token}'}}"
        )

        message = EmailMessage()
        message['From'] = self.from_email
        message['To'] = to_email
        message['Subject'] = 'Verify your Questr account'
        message.set_content(
            f'Click the following link to verify your email: '
            f'{verification_url}'
        )

        try:
            await aiosmtplib.send(
                message,
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                start_tls=True,
            )
            logger.info('Verification email sent to %s', to_email)
            return True
        except Exception:  # noqa: BLE001
            logger.exception(
                'Failed to send verification email to %s', to_email
            )
            return False


class ConsoleEmailService(BaseEmailService):
    """Development-only email service that logs instead of sending."""

    async def send_verification_email(  # noqa: PLR6301
        self, to_email: str, token: str
    ) -> bool:
        logger.info(
            '[DEV] Would send verification email to %s with token: %s',
            to_email,
            token,
        )
        return True


def get_email_service() -> BaseEmailService:
    """Factory function to get the configured email service."""
    if settings.EMAIL_ENABLED:
        return SmtpEmailService(
            host=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            from_email=settings.EMAIL_FROM,
        )
    return ConsoleEmailService()
