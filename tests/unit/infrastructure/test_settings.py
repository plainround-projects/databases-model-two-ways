import pytest

from rental_shop.infrastructure.settings import ConfigurationError, Settings

MINIMAL = {"POSTGRES_PASSWORD": "s3cret-value"}


def test_defaults_describe_the_local_compose_setup():
    settings = Settings.from_env(MINIMAL)
    postgres = settings.postgres
    assert (postgres.host, postgres.port, postgres.database, postgres.user) == ("localhost", 5441, "rentals", "shop")
    assert (postgres.schema, postgres.connect_timeout_seconds, postgres.statement_timeout_ms) == ("public", 5, 30_000)
    assert settings.log_level == "INFO"


def test_the_database_password_has_no_default():
    with pytest.raises(ConfigurationError, match="POSTGRES_PASSWORD"):
        Settings.from_env({})


def test_the_password_never_appears_in_a_printed_settings_object():
    assert "s3cret-value" not in repr(Settings.from_env(MINIMAL))


def test_every_variable_can_be_overridden():
    settings = Settings.from_env(
        {
            **MINIMAL,
            "POSTGRES_HOST": "db",
            "POSTGRES_PORT": "6543",
            "POSTGRES_DB": "x",
            "POSTGRES_USER": "u",
            "POSTGRES_SCHEMA": "lab_one",
            "POSTGRES_CONNECT_TIMEOUT_SECONDS": "2",
            "POSTGRES_STATEMENT_TIMEOUT_MS": "500",
            "LOG_LEVEL": "debug",
        }
    )
    postgres = settings.postgres
    assert (postgres.host, postgres.port, postgres.database, postgres.user) == ("db", 6543, "x", "u")
    assert (postgres.schema, postgres.connect_timeout_seconds, postgres.statement_timeout_ms) == ("lab_one", 2, 500)
    assert (postgres.password, settings.log_level) == ("s3cret-value", "DEBUG")


@pytest.mark.parametrize(
    "extra",
    [
        {"POSTGRES_PORT": "0"},
        {"POSTGRES_PORT": "five"},
        {"POSTGRES_HOST": "  "},
        {"POSTGRES_SCHEMA": "public; DROP TABLE rentals"},
        {"POSTGRES_SCHEMA": "Upper"},
        {"POSTGRES_STATEMENT_TIMEOUT_MS": "-1"},
        {"LOG_LEVEL": "LOUD"},
    ],
)
def test_an_unusable_value_is_rejected_with_the_variable_name(extra):
    with pytest.raises(ConfigurationError, match=next(iter(extra))):
        Settings.from_env({**MINIMAL, **extra})


def test_settings_read_the_process_environment_by_default(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "from-the-process")
    assert Settings.from_env().postgres.password == "from-the-process"
