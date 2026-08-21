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

    @abstractmethod
    async def send_password_changed_email(self, to_email: str) -> bool:
        """Notify that the account password changed."""
        ...

    @abstractmethod
    async def send_password_reset_email(
        self, to_email: str, token: str
    ) -> bool:
        """Send a password-reset link."""
        ...

    @abstractmethod
    async def send_password_reset_done_email(self, to_email: str) -> bool:
        """Notify that the password was reset."""
        ...

    @abstractmethod
    async def send_email_change_confirm_email(
        self, to_email: str, token: str
    ) -> bool:
        """Send a confirm-email-change link to the new address."""
        ...

    @abstractmethod
    async def send_email_change_old_notification(
        self, to_email: str, revert_token: str
    ) -> bool:
        """Notify the old address with a revert link."""
        ...

    @abstractmethod
    async def send_email_changed_notice(self, to_email: str) -> bool:
        """Notify that the email was changed."""
        ...

    @abstractmethod
    async def send_email_change_reverted_notice(self, to_email: str) -> bool:
        """Notify that the email change was reverted."""
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
        verification_url = (
            f'{settings.app_url}/api/v1/auth/verify-email/{token}'
        )

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

    async def send_password_changed_email(self, to_email: str) -> bool:
        message = EmailMessage()
        message['From'] = self.from_email
        message['To'] = to_email
        message['Subject'] = 'Your Questr password was changed'
        message.set_content(
            'Your Questr account password was changed. '
            'If this was not you, contact support immediately.'
        )
        message.add_alternative(
            '<html><body>'
            '<p>Your Questr account password was changed.</p>'
            '<p>If this was not you, contact support immediately.</p>'
            '</body></html>',
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
            logger.info('Password-changed email sent to %s', to_email)
            return True
        except Exception:  # noqa: BLE001
            logger.exception(
                'Failed to send password-changed email to %s', to_email
            )
            return False

    async def send_password_reset_email(
        self, to_email: str, token: str
    ) -> bool:
        reset_url = f'{settings.app_url}/api/v1/auth/reset-password/{token}'
        message = EmailMessage()
        message['From'] = self.from_email
        message['To'] = to_email
        message['Subject'] = 'Reset your Questr password'
        message.set_content(
            f'Click the following link to reset your password: {reset_url}'
        )
        message.add_alternative(
            f'<html><body>'
            f'<p>Click the following link to reset your password:</p>'
            f'<p><a href="{reset_url}">{reset_url}</a></p>'
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
            logger.info('Password-reset email sent to %s', to_email)
            return True
        except Exception:  # noqa: BLE001
            logger.exception(
                'Failed to send password-reset email to %s', to_email
            )
            return False

    async def send_password_reset_done_email(self, to_email: str) -> bool:
        message = EmailMessage()
        message['From'] = self.from_email
        message['To'] = to_email
        message['Subject'] = 'Your Questr password was reset'
        message.set_content(
            'Your Questr password was reset. '
            'If this was not you, contact support immediately.'
        )
        message.add_alternative(
            '<html><body>'
            '<p>Your Questr password was reset.</p>'
            '<p>If this was not you, contact support immediately.</p>'
            '</body></html>',
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
            logger.info('Password-reset-done email sent to %s', to_email)
            return True
        except Exception:  # noqa: BLE001
            logger.exception(
                'Failed to send password-reset-done email to %s', to_email
            )
            return False

    async def send_email_change_confirm_email(
        self, to_email: str, token: str
    ) -> bool:
        confirm_url = (
            f'{settings.app_url}/api/v1/auth/me/email/confirm/{token}'
        )
        message = EmailMessage()
        message['From'] = self.from_email
        message['To'] = to_email
        message['Subject'] = 'Confirm your new Questr email'
        message.set_content(
            f'Click the following link to confirm your new email: '
            f'{confirm_url}'
        )
        message.add_alternative(
            f'<html><body>'
            f'<p>Click the following link to confirm your new email:</p>'
            f'<p><a href="{confirm_url}">{confirm_url}</a></p>'
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
            logger.info('Email-change confirm email sent to %s', to_email)
            return True
        except Exception:  # noqa: BLE001
            logger.exception(
                'Failed to send email-change confirm email to %s', to_email
            )
            return False

    async def send_email_change_old_notification(
        self, to_email: str, revert_token: str
    ) -> bool:
        revert_url = (
            f'{settings.app_url}/api/v1/auth/me/email/revert/{revert_token}'
        )
        message = EmailMessage()
        message['From'] = self.from_email
        message['To'] = to_email
        message['Subject'] = 'Your Questr email was changed'
        message.set_content(
            f'Your Questr email was changed. If this was not you, '
            f'click the following link to revert it: {revert_url}'
        )
        message.add_alternative(
            f'<html><body>'
            f'<p>Your Questr email was changed.</p>'
            f'<p>If this was not you, click the following link to '
            f'revert it:</p>'
            f'<p><a href="{revert_url}">{revert_url}</a></p>'
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
            logger.info('Email-change old notification sent to %s', to_email)
            return True
        except Exception:  # noqa: BLE001
            logger.exception(
                'Failed to send email-change old notification to %s',
                to_email,
            )
            return False

    async def send_email_changed_notice(self, to_email: str) -> bool:
        message = EmailMessage()
        message['From'] = self.from_email
        message['To'] = to_email
        message['Subject'] = 'Your Questr email was changed'
        message.set_content(
            'Your Questr email was changed. '
            'If this was not you, contact support immediately.'
        )
        message.add_alternative(
            '<html><body>'
            '<p>Your Questr email was changed.</p>'
            '<p>If this was not you, contact support immediately.</p>'
            '</body></html>',
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
            logger.info('Email-changed notice sent to %s', to_email)
            return True
        except Exception:  # noqa: BLE001
            logger.exception(
                'Failed to send email-changed notice to %s', to_email
            )
            return False

    async def send_email_change_reverted_notice(self, to_email: str) -> bool:
        message = EmailMessage()
        message['From'] = self.from_email
        message['To'] = to_email
        message['Subject'] = 'Your Questr email change was reverted'
        message.set_content(
            'Your Questr email change was reverted. '
            'If this was not you, contact support immediately.'
        )
        message.add_alternative(
            '<html><body>'
            '<p>Your Questr email change was reverted.</p>'
            '<p>If this was not you, contact support immediately.</p>'
            '</body></html>',
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
            logger.info('Email-change-reverted notice sent to %s', to_email)
            return True
        except Exception:  # noqa: BLE001
            logger.exception(
                'Failed to send email-change-reverted notice to %s',
                to_email,
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

    async def send_password_changed_email(  # noqa: PLR6301
        self, to_email: str
    ) -> bool:
        logger.info('[DEV] Would send password-changed email to %s', to_email)
        return True

    async def send_password_reset_email(  # noqa: PLR6301
        self, to_email: str, token: str
    ) -> bool:
        logger.info(
            '[DEV] Would send password-reset email to %s with token: %s',
            to_email,
            token,
        )
        return True

    async def send_password_reset_done_email(  # noqa: PLR6301
        self, to_email: str
    ) -> bool:
        logger.info(
            '[DEV] Would send password-reset-done email to %s', to_email
        )
        return True

    async def send_email_change_confirm_email(  # noqa: PLR6301
        self, to_email: str, token: str
    ) -> bool:
        logger.info(
            '[DEV] Would send email-change confirm email to %s with token: %s',
            to_email,
            token,
        )
        return True

    async def send_email_change_old_notification(  # noqa: PLR6301
        self, to_email: str, revert_token: str
    ) -> bool:
        logger.info(
            '[DEV] Would send email-change old notification to %s with '
            'revert token: %s',
            to_email,
            revert_token,
        )
        return True

    async def send_email_changed_notice(  # noqa: PLR6301
        self, to_email: str
    ) -> bool:
        logger.info('[DEV] Would send email-changed notice to %s', to_email)
        return True

    async def send_email_change_reverted_notice(  # noqa: PLR6301
        self, to_email: str
    ) -> bool:
        logger.info(
            '[DEV] Would send email-change-reverted notice to %s', to_email
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
