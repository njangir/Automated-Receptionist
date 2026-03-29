"""Service for retrieving user portfolio details."""
import logging
from typing import List
from playwright.async_api import Page

logger = logging.getLogger(__name__)

class PortfolioService:
    """Service for retrieving user portfolio details."""

    def __init__(self, page: Page):
        """
        Initialize portfolio service.

        Args:
            page: Playwright page object
        """
        self.page = page

    @staticmethod
    def _extract_table_rows_js():
        """Return JavaScript code for extracting table rows."""
        return """() => {
            const rows = [];
            const tableRows = document.querySelectorAll('tr');

            for (const row of tableRows) {
                const cells = [];
                const rowCells = row.querySelectorAll('td, th');

                for (const cell of rowCells) {
                    const text = (cell.textContent || '').trim();
                    cells.push(text);
                }

                if (cells.length > 0) {
                    rows.push(cells);
                }
            }

            return rows;
        }"""

    def _rows_to_markdown(self, rows: List[List[str]]) -> str:
        """
        Convert table rows to markdown format.

        Args:
            rows: List of rows, each row is a list of cell texts

        Returns:
            Markdown table string
        """
        if not rows:
            return "Portfolio is empty or no data available."

        markdown_lines = []

        for i, row in enumerate(rows):
            if i == 0:

                markdown_lines.append("| " + " | ".join(row) + " |")

                markdown_lines.append("|" + "|".join(["---"] * len(row)) + "|")
            else:

                markdown_lines.append("| " + " | ".join(row) + " |")

        return "\n".join(markdown_lines)

    async def get_user_portfolio(self, client_code: str) -> str:
        """
        Get user portfolio details from the backoffice system.

        Args:
            client_code: Client code to look up

        Returns:
            Portfolio details as markdown table
        """
        try:
            if not client_code:
                return "Error: CLIENT_CODE environment variable is not set!"

            logger.info(f"Retrieving portfolio for client code: {client_code}")

            await self.page.get_by_role("link", name="Reports ", exact=True).click()
            await self.page.get_by_role("link", name="PortFolio").click()

            await self.page.wait_for_load_state("networkidle")

            await self.page.locator("#ctl00_ContentPlaceHolder1_txtClientCode").fill(client_code)

            await self.page.get_by_role("button", name="Go").click()

            await self.page.locator("#ctl00_ContentPlaceHolder1_gvGrid").wait_for(
                state="visible", timeout=10000
            )
            await self.page.locator("#ctl00_ContentPlaceHolder1_Table2").wait_for(
                state="visible", timeout=10000
            )

            header_table_locator = self.page.locator("#ctl00_ContentPlaceHolder1_Table2")
            data_table_locator = self.page.locator("#ctl00_ContentPlaceHolder1_gvGrid")

            extract_js = self._extract_table_rows_js()

            header_table_element = await header_table_locator.first.element_handle()
            data_table_element = await data_table_locator.first.element_handle()

            header_rows = await header_table_element.evaluate(extract_js)
            data_rows = await data_table_element.evaluate(extract_js)

            merged_rows = header_rows + data_rows

            markdown_table = self._rows_to_markdown(merged_rows)

            logger.info("Successfully retrieved portfolio")
            return markdown_table

        except Exception as e:
            error_msg = f"Error: Failed to retrieve portfolio: {str(e)}"
            logger.error(error_msg)
            return error_msg
