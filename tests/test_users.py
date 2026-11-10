import json
from pathlib import Path

from cryptography.fernet import Fernet

from users import UserManager


def test_create_user_creates_directories(tmp_path):
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(123, "test@mail.com", "secret")
    assert (tmp_path / "123" / "raw" / "activities").is_dir()
    assert (tmp_path / "123" / "raw" / "stats").is_dir()
    assert (tmp_path / "123" / "config.json").exists()


def test_user_exists(tmp_path):
    mgr = UserManager(users_dir=tmp_path)
    assert not mgr.user_exists(123)
    mgr.create_user(123, "test@mail.com", "secret")
    assert mgr.user_exists(123)


def test_credentials_encrypted_on_disk(tmp_path):
    key = Fernet.generate_key().decode()
    mgr = UserManager(encryption_key=key, users_dir=tmp_path)
    mgr.create_user(123, "test@mail.com", "secret")

    raw = json.loads((tmp_path / "123" / "config.json").read_text())
    assert raw["garmin_email"] != "test@mail.com"
    assert raw["garmin_password"] != "secret"


def test_get_garmin_credentials_decrypts(tmp_path):
    key = Fernet.generate_key().decode()
    mgr = UserManager(encryption_key=key, users_dir=tmp_path)
    mgr.create_user(123, "test@mail.com", "secret")

    email, password = mgr.get_garmin_credentials(123)
    assert email == "test@mail.com"
    assert password == "secret"


def test_get_garmin_credentials_none_for_missing_user(tmp_path):
    mgr = UserManager(users_dir=tmp_path)
    assert mgr.get_garmin_credentials(999) is None


def test_update_profile(tmp_path):
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(123, "a@b.com", "p")
    assert mgr.get_profile(123) == ""

    mgr.update_profile(123, "Corro 3 veces por semana")
    assert mgr.get_profile(123) == "Corro 3 veces por semana"


def test_rate_limit_allows_within_limit(tmp_path):
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(123, "a@b.com", "p")

    allowed, remaining = mgr.check_rate_limit(123)
    assert allowed is True
    assert remaining == 30


def test_rate_limit_blocks_at_limit(tmp_path):
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(123, "a@b.com", "p")

    for _ in range(30):
        mgr.increment_usage(123)

    allowed, remaining = mgr.check_rate_limit(123)
    assert allowed is False
    assert remaining == 0


def test_increment_usage_counts(tmp_path):
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(123, "a@b.com", "p")

    mgr.increment_usage(123)
    mgr.increment_usage(123)

    allowed, remaining = mgr.check_rate_limit(123)
    assert allowed is True
    assert remaining == 28


def test_paths_per_user(tmp_path):
    mgr = UserManager(users_dir=tmp_path)
    assert mgr.activities_dir(111) != mgr.activities_dir(222)
    assert mgr.stats_dir(111) != mgr.stats_dir(222)
    assert "111" in str(mgr.activities_dir(111))
    assert "222" in str(mgr.activities_dir(222))


def test_no_encryption_stores_plaintext(tmp_path):
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(123, "test@mail.com", "secret")

    raw = json.loads((tmp_path / "123" / "config.json").read_text())
    assert raw["garmin_email"] == "test@mail.com"
    assert raw["garmin_password"] == "secret"


def test_calendar_token_generated_on_first_access(tmp_path):
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(123, "a@b.com", "p")

    token = mgr.get_calendar_token(123)
    assert token is not None
    assert len(token) == 32
    assert mgr.get_calendar_token(123) == token


def test_find_user_by_calendar_token(tmp_path):
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(111, "a@b.com", "p")
    mgr.create_user(222, "c@d.com", "p")

    token_111 = mgr.get_calendar_token(111)
    token_222 = mgr.get_calendar_token(222)

    assert mgr.find_user_by_calendar_token(token_111) == 111
    assert mgr.find_user_by_calendar_token(token_222) == 222
    assert mgr.find_user_by_calendar_token("nonexistent") is None


def test_save_and_get_plan(tmp_path):
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(123, "a@b.com", "p")

    assert mgr.get_plan(123) is None

    plan = {
        "sessions": [{"weekday": 0, "time": "18:00", "duration_minutes": 60, "title": "Pecho"}],
        "weeks": 4,
        "valid_from": "2026-11-16",
    }
    mgr.save_plan(123, plan)
    loaded = mgr.get_plan(123)
    assert loaded["sessions"][0]["title"] == "Pecho"
    assert loaded["weeks"] == 4
