"""Browser service for managing browser connection via Chrome DevTools Protocol."""
import logging
import os
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from services.browser_automation.chrome_launcher import ChromeLauncher

logger = logging.getLogger(__name__)

class BrowserService:
    """Service for managing browser connection via Chrome DevTools Protocol."""

    def __init__(
        self,
        chrome_debug_port: int = 9222,
        auto_start_chrome: bool = True,
        chrome_user_data_dir: Optional[str] = None,
        chrome_executable_path: Optional[str] = None
    ):
        """
        Initialize browser service.

        Args:
            chrome_debug_port: Port where Chrome is running with remote debugging
            auto_start_chrome: Automatically start Chrome if not running
            chrome_user_data_dir: Chrome user data directory
            chrome_executable_path: Optional path to Chrome executable
        """
        self.chrome_debug_port = chrome_debug_port
        self.chrome_debug_url = f"http://localhost:{chrome_debug_port}"
        self.auto_start_chrome = auto_start_chrome
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        self.chrome_launcher = ChromeLauncher(
            chrome_debug_port=chrome_debug_port,
            user_data_dir=chrome_user_data_dir,
            chrome_executable_path=chrome_executable_path
        )

    def ensure_chrome_running(self) -> bool:
        """
        Ensure Chrome is running with remote debugging.

        Returns:
            True if Chrome is running, False otherwise
        """
        return self.chrome_launcher.ensure_chrome_running(
            port=self.chrome_debug_port,
            auto_start=self.auto_start_chrome
        )

    async def connect(self) -> Page:
        """
        Connect to existing Chrome instance via CDP.

        Returns:
            Page object for interacting with the browser
        """
        if self.page is not None:
            return self.page

        if not self.ensure_chrome_running():
            raise RuntimeError(
                f"Chrome is not running on port {self.chrome_debug_port}. "
                "Please start Chrome with remote debugging enabled."
            )

        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.connect_over_cdp(self.chrome_debug_url)

            contexts = self.browser.contexts
            if contexts:
                self.context = contexts[0]
                pages = self.context.pages
                if pages:
                    self.page = pages[0]
                else:
                    self.page = await self.context.new_page()
            else:
                self.context = await self.browser.new_context()
                self.page = await self.context.new_page()

            logger.info(f"Connected to Chrome via CDP at {self.chrome_debug_url}")
            return self.page

        except Exception as e:
            logger.error(f"Failed to connect to Chrome: {e}")
            raise

    async def ensure_connected(self) -> Page:
        """Ensure browser is connected, connect if not."""
        if self.page is None:
            await self.connect()
        return self.page

    async def close(self, stop_chrome: bool = False):
        """
        Close browser connection.

        Args:
            stop_chrome: If True, also stop the Chrome process
        """
        try:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            self.browser = None
            self.context = None
            self.page = None
            logger.info("Browser connection closed")

            if stop_chrome:
                self.chrome_launcher.stop_chrome()
        except Exception as e:
            logger.warning(f"Error closing browser: {e}")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
