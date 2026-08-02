"""Test config caching mechanism."""

import os
import tempfile

import yaml

from loto_ops.config import load_settings


def test_config_cache_returns_same_object():
    """Test that multiple calls to load_settings with same file return cached object."""
    # Create a temporary config file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(
            {
                "paths": {
                    "ops_project": "/tmp/test",
                    "loto_life_project": "/tmp/test_life",
                    "loto_forecast_project": "/tmp/test_forecast",
                    "zip_output_dir": "/tmp/test_zip",
                },
                "db": {
                    "host": "127.0.0.1",
                    "port": 5432,
                    "user": "test",
                    "password": "test_pass",
                    "database": "test_db",
                    "maintenance_database": "postgres",
                },
                "pipeline": {"default_games": "all"},
                "scheduler": {"time": "06:30"},
            },
            f,
        )
        config_path = f.name

    try:
        # First call should load from file
        settings1 = load_settings(config_path)

        # Second call with same file should return cached object
        settings2 = load_settings(config_path)

        # Both should be the same object (cached)
        assert settings1 is settings2, "Cached settings should be the same object"

        # Clean up
        os.unlink(config_path)
    except Exception as e:
        # Clean up temp file if it exists
        if os.path.exists(config_path):
            os.unlink(config_path)
        raise e


def test_config_cache_different_files():
    """Test that different config files result in different cached objects."""
    # Create two temporary config files
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f1:
        yaml.dump(
            {
                "paths": {"ops_project": "/tmp/test1"},
                "db": {
                    "host": "127.0.0.1",
                    "port": 5432,
                    "user": "test1",
                    "password": "pass1",
                    "database": "db1",
                    "maintenance_database": "postgres",
                },
                "pipeline": {"default_games": "all"},
                "scheduler": {"time": "06:30"},
            },
            f1,
        )
        config_path1 = f1.name

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f2:
        yaml.dump(
            {
                "paths": {"ops_project": "/tmp/test2"},
                "db": {
                    "host": "127.0.0.2",
                    "port": 5433,
                    "user": "test2",
                    "password": "pass2",
                    "database": "db2",
                    "maintenance_database": "postgres",
                },
                "pipeline": {"default_games": "all"},
                "scheduler": {"time": "07:00"},
            },
            f2,
        )
        config_path2 = f2.name

    try:
        # Load settings from first file
        settings1 = load_settings(config_path1)

        # Load settings from second file
        settings2 = load_settings(config_path2)

        # Different files should result in different cached objects
        assert settings1 is not settings2, (
            "Different config files should result in different cached objects"
        )

        # Clean up
        os.unlink(config_path1)
        os.unlink(config_path2)
    except Exception as e:
        # Clean up temp files if they exist
        if os.path.exists(config_path1):
            os.unlink(config_path1)
        if os.path.exists(config_path2):
            os.unlink(config_path2)
        raise e
