"""
Gmail SMTP email sender.

Sends a finished EPUB file as an attachment to the given recipient address.
Credentials are read from the app Settings (which loads from .env).
"""
import logging
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)
_MAX_ATTACHMENT_MB = 24  # Gmail hard limit is 25 MB; keep a 1 MB margin

def send_epub_to_email(
    epub_path: Path,
    recipient_email: str,
    retries: int = 3,
) -> bool:
    """
    Send an EPUB file via Gmail SMTP (port 587, STARTTLS).

    Args:
        epub_path: Absolute path to the .epub file.
        recipient_email: Destination email address.
        retries: Number of send attempts before giving up.

    Returns:
        True on success, False if all retries failed.

    Raises:
        FileNotFoundError: If the EPUB file doesn't exist.
        ValueError: If credentials are missing or the file is too large.
    """
    settings = get_settings()

    if not epub_path.exists():
        raise FileNotFoundError(f"EPUB file not found: {epub_path}")

    if not settings.gmail_user or not settings.gmail_app_password:
        raise ValueError(
            "GMAIL_USER and GMAIL_APP_PASSWORD must be set in the .env file"
        )

    epub_data = epub_path.read_bytes()
    file_size_mb = len(epub_data) / (1024 * 1024)
    if file_size_mb > _MAX_ATTACHMENT_MB:
        raise ValueError(
            f"EPUB is too large for Gmail attachment ({file_size_mb:.2f} MB — limit is {_MAX_ATTACHMENT_MB} MB)"
        )

    msg = EmailMessage()
    msg["Subject"] = f"Novel Delivered: {epub_path.stem}"
    msg["From"] = settings.gmail_user
    msg["To"] = recipient_email
    msg.set_content(f"Your requested novel '{epub_path.stem}' is attached.")
    msg.add_attachment(
        epub_data,
        maintype="application",
        subtype="epub+zip",
        filename=epub_path.name,
    )

    for attempt in range(1, retries + 1):
        try:
            logger.info("Email attempt %d/%d — connecting to Gmail SMTP…", attempt, retries)
            with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
                smtp.starttls()
                smtp.login(settings.gmail_user, settings.gmail_app_password)
                smtp.send_message(msg)
            logger.info("Email sent successfully to %s", recipient_email)
            return True
        except Exception as exc:
            logger.warning("Email attempt %d/%d failed: %s", attempt, retries, exc)
            if attempt < retries:
                time.sleep(5 * attempt)
    return False
