"""
Run locally with: uvicorn app:app --reload
"""

import asyncio
import sys

if sys.platform == "win32" and hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from src.app.main import app

