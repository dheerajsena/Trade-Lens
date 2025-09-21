import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from config import app_cfg
import os

def _smtp_cfg():
    return dict(
        host=os.getenv("SMTP_HOST",""),
        port=int(os.getenv("SMTP_PORT","587")),
        user=os.getenv("SMTP_USER",""),
        pw=os.getenv("SMTP_PASS",""),
        from_email=os.getenv("FROM_EMAIL","no-reply@yourapp.com"),
    )

def send_email(to_email: str, subject: str, html_body: str):
    cfg = _smtp_cfg()
    if not (cfg["host"] and cfg["user"] and cfg["pw"]):
        # Mock fallback — caller can display link in UI
        return {"ok": False, "mock": True}
    msg = MIMEText(html_body, "html")
    msg["Subject"] = subject
    msg["From"] = formataddr(("Swing Tracker", cfg["from_email"]))
    msg["To"] = to_email
    with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
        server.starttls()
        server.login(cfg["user"], cfg["pw"])
        server.sendmail(cfg["from_email"], [to_email], msg.as_string())
    return {"ok": True, "mock": False}
