"""Pytest bootstrap: put the backend dir on sys.path so tests can use the
project's absolute imports (e.g. `from config import config`)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
