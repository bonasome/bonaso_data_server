from datetime import date, datetime
from dateutil.relativedelta import relativedelta

'''
Functions that help manage dates when collecting aggregate data.
'''
def get_month_string(date):
    #returns the month as a string from a date object
    return date.strftime('%b %Y') 

def get_quarter_string(date):
    #returns the quarter as a string from a date object
    return f"Q{((date.month - 1) // 3) + 1} {date.year}"

def get_month_strings_between(start_date, end_date):
    #get list of month strings between two dates
    months = []
    current = start_date.replace(day=1)
    while current <= end_date:
        months.append(get_month_string(current)) 
        current += relativedelta(months=1)
    return months

def get_quarter_strings_between(start_date, end_date):
    #get list of quarter strings between two dates
    quarters = []
    current = start_date.replace(day=1)
    while current <= end_date:
        quarters.append(get_quarter_string(current))
        current += relativedelta(months=3)
    return quarters