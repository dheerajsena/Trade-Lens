import os
from dataclasses import dataclass

@dataclass
class AppConfig:
    app_url: str = os.getenv("APP_URL", "http://localhost:8501")  # used in emails/links
    secret_key: str = os.getenv("APP_SECRET_KEY", "change-me")    # HMAC signing

app_cfg = AppConfig()
