import random
import threading
import logging
from typing import Dict, Optional
from curl_cffi import requests

logger = logging.getLogger("stealth_client")

TLS_PROFILES = [
    "safari17_0",
    "chrome124",
    "chrome120",
    "chrome119"
]

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
]

PREWARM_URLS = [
    "https://www.ajio.com/c/830216",
    "https://www.ajio.com/c/830316",
    "https://www.ajio.com/c/830101",
    "https://www.ajio.com/c/830501"
]

class StealthSessionManager:
    """
    Thread-safe session pool manager. Pre-warms session cookie jars with real Akamai
    visitor tokens (_abck, bm_sz) and manages randomized browser TLS fingerprints.
    """
    def __init__(self):
        self._thread_local = threading.local()
        self._lock = threading.Lock()

    def get_session(self) -> requests.Session:
        if not hasattr(self._thread_local, "session") or self._thread_local.session is None:
            profile = random.choice(TLS_PROFILES)
            ua = random.choice(USER_AGENTS)
            s = requests.Session(impersonate=profile)
            headers = {
                "User-Agent": ua,
                "Referer": "https://www.ajio.com/",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "navigate"
            }
            # Pre-warm session to obtain valid Akamai sensor tokens
            try:
                prewarm_target = random.choice(PREWARM_URLS)
                s.get(prewarm_target, headers=headers, timeout=10)
            except Exception as e:
                logger.warning(f"Session pre-warm initial probe: {e}")

            self._thread_local.session = s
            self._thread_local.request_count = 0
            self._thread_local.headers = headers

        # Periodic soft re-warm every 100 requests
        self._thread_local.request_count += 1
        if self._thread_local.request_count > 100:
            try:
                self._thread_local.session.get("https://www.ajio.com/c/830216", headers=self._thread_local.headers, timeout=8)
            except Exception:
                pass
            self._thread_local.request_count = 0

        return self._thread_local.session

    def get_headers(self) -> Dict[str, str]:
        if hasattr(self._thread_local, "headers") and self._thread_local.headers:
            return self._thread_local.headers
        return {
            "User-Agent": USER_AGENTS[0],
            "Referer": "https://www.ajio.com/"
        }

stealth_manager = StealthSessionManager()
