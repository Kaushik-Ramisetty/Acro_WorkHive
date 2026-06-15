"""
Quick standalone test of the SMTP credentials in .env. Run with:

    python test_smtp.py your-email@example.com

It tries to send a one-line message to the given address and prints exactly
what Gmail says. Use this to confirm whether your App Password works WITHOUT
going through the FastAPI flow.
"""
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage

from dotenv import load_dotenv
load_dotenv()

if len(sys.argv) < 2:
    print("Usage: python test_smtp.py <recipient@email.com>")
    sys.exit(1)

to = sys.argv[1]
host = os.getenv("SMTP_HOST", "smtp.gmail.com")
port = int(os.getenv("SMTP_PORT", "587"))
user = os.getenv("SMTP_USERNAME", "")
pw   = (os.getenv("SMTP_PASSWORD", "") or "").replace(" ", "")
sender = os.getenv("SMTP_FROM_EMAIL", "") or user

print(f"Host:      {host}:{port}")
print(f"Username:  {user}")
print(f"Password:  {'*' * len(pw)} ({len(pw)} chars after stripping spaces)")
print(f"From:      {sender}")
print(f"To:        {to}")
print()

msg = EmailMessage()
msg["Subject"] = "HRMS SMTP test"
msg["From"]    = sender
msg["To"]      = to
msg.set_content("If you can read this, your SMTP credentials work.")

try:
    ctx = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=10) as smtp:
        smtp.set_debuglevel(1)   # show every SMTP turn
        smtp.ehlo()
        smtp.starttls(context=ctx)
        smtp.ehlo()
        smtp.login(user, pw)
        smtp.send_message(msg)
    print("\nSUCCESS - check the recipient inbox (and spam folder).")
except smtplib.SMTPAuthenticationError as e:
    print(f"\nAUTH FAILED: {e}")
    print("This usually means the Gmail App Password is wrong or revoked.")
    print("Generate a new one at https://myaccount.google.com/apppasswords")
except Exception as e:
    print(f"\nFAILED: {type(e).__name__}: {e}")
