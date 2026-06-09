# tests/test_main.py
"""`python -m fine_tuning_os` entry point wiring."""

import fine_tuning_os.__main__ as entry
from fine_tuning_os.server import main as server_main


def test_main_module_reexports_server_main():
    assert entry.main is server_main
