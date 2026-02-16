from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from flask import current_app
# Убираем импорт из app - будем импортировать локально

def calculate_funds_growth():
    # Импортируем db и модели внутри функции
    from app import db
    from db.models import fund_values, funds
    
    today = datetime.now().date()
    max_days_ago = (today - relativedelta(years=5)).toordinal()

    # Получаем все активные фонды
    active_funds = funds.query.filter_by(is_archived=False).all()
    fund_ids = [fund.id for fund in active_funds]

    if not fund_ids:
        return {}

    # Получаем данные для всех активных фондов
    all_funds_data = db.session.query(
        fund_values.fund_id,
        fund_values.date,
        fund_values.share_price
    ).filter(
        fund_values.fund_id.in_(fund_ids),
        fund_values.date >= date.fromordinal(max_days_ago)
    ).order_by(fund_values.fund_id, fund_values.date).all()

    # Создаем словари для быстрого поиска цен по датам для каждого фонда
    funds_price_data = {fund_id: {} for fund_id in fund_ids}

    for item in all_funds_data:
        funds_price_data[item.fund_id][item.date] = item.share_price

    def get_last_working_day_price(target_date, fund_id):
        price_data = funds_price_data.get(fund_id, {})
        
        if not price_data:
            return None, None
            
        current_date = target_date
        max_iterations = 365 * 5
        iterations = 0
        
        while iterations < max_iterations:
            if current_date in price_data:
                return price_data[current_date], current_date
            current_date -= timedelta(days=1)
            iterations += 1
        return None, None

    def calculate_growth(end_price, start_price):
        if start_price and end_price and start_price != 0:
            return ((end_price / start_price) - 1) * 100
        return None

    periods = {
        "1m": relativedelta(months=1),
        "3m": relativedelta(months=3),
        "6m": relativedelta(months=6),
        "1y": relativedelta(years=1),
        "3y": relativedelta(years=3),
        "5y": relativedelta(years=5),
    }

    growth_data = {}

    for fund in active_funds:
        fund_growth = {}
        end_date = today.replace(day=1) - timedelta(days=1)
        
        for period_name, period_delta in periods.items():
            start_date = end_date - period_delta
            
            end_price, actual_end_date = get_last_working_day_price(end_date, fund.id)
            start_price, actual_start_date = get_last_working_day_price(start_date, fund.id)
            
            growth = calculate_growth(end_price, start_price)
            fund_growth[period_name] = {
                'value': growth,
                'start_date': actual_start_date,
                'end_date': actual_end_date
            }

        growth_data[fund.id] = {
            'growth': fund_growth,
            'description': fund.footer_description or '',
            'short_name': fund.short_name
        }

    return growth_data

def get_period_name(period_code):
    names = {
        '1m': '1 месяц',
        '3m': '3 месяца',
        '6m': '6 месяцев',
        '1y': '1 год',
        '3y': '3 года',
        '5y': '5 лет'
    }
    return names.get(period_code, period_code)