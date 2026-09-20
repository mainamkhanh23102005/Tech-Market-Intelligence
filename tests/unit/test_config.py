import pytest
from pydantic import ValidationError
from tech_market_api.config import Settings


def test_settings_use_explicit_safe_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.APP_ENV == "local"
    assert settings.LOG_LEVEL == "INFO"
    assert settings.PROVIDER_API_KEY is None


def test_invalid_environment_fails_without_exposing_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "must-not-appear"
    monkeypatch.setenv("APP_ENV", "invalid")
    monkeypatch.setenv("PROVIDER_API_KEY", secret)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    assert secret not in str(error.value)


def test_secret_is_redacted_in_settings_representation() -> None:
    secret = "must-not-appear"

    settings = Settings(_env_file=None, PROVIDER_API_KEY=secret)

    assert secret not in repr(settings)
    assert settings.PROVIDER_API_KEY is not None
    assert settings.PROVIDER_API_KEY.get_secret_value() == secret
