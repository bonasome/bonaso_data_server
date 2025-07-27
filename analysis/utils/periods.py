from datetime import date, datetime
from dateutil.relativedelta import relativedelta

def get_month_string(date):
    return date.strftime('%b %Y') 

def get_quarter_string(date):
    return f"Q{((date.month - 1) // 3) + 1} {date.year}"

def get_month_strings_between(start_date, end_date):
    months = []
    current = start_date.replace(day=1)
    while current <= end_date:
        months.append(get_month_string(current)) 
        current += relativedelta(months=1)
    return months

def get_quarter_strings_between(start_date, end_date):
    quarters = []
    current = start_date.replace(day=1)
    while current <= end_date:
        quarters.append(get_quarter_string(current))
        current += relativedelta(months=3)
    return quarters