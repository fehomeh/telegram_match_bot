import logging
import gspread
from google.oauth2 import service_account
import os


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
