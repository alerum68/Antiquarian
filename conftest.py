"""
Root conftest.py for pytest configuration.
Ignores local development and scratch directories during test collection.
"""

collect_ignore_glob = ["Working/*", "DEV/*"]
