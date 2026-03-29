"""Service for retrieving user profile/bank details."""
import logging
from typing import Optional
from playwright.async_api import Page

logger = logging.getLogger(__name__)

class ProfileService:
    """Service for retrieving user profile and bank details."""

    def __init__(self, page: Page):
        """
        Initialize profile service.

        Args:
            page: Playwright page object
        """
        self.page = page

    async def get_user_bank_details(self, client_code: str) -> str:
        """
        Get user bank details from the backoffice system.

        Args:
            client_code: Client code to look up

        Returns:
            Bank details as string
        """
        try:
            if not client_code:
                return "Error: Client code is not available. Please provide your client code first."

            logger.info(f"Retrieving bank details for client code: {client_code}")

            await self.page.get_by_role("listitem").filter(has_text="ClientProfile").click()
            await self.page.get_by_role("link", name="Client Detail").click()

            await self.page.wait_for_load_state("networkidle")

            await self.page.locator("#ctl00_ContentPlaceHolder1_txt_clientcode").fill(client_code)

            await self.page.get_by_role("button", name="Go").click()

            await self.page.wait_for_load_state("networkidle")

            bank_details_locator = self.page.locator("tr:nth-child(4) > td:nth-child(2)")
            await bank_details_locator.wait_for(state="visible", timeout=10000)

            bank_details = await bank_details_locator.inner_text()

            result = f"Bank Name followed by Account Number: {bank_details}"
            logger.info(f"Successfully retrieved bank details: {result}")

            return result

        except Exception as e:
            error_msg = f"Error: Failed to retrieve bank details: {str(e)}"
            logger.error(error_msg)
            return error_msg
