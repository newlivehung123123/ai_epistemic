"""Run the tests with python3 -I -m pytest tests (from the project folder). -I drops the current folder from
sys.path, so the project folder is added here."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
