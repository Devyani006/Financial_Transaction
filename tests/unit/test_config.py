import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestDatabaseConfig:

    def test_valid_config_loads(self, mock_env):
        from importlib import reload
        import app.config as cfg_module
        reload(cfg_module)

        config = cfg_module.DatabaseConfig()
        assert config.host == "127.0.0.1"
        assert config.port == 3306
        assert config.name == "financial_transaction_test"
        assert config.user == "test_user"

    def test_connection_url_format(self, mock_env):
        from importlib import reload
        import app.config as cfg_module
        reload(cfg_module)

        config = cfg_module.DatabaseConfig()
        url = config.url
        assert "mysql+pymysql://" in url
        assert "test_user" in url
        assert "127.0.0.1" in url
        assert "3306" in url
        assert "charset=utf8mb4" in url

    def test_missing_required_variable_raises(self, incomplete_env):
        from importlib import reload
        import app.config as cfg_module
        reload(cfg_module)

        with pytest.raises(cfg_module.ConfigError) as exc_info:
            cfg_module.DatabaseConfig()
        assert "DB_USER" in str(exc_info.value) or "DB_PASSWORD" in str(exc_info.value)

    def test_error_message_is_helpful(self, incomplete_env):
        from importlib import reload
        import app.config as cfg_module
        reload(cfg_module)

        try:
            cfg_module.DatabaseConfig()
        except cfg_module.ConfigError as e:
            assert ".env" in str(e).lower() or "environment" in str(e).lower()

    def test_password_not_in_repr(self, mock_env):
        from importlib import reload
        import app.config as cfg_module
        reload(cfg_module)

        config = cfg_module.DatabaseConfig()
        assert "test_password" not in repr(config)

    def test_default_port_is_3306(self):
        env = {
            "DB_HOST": "127.0.0.1",
            "DB_NAME": "mydb",
            "DB_USER": "user",
            "DB_PASSWORD": "pass",
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("DB_PORT", None)
            from importlib import reload
            import app.config as cfg_module
            reload(cfg_module)
            config = cfg_module.DatabaseConfig()
            assert config.port == 3306


class TestAppConfig:

    def test_debug_defaults_to_false(self, mock_env):
        with patch.dict(os.environ, mock_env, clear=False):
            os.environ.pop("DEBUG", None)
            from importlib import reload
            import app.config as cfg_module
            reload(cfg_module)
            config = cfg_module.AppConfig()
            assert config.debug is False

    def test_anomaly_contamination_defaults(self, mock_env):
        from importlib import reload
        import app.config as cfg_module
        reload(cfg_module)
        config = cfg_module.AppConfig()
        assert abs(config.anomaly_contamination - 0.02) < 1e-9

    def test_anomaly_seed_defaults_to_42(self, mock_env):
        from importlib import reload
        import app.config as cfg_module
        reload(cfg_module)
        config = cfg_module.AppConfig()
        assert config.anomaly_random_seed == 42
