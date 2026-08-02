import sys
import pathlib
import pytest

# この tests/ があるディレクトリ (nf_loto_webui/) を PYTHONPATH に追加して、
# `import src` が通るようにする
_THIS_DIR = pathlib.Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


class DummyCursor:
    def __init__(self):
        self.executed = []
        self._fetchone_result = [123]

    def execute(self, sql, params=None):
        # 簡易的に実行履歴を残すだけ
        self.executed.append((sql, params))

    def fetchone(self):
        return self._fetchone_result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DummyConnection:
    def __init__(self):
        self.cursor_obj = DummyCursor()
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def dummy_db():
    """db_logger 用のダミー接続。"""
    return DummyConnection()
