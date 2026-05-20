"""
SMTP email service for OTP delivery.

send_otp_email() is the single public function.  It never raises — all
failures are logged and the caller receives a bool indicating success.
This ensures a broken SMTP config can never abort the login flow.

Configuration (all via .env / environment variables):
    SMTP_HOST        smtp.gmail.com
    SMTP_PORT        587  (STARTTLS)
    SMTP_USERNAME    workhivehr@gmail.com
    SMTP_PASSWORD    <16-character Gmail App Password>
    SMTP_FROM_EMAIL  workhivehr@gmail.com  (default)

Gmail setup:
    1. Enable 2-Step Verification on the Google Account.
    2. Go to Google Account → Security → 2-Step Verification → App passwords.
    3. Create an App password for "Mail" / "Other (HRMS)".
    4. Paste the 16-character code into SMTP_PASSWORD in .env.

If SMTP_PASSWORD is empty the function logs a warning and returns False,
which causes otp_tasks.py to fall back to console-only logging.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)

_SUBJECT = "WorkHive HRMS Login Verification Code"
_FROM_DISPLAY = f"Acronotics HR <{settings.SMTP_FROM_EMAIL}>"


def _build_plain(otp: str, full_name: str) -> str:
    greeting = f"Hi {full_name}," if full_name else "Hi,"
    return (
        f"{greeting}\n\n"
        f"You are receiving this email because a login was attempted on your\n"
        f"WorkHive HRMS account.\n\n"
        f"Your one-time verification code is:\n\n"
        f"    {otp}\n\n"
        f"This code is valid for 2 minutes. Do not share it with anyone.\n\n"
        f"If you did not attempt to log in, please contact your administrator\n"
        f"immediately and do not use this code.\n\n"
        f"— Acronotics HR Team\n"
        f"  Acronotics Limited\n"
    )


def _build_html(otp: str, full_name: str) -> str:
    greeting = f"Hi {full_name}," if full_name else "Hi,"
    # Outlook-bulletproof: 100%-table layout, inline styles, MSO conditionals,
    # explicit width on Outlook fallback table, no CSS shorthand background.
    return f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office" lang="en">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<meta http-equiv="X-UA-Compatible" content="IE=edge" />
<meta name="x-apple-disable-message-reformatting" />
<title>WorkHive HRMS Login Verification</title>
<!--[if mso]>
<style type="text/css">
table {{ border-collapse: collapse; }}
td   {{ font-family: Arial, sans-serif; mso-line-height-rule: exactly; }}
.otp-code {{ font-family: 'Courier New', Courier, monospace !important; }}
</style>
<xml>
  <o:OfficeDocumentSettings>
    <o:AllowPNG/>
    <o:PixelsPerInch>96</o:PixelsPerInch>
  </o:OfficeDocumentSettings>
</xml>
<![endif]-->
<style type="text/css">
  /* Force table cells to behave on Outlook */
  table, td {{ border-collapse: collapse !important; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
  img {{ -ms-interpolation-mode: bicubic; border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; }}
  body, #bodyTable {{ width: 100% !important; height: 100% !important; margin: 0; padding: 0; background-color: #f2f4f7; }}
  /* Mobile */
  @media screen and (max-width: 480px) {{
    .container       {{ width: 100% !important; }}
    .px-pad          {{ padding-left: 16px !important; padding-right: 16px !important; }}
    .otp-code        {{ font-size: 28px !important; letter-spacing: 6px !important; }}
    .header-title    {{ font-size: 20px !important; }}
  }}
  /* Dark-mode hint (Outlook ignores this; safe) */
  @media (prefers-color-scheme: dark) {{
    body {{ background-color: #1a202c !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background-color:#f2f4f7;font-family:Arial,Helvetica,sans-serif;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">

  <!-- Hidden preheader for inbox preview -->
  <div style="display:none;font-size:1px;color:#f2f4f7;line-height:1px;max-height:0px;max-width:0px;opacity:0;overflow:hidden;mso-hide:all;">
    Your WorkHive HRMS verification code is {otp}. Valid for 2 minutes.
  </div>

  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" id="bodyTable" style="background-color:#f2f4f7;">
    <tr>
      <td align="center" valign="top" style="padding:40px 16px;">
        <!--[if mso]>
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="420" align="center"><tr><td>
        <![endif]-->
        <table role="presentation" class="container" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width:420px;background-color:#ffffff;border:1px solid #e2e6ea;border-radius:10px;">
          <!-- HEADER -->
          <tr>
            <td align="center" bgcolor="#2d3ec9" style="background-color:#2d3ec9;padding:28px 32px 24px;border-radius:10px 10px 0 0;">
              <p style="margin:0 0 4px;color:#c7d2fe;font-size:11px;font-weight:bold;letter-spacing:3px;text-transform:uppercase;font-family:Arial,Helvetica,sans-serif;">
                Acronotics HRMS
              </p>
              <p class="header-title" style="margin:0;color:#ffffff;font-size:22px;font-weight:bold;font-family:Arial,Helvetica,sans-serif;">
                Login Verification
              </p>
            </td>
          </tr>
          <!-- BODY -->
          <tr>
            <td class="px-pad" style="padding:32px 32px 24px;font-family:Arial,Helvetica,sans-serif;">
              <p style="margin:0 0 14px;color:#1e293b;font-size:15px;line-height:22px;">{greeting}</p>
              <p style="margin:0 0 28px;color:#475569;font-size:14px;line-height:22px;">
                A sign-in attempt was made on your <strong>WorkHive HRMS</strong> account.
                Enter the verification code below to complete your login.
              </p>

              <!-- OTP BOX -->
              <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td align="center" bgcolor="#f0f4ff" style="background-color:#f0f4ff;border:2px solid #2d3ec9;border-radius:8px;padding:20px 16px;">
                    <p style="margin:0 0 8px;color:#64748b;font-size:11px;font-weight:bold;letter-spacing:2px;text-transform:uppercase;font-family:Arial,Helvetica,sans-serif;">
                      Your verification code
                    </p>
                    <p class="otp-code" style="margin:0;color:#2d3ec9;font-family:'Courier New',Courier,monospace;font-size:32px;font-weight:bold;letter-spacing:8px;line-height:38px;mso-line-height-rule:exactly;">
                      {otp}
                    </p>
                  </td>
                </tr>
              </table>

              <!-- EXPIRY ALERT -->
              <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-top:20px;">
                <tr>
                  <td bgcolor="#fffbeb" style="background-color:#fffbeb;border-left:4px solid #f59e0b;border-radius:4px;padding:12px 16px;">
                    <p style="margin:0;color:#92400e;font-size:13px;line-height:18px;font-family:Arial,Helvetica,sans-serif;">
                      &#9679; This code is valid for <strong>2 minutes</strong>. Do not share it with anyone.
                    </p>
                  </td>
                </tr>
              </table>

              <p style="margin:20px 0 0;color:#94a3b8;font-size:13px;line-height:18px;font-family:Arial,Helvetica,sans-serif;">
                If you did not request this code, you can safely ignore this email. Your account remains secure.
              </p>
            </td>
          </tr>
          <!-- FOOTER -->
          <tr>
            <td align="center" bgcolor="#f8fafc" style="background-color:#f8fafc;border-top:1px solid #e2e8f0;border-radius:0 0 10px 10px;padding:16px 32px;">
              <p style="margin:0;color:#94a3b8;font-size:12px;font-family:Arial,Helvetica,sans-serif;">
                &copy; WorkHive HRMS &bull; Acronotics Internal System
              </p>
            </td>
          </tr>
        </table>
        <!--[if mso]>
        </td></tr></table>
        <![endif]-->
      </td>
    </tr>
  </table>

</body>
</html>"""


def send_otp_email(to_email: str, otp: str, full_name: str = "") -> bool:
    """
    Send an OTP verification email via Gmail SMTP / STARTTLS.

    Returns True on success, False on any failure.  Never raises.
    Fallback: caller (otp_tasks.py) always logs the OTP to the console
    regardless of this function's return value.
    """
    if not settings.SMTP_HOST or not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        logger.warning(
            "[EMAIL] SMTP not fully configured — skipping delivery to %s", to_email
        )
        return False

    try:
        msg = EmailMessage()
        msg["Subject"] = _SUBJECT
        msg["From"] = _FROM_DISPLAY
        msg["To"] = to_email
        msg["Reply-To"] = settings.SMTP_FROM_EMAIL
        msg["X-Mailer"] = "WorkHive HRMS System"

        msg.set_content(_build_plain(otp, full_name))
        msg.add_alternative(_build_html(otp, full_name), subtype="html")

        context = ssl.create_default_context()
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(msg)

        logger.info("[EMAIL] OTP sent to %s", to_email)
        return True

    except smtplib.SMTPAuthenticationError as exc:
        logger.error(
            "[EMAIL ERROR] Failed to send OTP to %s: auth error — "
            "check SMTP_USERNAME / SMTP_PASSWORD (%s)",
            to_email, exc,
        )
    except smtplib.SMTPConnectError as exc:
        logger.error(
            "[EMAIL ERROR] Failed to send OTP to %s: cannot connect to %s:%d (%s)",
            to_email, settings.SMTP_HOST, settings.SMTP_PORT, exc,
        )
    except smtplib.SMTPException as exc:
        logger.error("[EMAIL ERROR] Failed to send OTP to %s: %s", to_email, exc)
    except OSError as exc:
        logger.error("[EMAIL ERROR] Failed to send OTP to %s: network error — %s", to_email, exc)
    except Exception as exc:
        logger.exception("[EMAIL ERROR] Failed to send OTP to %s: unexpected error — %s", to_email, exc)

    return False
