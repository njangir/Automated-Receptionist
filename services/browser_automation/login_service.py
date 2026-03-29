"""Service for logging into the backoffice system."""
import logging
import os
from typing import Optional
from playwright.async_api import Page

logger = logging.getLogger(__name__)

class LoginService:
    """Service for handling login to backoffice system."""

    def __init__(self, page: Page):
        """
        Initialize login service.

        Args:
            page: Playwright page object
        """
        self.page = page

    async def login(
        self,
        login_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        login_type: Optional[str] = None
    ) -> bool:
        """
        Login to the backoffice system.

        Args:
            login_url: URL of the login page
            username: Username for login
            password: Password for login
            login_type: Login type option value

        Returns:
            True if login successful, False otherwise
        """
        try:

            login_url = login_url or os.getenv("LOGIN_URL")
            username = username or os.getenv("LOGIN_USERNAME", "")
            password = password or os.getenv("LOGIN_PASSWORD", "")
            login_type = login_type or os.getenv("LOGIN_TYPE", "15")

            if not username or not password:
                logger.error("Username or password not provided")
                return False

            logger.info(f"Navigating to login page: {login_url}")
            await self.page.goto(login_url)

            await self.page.wait_for_load_state("networkidle")

            logger.info("Filling login form")
            await self.page.get_by_role("textbox", name="Username").click()
            await self.page.get_by_role("textbox", name="Username").fill(username)

            await self.page.get_by_role("textbox", name="Password").click()
            await self.page.get_by_role("textbox", name="Password").fill(password)

            await self.page.locator("#DdlLoginType").select_option(login_type)

            logger.info("Login form filled, ready for submission")
            return True

        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False