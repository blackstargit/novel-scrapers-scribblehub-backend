import os
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path
from dotenv import load_dotenv

# Load env variables
load_dotenv()

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

def send_epub_to_email(epub_path: Path, recipient_email: str, retries: int = 3) -> bool:
    """Send an EPUB file via Gmail SMTP."""
    if not epub_path.exists():
        raise FileNotFoundError(f"EPUB file not found: {epub_path}")

    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        raise ValueError("GMAIL_USER and GMAIL_APP_PASSWORD must be strictly set in the .env file")

    msg = EmailMessage()
    msg['Subject'] = f"Novel Delivered: {epub_path.stem}"
    msg['From'] = GMAIL_USER
    msg['To'] = recipient_email
    msg.set_content(f"Attached is the downloaded EPUB for {epub_path.stem}.")

    with open(epub_path, 'rb') as f:
        epub_data = f.read()

    file_size_mb = len(epub_data) / (1024 * 1024)
    if file_size_mb > 24:
        raise ValueError(f"EPUB is too large for Gmail attachment ({file_size_mb:.2f} MB)")

    msg.add_attachment(epub_data, maintype='application', subtype='epub+zip', filename=epub_path.name)

    for attempt in range(1, retries + 1):
        try:
            print(f"Attempt {attempt}/{retries} — connecting to Gmail SMTP...")
            with smtplib.SMTP('smtp.gmail.com', 587) as smtp:
                smtp.starttls()
                smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
                smtp.send_message(msg)
            print("Email sent successfully!")
            return True
        except Exception as e:
            print(f"Attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(5 * attempt)

    return False
