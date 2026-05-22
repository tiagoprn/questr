import logging
from abc import ABC, abstractmethod
from email.message import EmailMessage

import aiosmtplib

from questr.settings import settings

logger = logging.getLogger(__name__)


class BaseEmailService(ABC):
    @abstractmethod
    async def send_verification_email(self, to_email: str, token: str) -> bool:
        """Send verification email. Returns True on success."""
        ...


class SmtpEmailService(BaseEmailService):
    """Email service using SMTP (e.g., Mailpit for local dev)."""

    def __init__(  # noqa: PLR0913,PLR0917
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        from_email: str,
        use_starttls: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.use_starttls = use_starttls

    async def send_verification_email(self, to_email: str, token: str) -> bool:
        verification_url = f'{settings.app_url}/v1/auth/verify-email/{token}'

        message = EmailMessage()
        message['From'] = self.from_email
        message['To'] = to_email
        message['Subject'] = 'Verify your Questr account'
        message.set_content(
            f'Click the following link to verify your email: '
            f'{verification_url}'
        )
        message.add_alternative(
            f'<html><body>'
            f'<p>Click the following link to verify your email:</p>'
            f'<p><a href="{verification_url}">{verification_url}</a></p>'
            f'</body></html>',
            subtype='html',
        )

        try:
            await aiosmtplib.send(
                message,
                hostname=self.host,
                port=self.port,
                username=self.username or None,
                password=self.password or None,
                start_tls=self.use_starttls,
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
            use_starttls=settings.SMTP_USE_STARTTLS,
        )
    return ConsoleEmailService()
