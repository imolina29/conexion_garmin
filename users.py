"""User management: registration, storage, encryption, rate limiting."""

import json
import logging
from datetime import date
from pathlib import Path

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
USERS_DIR = DATA_DIR / "users"

DAILY_MESSAGE_LIMIT = 30


class UserManager:
    def __init__(self, encryption_key: str | None = None, users_dir: Path | None = None):
        self._users_dir = users_dir or USERS_DIR
        self._fernet = Fernet(encryption_key.encode()) if encryption_key else None

    def _user_dir(self, telegram_id: int) -> Path:
        return self._users_dir / str(telegram_id)

    def _config_path(self, telegram_id: int) -> Path:
        return self._user_dir(telegram_id) / "config.json"

    def activities_dir(self, telegram_id: int) -> Path:
        return self._user_dir(telegram_id) / "raw" / "activities"

    def stats_dir(self, telegram_id: int) -> Path:
        return self._user_dir(telegram_id) / "raw" / "stats"

    def token_store_path(self, telegram_id: int) -> Path:
        return self._user_dir(telegram_id) / ".garmin_session"

    def _encrypt(self, text: str) -> str:
        if self._fernet:
            return self._fernet.encrypt(text.encode()).decode()
        return text

    def _decrypt(self, text: str) -> str:
        if self._fernet:
            return self._fernet.decrypt(text.encode()).decode()
        return text

    def _load_raw(self, telegram_id: int) -> dict | None:
        path = self._config_path(telegram_id)
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)

    def _save_raw(self, telegram_id: int, data: dict) -> None:
        path = self._config_path(telegram_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def user_exists(self, telegram_id: int) -> bool:
        return self._config_path(telegram_id).exists()

    def get_garmin_credentials(self, telegram_id: int) -> tuple[str, str] | None:
        data = self._load_raw(telegram_id)
        if not data:
            return None
        return self._decrypt(data["garmin_email"]), self._decrypt(data["garmin_password"])

    def get_profile(self, telegram_id: int) -> str:
        data = self._load_raw(telegram_id)
        if not data:
            return ""
        return data.get("profile", "")

    def create_user(self, telegram_id: int, garmin_email: str, garmin_password: str) -> None:
        self.activities_dir(telegram_id).mkdir(parents=True, exist_ok=True)
        self.stats_dir(telegram_id).mkdir(parents=True, exist_ok=True)
        data = {
            "telegram_id": telegram_id,
            "garmin_email": self._encrypt(garmin_email),
            "garmin_password": self._encrypt(garmin_password),
            "profile": "",
            "daily_limit": DAILY_MESSAGE_LIMIT,
            "daily_usage": {},
            "created_at": date.today().isoformat(),
        }
        self._save_raw(telegram_id, data)

    def update_profile(self, telegram_id: int, profile: str) -> None:
        data = self._load_raw(telegram_id)
        if not data:
            raise ValueError(f"User {telegram_id} not found")
        data["profile"] = profile
        self._save_raw(telegram_id, data)

    def check_rate_limit(self, telegram_id: int) -> tuple[bool, int]:
        data = self._load_raw(telegram_id)
        if not data:
            return False, 0
        daily_limit = data.get("daily_limit", DAILY_MESSAGE_LIMIT)
        usage = data.get("daily_usage", {})
        today = date.today().isoformat()
        used = usage.get(today, 0)
        remaining = daily_limit - used
        return remaining > 0, max(0, remaining)

    def increment_usage(self, telegram_id: int) -> None:
        data = self._load_raw(telegram_id)
        if not data:
            return
        today = date.today().isoformat()
        usage = data.get("daily_usage", {})
        data["daily_usage"] = {today: usage.get(today, 0) + 1}
        self._save_raw(telegram_id, data)
