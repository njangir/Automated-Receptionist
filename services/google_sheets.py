"""Google Sheets service for contact lookup."""
import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

root_dir = Path(__file__).parent.parent
from services.config_loader import load_config
load_config(root_dir)

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "0")
GOOGLE_SERVICE_ACCOUNT_PATH = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH", "")

GOOGLE_SHEET_PHONE_COLUMN = os.getenv("GOOGLE_SHEET_PHONE_COLUMN", "phone")
GOOGLE_SHEET_ACCOUNT_CODE_COLUMN = os.getenv("GOOGLE_SHEET_ACCOUNT_CODE_COLUMN", "Account Code")
GOOGLE_SHEET_ACCOUNT_NAME_COLUMN = os.getenv("GOOGLE_SHEET_ACCOUNT_NAME_COLUMN", "Account Name")

_sheets_service = None

def get_sheets_service():
    """Get or create Google Sheets service instance."""
    global _sheets_service
    if _sheets_service is None:
        try:
            creds = service_account.Credentials.from_service_account_file(
                GOOGLE_SERVICE_ACCOUNT_PATH,
                scopes=SCOPES
            )
            service = build('sheets', 'v4', credentials=creds)
            _sheets_service = service.spreadsheets()
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets service: {e}")
            raise
    return _sheets_service

async def find_contact_by_phone(phone: str) -> Optional[Dict[str, Any]]:
    """Search for a contact in Google Sheets by phone number"""
    try:
        sheet = get_sheets_service()
        result = sheet.values().get(
            spreadsheetId=SHEET_ID,
            range=SHEET_NAME
        ).execute()

        values = result.get('values', [])
        if not values:
            return None

        headers = values[0]
        for row in values[1:]:
            if row and len(row) > 0:
                try:
                    phone_index = headers.index(GOOGLE_SHEET_PHONE_COLUMN)
                    if phone_index < len(row) and row[phone_index] == phone:
                        return dict(zip(headers, row))
                except ValueError:

                    logger.warning(f"'{GOOGLE_SHEET_PHONE_COLUMN}' column not found in Google Sheets headers")
                    return None
        return None
    except Exception as e:
        logger.error(f"Error accessing Google Sheets: {e}")
        return None
