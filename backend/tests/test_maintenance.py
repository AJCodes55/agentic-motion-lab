"""Maintenance must exclude the serving app before reading or changing evidence."""
import pytest
from fastapi.testclient import TestClient

from mobility.config import Settings
from mobility.maintenance import application_lock, maintenance_lock


def test_serving_app_blocks_maintenance_and_releases_on_shutdown(tmp_path):
    from mobility.app import create_app
    with TestClient(create_app(Settings(data_root=tmp_path))):
        with pytest.raises(RuntimeError, match='in use'):
            with maintenance_lock(tmp_path):
                pass
    with maintenance_lock(tmp_path):
        pass


def test_maintenance_blocks_app_startup(tmp_path):
    from mobility.app import create_app
    with maintenance_lock(tmp_path):
        with pytest.raises(RuntimeError, match='in use'):
            with TestClient(create_app(Settings(data_root=tmp_path))):
                pass


def test_interrupted_cleanup_prevents_serving(tmp_path):
    (tmp_path / '.cleanup-journal.json').write_text('{}')
    with pytest.raises(RuntimeError, match='cleanup'):
        with application_lock(tmp_path):
            pass


def test_shared_readers_and_missing_root(tmp_path):
    with application_lock(tmp_path), application_lock(tmp_path):
        pass
    with pytest.raises(ValueError, match='existing'):
        with maintenance_lock(tmp_path / 'missing'):
            pass


def test_lock_symlink_rejected(tmp_path):
    target = tmp_path / 'external'
    target.write_text('unchanged')
    (tmp_path / 'maintenance.lock').symlink_to(target)
    with pytest.raises(ValueError, match='lock'):
        with maintenance_lock(tmp_path):
            pass
    assert target.read_text() == 'unchanged'
