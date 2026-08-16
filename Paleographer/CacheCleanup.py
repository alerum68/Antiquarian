"""
AI Assistant API Cache Cleanup Utility.

Deletes all active context caches under the configured API key, so they
don't sit around racking up storage costs.

Environment variables:
    AI_API_KEY: set in the environment or a .env file.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
# noinspection PyUnresolvedReferences
from google import genai

# ==========================================
# CONFIGURATION
# ==========================================
# Global settings come from the project root's .env; this tool's own settings come from
# its own subfolder's .env, so Paleographer stays runnable standalone.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)
client = genai.Client(api_key=os.getenv("AI_API_KEY"))


# ==========================================
# MAIN EXECUTION
# ==========================================
def cleanup_all_caches() -> None:
    """Fetch every active cache and delete it, one at a time."""
    print("Fetching active caches...")
    try:
        caches = client.caches.list()
        deleted_count = 0

        for cache in caches:
            print(
                f"Deleting cache: {cache.name} "
                f"(Created: {cache.create_time})"
            )
            try:
                client.caches.delete(name=cache.name)
                deleted_count += 1
            except Exception as delete_error:
                print(f"  [!] Failed to delete {cache.name}: {delete_error}")

        if deleted_count == 0:
            print("No active caches found. You're all clear!")
        else:
            print(f"\nSuccessfully deleted {deleted_count} orphaned caches.")

    except Exception as fetch_error:
        print(f"Error fetching caches: {fetch_error}")


if __name__ == "__main__":
    cleanup_all_caches()
