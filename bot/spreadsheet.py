import logging
from typing import Union, List, Any

import gspread
from google.oauth2 import service_account
import os

from gspread import WorksheetNotFound, ValueRange


def is_spreadsheet_writable(spreadsheet_url: str) -> bool:
    try:
        client = get_spreadsheet_client()
        spreadsheet = client.open_by_url(spreadsheet_url)
        spreadsheet.get_worksheet(0)
        worksheet = spreadsheet.add_worksheet('Temp Test worksheet', 2, 2)
        spreadsheet.del_worksheet(worksheet)
    except Exception as ex:
        logging.exception("Exception: %s", ex)
        return False
    return True


def get_spreadsheet_client() -> gspread.Client:
    credentials = service_account.Credentials.from_service_account_file(os.path.dirname(__file__) + "/../credentials.json")
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_with_scope = credentials.with_scopes(scope)
    return gspread.authorize(creds_with_scope)


def create_worksheet(spreadsheet_url: str, name: str, rows: int, cols: int) -> gspread.worksheet:
    client = get_spreadsheet_client()
    spreadsheet = client.open_by_url(spreadsheet_url)
    return spreadsheet.add_worksheet(name, rows, cols)


def has_worksheet_with_name(spreadsheet_url: str, worksheet_name: str) -> bool:
    client = get_spreadsheet_client()
    spreadsheet = client.open_by_url(spreadsheet_url)
    try:
        spreadsheet.worksheet(worksheet_name)
        return True
    except WorksheetNotFound:
        return False


def update_group_worksheet(spreadsheet_url: str, worksheet_name: str, updated_data: list):
    """Writes entire worksheet data in a single batch update to Google Sheets.

    Args:
        spreadsheet_url (str): Spreadsheet link.
        worksheet_name (str): The target worksheet to update.
        updated_data (list): The full worksheet structure with updated values.
    """
    client = get_spreadsheet_client()
    spreadsheet = client.open_by_url(spreadsheet_url)

    worksheet = spreadsheet.worksheet(worksheet_name)

    update_range = f"A1:{chr(64 + len(updated_data[0]))}{len(updated_data)}"  # E.g., "A1:G20"
    worksheet.update(update_range, updated_data)


def fetch_all_data_from_worksheet(spreadsheet_url: str, worksheet_name: str) -> Union[ValueRange, List[List[Any]]]:
    client = get_spreadsheet_client()
    spreadsheet = client.open_by_url(spreadsheet_url)
    worksheet = spreadsheet.worksheet(worksheet_name)

    return worksheet.get_all_values()
