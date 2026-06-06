from __future__ import annotations

import os


if os.environ.get("APP_TEST_REAL_PROVIDERS") != "1":
    os.environ["APP_AUTO_LOAD_DOTENV"] = "0"
    os.environ["LLM_PROVIDER"] = "fake"
    os.environ["PRON_PROVIDER"] = "mock"
    os.environ["ASR_PROVIDER"] = "fake"
    os.environ["TTS_PROVIDER"] = "browser"
    os.environ.setdefault("APP_DB_PATH", ".local/test/speaking_coach.sqlite")
    os.environ.setdefault("APP_AUDIO_DIR", ".local/test/audio")
