from flask import Flask, render_template, request, redirect, url_for, session, current_app, send_from_directory
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
import os
from flask_sqlalchemy import SQLAlchemy
from db import db
from db.models import funds, fund_values, fund_composition, fund_document, report_document, regulations_document, inform_message, news, news_block, analytics, analytics_block
from flask_login import login_user, login_required, current_user, logout_user
import json
from datetime import timezone
import pandas as pd
import re
import pytz
import base64
from utils.growth_calculator import calculate_funds_growth, get_period_name

from admin import admin, init_admin_auth

app = Flask(__name__)

# Инициализация аутентификации
init_admin_auth(app)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'secret secret key')

# УНИВЕРСАЛЬНАЯ КОНФИГУРАЦИЯ БАЗ ДАННЫХ
# По умолчанию используем MySQL, можно переключить на PostgreSQL
app.config['DB_TYPE'] = os.getenv('DB_TYPE', 'mysql')  # mysql или postgres
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

if app.config['DB_TYPE'] == 'mysql':
    # Конфигурация MySQL
    db_name = os.getenv('MYSQL_DATABASE', 'recordcapital')
    db_user = os.getenv('MYSQL_USER', 'recordcapital')
    db_password = os.getenv('MYSQL_PASSWORD', '715302')
    host_ip = os.getenv('MYSQL_HOST', '127.0.0.1')
    host_port = os.getenv('MYSQL_PORT', '3306')
    
    app.config['SQLALCHEMY_DATABASE_URI'] = \
        f'mysql+pymysql://{db_user}:{db_password}@{host_ip}:{host_port}/{db_name}'
    
    # Дополнительные настройки для MySQL
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_recycle': 280,
        'pool_pre_ping': True,
    }
    
    print(f"📊 Используется MySQL база: {db_name}")
    print(f"   Хост: {host_ip}:{host_port}")
    print(f"   Пользователь: {db_user}")

elif app.config['DB_TYPE'] == 'postgres':
    # Конфигурация PostgreSQL
    db_name = os.getenv('POSTGRES_DB', 'recordcap')
    db_user = os.getenv('POSTGRES_USER', 'recordcap')
    db_password = os.getenv('POSTGRES_PASSWORD', '715302')
    host_ip = os.getenv('POSTGRES_HOST', '127.0.0.1')
    host_port = os.getenv('POSTGRES_PORT', '5432')
    
    app.config['SQLALCHEMY_DATABASE_URI'] = \
        f'postgresql://{db_user}:{db_password}@{host_ip}:{host_port}/{db_name}'
    
    print(f"📊 Используется PostgreSQL база: {db_name}")
    print(f"   Хост: {host_ip}:{host_port}")
    print(f"   Пользователь: {db_user}")

else:
    # Если указан неверный тип базы данных
    raise ValueError(f"Неизвестный тип базы данных: {app.config['DB_TYPE']}. "
                     f"Используйте 'mysql' или 'postgres'")

# Инициализация базы данных
db.init_app(app)

# Создание таблиц при первом запуске
with app.app_context():
    try:
        db.create_all()
        print("✅ Таблицы базы данных созданы/проверены")
    except Exception as e:
        print(f"⚠️  Ошибка при создании таблиц: {e}")
        print("Возможно, нужно обновить модели для выбранной СУБД")
        
    # Проверка подключения
    try:
        from sqlalchemy import text
        result = db.session.execute(text('SELECT 1'))
        print(f"✅ Подключение к {app.config['DB_TYPE']} работает")
    except Exception as e:
        print(f"❌ Ошибка подключения к базе данных: {e}")

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16 МБ. Настройте по необходимости.

# 2. Папка для загрузки и разрешенные расширения
# app.root_path - это абсолютный путь к корневой папке вашего приложения.
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'documents/funds/')
REPORTS_UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'documents/reports')
REGULATIONS_UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'documents/regulations')
INFORM_MESSAGES_UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'documents/inform_messages')
ALLOWED_EXTENSIONS = {'pdf'} # Разрешаем только PDF

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['REPORTS_UPLOAD_FOLDER'] = REPORTS_UPLOAD_FOLDER
app.config['REGULATIONS_UPLOAD_FOLDER'] = REGULATIONS_UPLOAD_FOLDER
app.config['INFORM_MESSAGES_UPLOAD_FOLDER'] = INFORM_MESSAGES_UPLOAD_FOLDER
app.config['ALLOWED_EXTENSIONS'] = ALLOWED_EXTENSIONS

# Убедитесь, что папка для загрузки существует
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


app.register_blueprint(admin)


@app.context_processor
def inject_growth_data():
    # Можно добавить кэширование здесь
    growth_data = calculate_funds_growth()
    
    # Форматируем данные для шаблонов
    formatted_data = {}
    for fund_id, data in growth_data.items():
        fund_info = []
        last_date = None
        has_data = False
        
        for period in ['1m', '3m', '6m', '1y', '3y', '5y']:
            period_data = data['growth'].get(period, {})
            value = period_data.get('value')
            if value is not None:
                has_data = True
                sign = '+' if value >= 0 else ''
                fund_info.append(f"Доходность за {get_period_name(period)} {sign}{value:.2f}%")
                if period_data.get('end_date'):
                    last_date = period_data['end_date']
        
        formatted_data[fund_id] = {
            'description': data['description'],
            'growth_info': "; ".join(fund_info) if has_data else "",
            'last_date': last_date.strftime('%d.%m.%Y') if last_date else None,
            'short_name': data['short_name']
        }
    
    return {'growth_data': formatted_data}


from datetime import datetime

@app.route('/')
def index():
    # Получаем активные фонды для отображения карточек
    funds_list = funds.query.filter_by(is_archived=False).order_by(funds.name.desc()).all()
    
    # Получаем новости из базы данных с блоками
    news_list = news.query.options(db.joinedload(news.blocks)).order_by(news.news_date.desc()).all()
    
    # Рассчитываем данные о доходности
    growth_data_raw = calculate_funds_growth()
    
    # Форматируем для шаблона
    formatted_data = {}
    for fund_id, data in growth_data_raw.items():
        fund_info = []
        last_date = None
        has_data = False
        
        for period in ['1m', '3m', '6m', '1y', '3y', '5y']:
            period_data = data['growth'].get(period, {})
            value = period_data.get('value')
            if value is not None:
                has_data = True
                sign = '+' if value >= 0 else ''
                fund_info.append(f"Доходность за {get_period_name(period)} {sign}{value:.2f}%")
                if period_data.get('end_date'):
                    last_date = period_data['end_date']
        
        formatted_data[fund_id] = {
            'description': data['description'],
            'growth_info': "; ".join(fund_info) if has_data else "",
            'last_date': last_date.strftime('%d.%m.%Y') if last_date else None
        }

    return render_template(
        'index.html',
        funds=funds_list,
        formatted_data=formatted_data,
        news_list=news_list
    )

# Функция для получения русского названия месяца
def get_russian_month(month_num):
    months = {
        '01': 'Января', '02': 'Февраля', '03': 'Марта', '04': 'Апреля',
        '05': 'Мая', '06': 'Июня', '07': 'Июля', '08': 'Августа',
        '09': 'Сентября', '10': 'Октября', '11': 'Ноября', '12': 'Декабря'
    }
    return months.get(month_num, '')

# Функция для получения первого текстового абзаца
def get_first_paragraph(blocks):
    if not blocks:
        return "Описание отсутствует"
    
    # Ищем первый текстовый блок
    for block in blocks:
        if block.block_type == 'text' and block.content.strip():
            text = block.content.strip()
            # Берем первые 150 символов и обрезаем до последнего пробела
            if len(text) > 150:
                text = text[:150]
                last_space = text.rfind(' ')
                if last_space > 100:  # Чтобы не обрезать слишком сильно
                    text = text[:last_space]
                text += '...'
            return text
    
    return "Описание отсутствует"


@app.context_processor
def utility_processor():
    return {
        'get_russian_month': get_russian_month,
        'get_first_paragraph': get_first_paragraph
    }


@app.route('/contacts')
def contacts():
    return render_template('main/contacts.html')


@app.template_filter('b64encode')
def b64encode_filter(data):
    if data:
        return base64.b64encode(data).decode('utf-8')
    return None


@app.route('/funds')
def fund():
    funds_list = funds.query.filter_by(is_archived=False).order_by(funds.name.desc()).all()
    return render_template('main/funds.html', funds=funds_list)


@app.route('/funds/<string:fund_url>')
def fund_page(fund_url):
    # Находим фонд по URL имени
    fund = db.session.query(funds).filter_by(url_name=fund_url).first_or_404()
    
    # Получаем данные о стоимости фонда
    fund_values_data = fund.fund_values
    
    # Инициализация переменных с значениями по умолчанию
    last_date = None
    current_date_str = "нет данных"
    first_share_price = None
    first_benchmark = None
    share_chart_data = []
    benchmark_chart_data = []
    scha_chart_data = []
    share_growth_data = []
    benchmark_growth_data = []
    returns = {}
    date_options = []
    date_options_js = []
    date_display_js = []
    fund_data_json = []
    last_share_price = None
    has_enough_data = False

    # Только если есть данные в fund_values
    if fund_values_data:
        # Сортируем по дате
        fund_values_data = sorted(fund_values_data, key=lambda x: x.date)
        
        last_date = fund_values_data[-1].date
        current_date_str = last_date.strftime("%d.%m.%Y")
        first_share_price = fund_values_data[0].share_price if fund_values_data[0].share_price else None
        first_benchmark = fund_values_data[0].benchmark if fund_values_data[0].benchmark else None
        last_share_price = fund_values_data[-1].share_price if fund_values_data[-1].share_price else None
        has_enough_data = len(fund_values_data) > 1

        # Заполняем данные графиков
        for data_point in fund_values_data:
            dt = datetime.combine(data_point.date, datetime.min.time()).replace(tzinfo=timezone.utc)
            timestamp = int(dt.timestamp() * 1000)
            
            if data_point.share_price:
                share_chart_data.append([timestamp, float(data_point.share_price)])
            
            if data_point.benchmark:
                benchmark_chart_data.append([timestamp, float(data_point.benchmark)])
            
            if data_point.scha:
                scha_chart_data.append([timestamp, float(data_point.scha)])
            
            if first_share_price and data_point.share_price:
                share_growth = ((float(data_point.share_price) / float(first_share_price)) - 1) * 100
                share_growth_data.append([timestamp, share_growth])
            
            if first_benchmark and data_point.benchmark:
                benchmark_growth = ((float(data_point.benchmark) / float(first_benchmark)) - 1) * 100
                benchmark_growth_data.append([timestamp, benchmark_growth])

        # Расчет доходностей
        def calculate_return(period_days):
            try:
                end_date = fund_values_data[-1].date
                start_date = end_date - timedelta(days=period_days)

                start_price = None
                for data_point in fund_values_data:
                    if data_point.date >= start_date and data_point.share_price:
                        start_price = float(data_point.share_price)
                        break
                
                if start_price and start_price != 0:
                    end_price = float(fund_values_data[-1].share_price) if fund_values_data[-1].share_price else 0
                    return ((end_price / start_price) - 1) * 100
                return None
            except:
                return None

        returns = {
            'день': calculate_return(1),
            'неделя': calculate_return(7),
            'месяц': calculate_return(30),
            '6 месяцев': calculate_return(180),
            'год': calculate_return(365),
            '5 лет': calculate_return(1825)
        }

        # Подготовка данных для калькулятора
        date_options = [point.date for point in fund_values_data if point.share_price]
        date_options_js = [d.strftime('%Y-%m-%d') for d in date_options]
        date_display_js = [d.strftime('%d.%m.%Y') for d in date_options]
        
        fund_data_json = [{
            'date': point.date.strftime('%Y-%m-%d'),
            'share_price': float(point.share_price) if point.share_price else 0
        } for point in fund_values_data if point.share_price]

    # Получаем данные о составе фонда (последнюю дату)
    last_composition_date = db.session.query(db.func.max(fund_composition.date)).filter_by(fund_id=fund.id).scalar()
    
    # Инициализируем переменные
    issuer_data = []
    sector_data = []
    has_issuer_data = False
    has_sector_data = False
    composition_comment = ""
    composition_data = [] 

    if last_composition_date:
        composition_data = db.session.query(fund_composition).filter_by(fund_id=fund.id, date=last_composition_date).all()
        
        # Получаем комментарий управляющего
        if fund.manager and fund.manager.comment:
            composition_comment = fund.manager.comment
        
        # Временные словари для группировки
        issuer_dict = {}
        sector_dict = {}
        
        for item in composition_data:
            if item.issuer and item.share:  # Проверяем, что эмитент и доля не пустые
                issuer_dict[item.issuer] = issuer_dict.get(item.issuer, 0) + float(item.share)
                has_issuer_data = True
            if item.sector and item.share:  # Проверяем, что сектор и доля не пустые
                sector_dict[item.sector] = sector_dict.get(item.sector, 0) + float(item.share)
                has_sector_data = True
        
        # Функция подготовки данных для диаграмм
        def prepare_chart_data(data_dict):
            if not data_dict:
                return []
            sorted_items = sorted(data_dict.items(), key=lambda x: x[1], reverse=True)
            if len(sorted_items) > 9:
                main_items = sorted_items[:9]
                other_value = sum(item[1] for item in sorted_items[9:])
                return [{"name": k, "y": v} for k, v in main_items] + [{"name": "Другое", "y": other_value}]
            return [{"name": k, "y": v} for k, v in sorted_items]
        
        # Подготавливаем данные
        issuer_data = prepare_chart_data(issuer_dict) if has_issuer_data else []
        sector_data = prepare_chart_data(sector_dict) if has_sector_data else []

    # Получаем условия инвестирования
    conditions = fund.conditions if fund.conditions else []
    
    # Получаем шаги инвестирования
    steps = fund.steps if fund.steps else []
    
    # Получаем управляющего
    manager = fund.manager if fund.manager else None

    # Получаем изображения фонда
    background_image_b64 = None
    logo_b64 = None
    
    if fund.background_image:
        background_image_b64 = base64.b64encode(fund.background_image).decode('utf-8')
    
    if fund.logo:
        logo_b64 = base64.b64encode(fund.logo).decode('utf-8')

    chart_type = 'pie'  # значение по умолчанию
    if composition_data:
        chart_type = composition_data[0].chart_type if composition_data[0].chart_type else 'pie'

    return render_template(
        'main/fund_template.html',  # Это будет универсальный шаблон
        # Данные фонда
        fund=fund,
        background_image_b64=background_image_b64,
        background_mimetype=fund.background_mimetype,
        logo_b64=logo_b64,
        logo_mimetype=fund.logo_mimetype,
        
        # Условия и шаги
        conditions=conditions,
        steps=steps,
        manager=manager,
        
        # Основные данные для графиков
        share_data=json.dumps(share_chart_data),
        benchmark_data=json.dumps(benchmark_chart_data),
        scha_data=json.dumps(scha_chart_data),
        
        # Данные для роста
        share_growth_data=json.dumps(share_growth_data),
        benchmark_growth_data=json.dumps(benchmark_growth_data),
        
        # Данные о доходности
        returns=returns,
        
        # Данные о составе фонда
        issuer_data=json.dumps(issuer_data),
        sector_data=json.dumps(sector_data),
        has_issuer_data=has_issuer_data,
        has_sector_data=has_sector_data,
        composition_date=last_composition_date.strftime('%d.%m.%Y') if last_composition_date else None,
        composition_comment=composition_comment,
        
        # Данные о датах
        current_date=current_date_str,
        date_options=date_options,
        date_options_js=date_options_js,
        date_display_js=date_display_js,
        
        # Данные о фондах
        fund_data_json=fund_data_json,
        last_share_price=last_share_price,
        
        # Данные об инвестициях
        min_investment=10000,
        max_investment=10000000, 
        default_amount=500000, 

        has_enough_data=has_enough_data,

        chart_type=chart_type
    )


@app.route('/documents/uk')  
def uk_documents():
    # Получаем текущую дату и время в Московском часовом поясе
    moscow_tz = pytz.timezone('Europe/Moscow')
    now = datetime.now(moscow_tz)
    
    # Получаем все документы
    all_documents = report_document.query.order_by(report_document.upload_date.desc()).all()
    
    # Фильтруем документы: показываем те, у которых expiration_date is NULL 
    # или expiration_date >= текущей даты (включая весь день окончания)
    documents = []
    for doc in all_documents:
        if doc.upload_date:
            doc.upload_date = doc.upload_date.astimezone(moscow_tz)
        
        # Если дата окончания не установлена - показываем документ
        if doc.expiration_date is None:
            documents.append(doc)
        else:
            # Конвертируем expiration_date в Московское время для сравнения
            expiration_moscow = doc.expiration_date.astimezone(moscow_tz)
            
            # Документ виден весь день даты окончания (до 23:59:59)
            # Добавляем 1 день, чтобы документ отображался включительно до конца дня expiration_date
            expiration_with_full_day = expiration_moscow + timedelta(days=1)
            
            if expiration_with_full_day > now:
                documents.append(doc)
    
    return render_template(
        'main/uk_documents.html',
        documents=documents,
        current_date=now.date()
    )


@app.route('/documents/funds')
def funds_documents():
    fund = funds.query.order_by(funds.name.desc()).all()
    return render_template('main/funds_documents.html', funds=fund)


@app.route('/documents/regulations') 
def regulations_documents():
    documents = regulations_document.query.order_by(regulations_document.upload_date.desc()).all()
    
    moscow_tz = pytz.timezone('Europe/Moscow')
    for doc in documents:
        if doc.upload_date:
            doc.upload_date = doc.upload_date.astimezone(moscow_tz)

    return render_template(
        'main/regulations_documents.html',
        documents=documents,
        current_date=datetime.now(pytz.timezone('Europe/Moscow')).date()
    )


@app.route('/documents/messages')
def messages_documents():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    # Получаем сообщения с пагинацией
    messages = inform_message.query.order_by(
        inform_message.upload_date.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('main/messages_documents.html', messages=messages)


@app.route('/documents/messages/<int:message_id>')
def message_detail(message_id):
    message = inform_message.query.get_or_404(message_id)
    return render_template('main/message_detail.html', message=message)


@app.route('/documents/funds/<fund_name>')
def fund_documents(fund_name):
    # Ищем фонд по url_name вместо id
    fund = funds.query.filter_by(url_name=fund_name).first_or_404()
    clean_name = re.sub(r'^[^«»"\'„""]*[«»"\'„""]|[«»"\'„""][^«»"\'„""]*$', '', fund.name)
    documents = fund_document.query.filter_by(fund_id=fund.id).all()
    
    # Группируем документы по типам
    documents_by_type = {}
    
    # Устанавливаем московский часовой пояс
    moscow_tz = pytz.timezone('Europe/Moscow')
    now = datetime.now(moscow_tz)
    
    for doc in documents:
        # Проверяем срок действия документа с учетом московского времени
        if doc.expiration_date:
            # Конвертируем дату окончания в московское время
            expiration_moscow = doc.expiration_date.astimezone(moscow_tz)
            
            # Добавляем 1 день к дате окончания для продления срока отображения
            expiration_moscow += timedelta(days=1)
            
            if expiration_moscow < now:
                continue  # Пропускаем документы, срок которых истек с учетом дополнительного дня
            
        if doc.document_type not in documents_by_type:
            documents_by_type[doc.document_type] = []
        documents_by_type[doc.document_type].append(doc)
    
    # Удаляем типы, где не осталось документов после фильтрации
    documents_by_type = {k: v for k, v in documents_by_type.items() if v}

    # Получаем значения стоимости пая для вкладки
    fund_values_data = []
    show_values_tab = False
    
    # Проверяем, есть ли данные в базе
    values_count = fund_values.query.filter_by(fund_id=fund.id).count()
    if values_count > 0:
        show_values_tab = True
        
        values = fund_values.query.filter_by(fund_id=fund.id)\
                                    .order_by(fund_values.date.desc())\
                                    .all()
        
        # Рассчитываем отклонения для каждого значения
        for value in values:
            # Проверяем, что у текущего значения есть необходимые данные
            if not value.share_price or not value.benchmark:
                value.deviation_20d = None
                value.deviation_250d = None
                fund_values_data.append(value)
                continue
            
            # Для 20 рабочих дней (~1 месяц)
            past_20d = fund_values.query.filter(
                fund_values.fund_id == fund.id,
                fund_values.date < value.date,
                fund_values.share_price.isnot(None),
                fund_values.benchmark.isnot(None)
            ).order_by(fund_values.date.desc()).offset(19).first()
            
            if past_20d and past_20d.share_price and past_20d.benchmark:
                try:
                    share_return_20d = (past_20d.share_price / value.share_price) - 1
                    bench_return_20d = (past_20d.benchmark / value.benchmark) - 1
                    value.deviation_20d = share_return_20d - bench_return_20d
                except (TypeError, ZeroDivisionError):
                    value.deviation_20d = None
            else:
                value.deviation_20d = None
            
            # Для 250 рабочих дней (~1 год)
            past_250d = fund_values.query.filter(
                fund_values.fund_id == fund.id,
                fund_values.date < value.date,
                fund_values.share_price.isnot(None),
                fund_values.benchmark.isnot(None)
            ).order_by(fund_values.date.desc()).offset(249).first()
            
            if past_250d and past_250d.share_price and past_250d.benchmark:
                try:
                    share_return_250d = (past_250d.share_price / value.share_price) - 1
                    bench_return_250d = (past_250d.benchmark / value.benchmark) - 1
                    value.deviation_250d = share_return_250d - bench_return_250d
                except (TypeError, ZeroDivisionError):
                    value.deviation_250d = None
            else:
                value.deviation_250d = None
            
            fund_values_data.append(value)

    # Обрабатываем текст для вывода
    if fund.text_for_document:
        text_for_display = fund.text_for_document.replace('\n', '<br>')
    else:
        text_for_display = None
    
    return render_template('main/fund_documents.html', 
                         fund=fund, 
                         clean_name=clean_name,
                         documents_by_type=documents_by_type,
                         fund_values=fund_values_data,
                         show_values_tab=show_values_tab,
                         values_count=values_count,
                         now=now,
                         text_for_display=text_for_display)


@app.route('/documents/funds/download/<filename>')
def download_document(filename):
    uploads = os.path.join(current_app.root_path, 'static/documents/funds/')
    return send_from_directory(uploads, filename, as_attachment=True)


@app.route('/documents/reports/download/<filename>')
def download_report_document(filename):
    uploads = os.path.join(current_app.root_path, 'static/documents/reports/')
    return send_from_directory(uploads, filename, as_attachment=True)


@app.route('/documents/regulations/download/<filename>')
def download_regulations_document(filename):
    uploads = os.path.join(current_app.root_path, 'static/documents/regulations/')
    return send_from_directory(uploads, filename, as_attachment=True)


@app.route('/about_company/news')
def news_list():
    """Страница со списком всех новостей"""
    try:
        all_news = news.query.order_by(news.news_date.desc()).all()
        
        # Группируем по годам
        news_by_year = {}
        for news_item in all_news:
            year = news_item.news_date.year
            if year not in news_by_year:
                news_by_year[year] = []
            news_by_year[year].append(news_item)
        
        # Передаем текущую дату в шаблон
        today = datetime.now().date()
        
        return render_template('main/news.html', 
                             news_by_year=news_by_year,
                             today=today)
                             
    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return render_template('main/news.html', 
                             news_by_year={},
                             today=datetime.now().date())


@app.route('/about_company/news/<int:news_id>')
def news_detail(news_id):
    """Страница отдельной новости"""

    news_item = news.query.get_or_404(news_id)
    
    # Получаем блоки новости
    news_blocks = news_block.query.filter_by(news_id=news_id)\
                                    .order_by(news_block.order_index)\
                                    .all()
    
    return render_template('main/new.html',
                            news=news_item,
                            blocks=news_blocks)


@app.route('/market_analytics')
def market_analytics_list():
    """Страница со списком всех аналитических материалов"""
    try:
        all_analytics = analytics.query.order_by(analytics.analytics_date.desc()).all()
        
        # Группируем по годам
        analytics_by_year = {}
        for analytic_item in all_analytics:
            year = analytic_item.analytics_date.year
            if year not in analytics_by_year:
                analytics_by_year[year] = []
            analytics_by_year[year].append(analytic_item)
        
        # Передаем текущую дату в шаблон
        today = datetime.now().date()
        
        return render_template('main/market_analytics.html', 
                             analytics_by_year=analytics_by_year,
                             today=today)
                             
    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return render_template('main/market_analytics.html', 
                             analytics_by_year={},
                             today=datetime.now().date())


@app.route('/market_analytics/<int:analytics_id>')
def analytics_detail(analytics_id):
    """Страница отдельной аналитики"""
    try:
        analytic_item = analytics.query.get_or_404(analytics_id)
        
        # Получаем блоки аналитики
        analytics_blocks = analytics_block.query.filter_by(analytics_id=analytics_id)\
                                               .order_by(analytics_block.order_index)\
                                               .all()
        
        return render_template('main/analytic_detail.html',
                             analytic=analytic_item,
                             blocks=analytics_blocks)
    except Exception as e:
        print(f"Ошибка: {e}")
        abort(404)


@app.route('/personal_accounts')
def personal_accounts():
    """Страница с доступом к личным кабинетами"""
    # Получаем все фонды из базы данных
    all_funds = db.session.query(funds).filter_by(is_archived=False).all()
    
    processed_funds = []
    for fund in all_funds:
        # Упрощенная логика - берем текст между « и »
        name = fund.name
        name_in_quotes = fund.short_name  # По умолчанию используем short_name
        
        # Пытаемся найти текст в кавычках
        if '«' in name and '»' in name:
            start = name.find('«') + 1
            end = name.find('»')
            if start < end:
                name_in_quotes = name[start:end]
        elif '"' in name:
            # Или ищем в двойных кавычках
            parts = name.split('"')
            if len(parts) > 1:
                name_in_quotes = parts[1]  # Берем текст между первыми кавычками
        
        processed_funds.append({
            'id': fund.id,
            'name': name_in_quotes,
            'logo': fund.logo,
            'logo_mimetype': fund.logo_mimetype
        })
    
    return render_template('main/personal_accounts.html', funds=processed_funds)


@app.route('/about_company/history')
def company_history():
    """Страница с историей компании"""
    return render_template('main/history.html')         

