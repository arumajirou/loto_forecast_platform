"""pytest configuration file."""

import sys
from pathlib import Path

# プロジェクトルートへパスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
