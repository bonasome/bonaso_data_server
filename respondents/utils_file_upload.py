import string
from itertools import product
import re
from dateutil.parser import parse as parse_date
from datetime import date, timedelta, datetime
from openpyxl.utils.datetime import from_excel

def excel_columns():
        '''
        Helper the manage values in excel columns.
        '''
        for size in range(1, 3):  # A to ZZ
            for letters in product(string.ascii_uppercase, repeat=size):
                yield ''.join(letters)

def valid_excel_date(value):
    '''
    Helper to validate the myriad of dates from excel.
    - date (string/date): object to check is a date
    '''
    if value is None:
        return None
    # Already a Python date or datetime
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        if value > date.today():
            return None
        return value
    # Try ISO string
    try:
        parsed = date.fromisoformat(value)
        if parsed > date.today():
            return None
        return parsed
    except (ValueError, TypeError):
        pass
    # Try Excel serial number (e.g., 45000 or '45000')
    try:
        numeric_value = float(value)
        converted = from_excel(numeric_value)
        if isinstance(converted, datetime):
            converted = converted.date()
        if converted > date.today():
            return None
        return converted
    except (ValueError, TypeError):
        pass
    try:
        parsed = parse_date(value, dayfirst=True).date()
        if parsed > date.today():
            return None
        return parsed
    except (ValueError, TypeError):
        pass
    try:
        parsed = parse_date(value, dayfirst=False).date()
        if parsed > date.today():
            return None
        return parsed
    except (ValueError, TypeError):
        pass
    return None

'''
Few helpers the verify data types
'''
def is_email(value):
    #checks email
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return bool(re.match(pattern, value))

def is_phone_number(value):
    #checks phone number
    pattern = r'^\+?[\d\s\-\(\)]{7,20}$'
    return bool(re.fullmatch(pattern, value))

def is_truthy(value):
    # checks boolean
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    if isinstance(value, str):
        return value.strip().lower() in ['true', 'yes', '1']
    return False