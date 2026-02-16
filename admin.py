from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, abort, jsonify
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
import os
from os import path
from flask_sqlalchemy import SQLAlchemy
from db import db
from db.models import funds, fund_conditions, fund_manager, fund_steps, fund_values, fund_composition, fund_document, report_document, regulations_document, inform_message, news, news_block, analytics, analytics_block, admin_user, company_history_event
from flask_login import LoginManager, login_user, login_required, current_user, logout_user
import json
from datetime import timezone
import pandas as pd
from werkzeug.utils import secure_filename # Для безопасного имени файла
import uuid # Для генерации уникальных имен
import pytz
import base64
import time
from werkzeug.security import check_password_hash

# Создаем блюпринт
admin = Blueprint('admin', __name__, url_prefix='/admin')

# Создаем login_manager
login_manager = LoginManager()

def init_admin_auth(app):
    """Инициализация аутентификации для админки"""
    login_manager.init_app(app)
    login_manager.login_view = 'admin.login'
    login_manager.login_message = 'Требуется авторизация'
    
    @login_manager.user_loader
    def load_user(user_id):
        from db.models import admin_user
        return admin_user.query.get(int(user_id))


# Роуты аутентификации ДОЛЖНЫ БЫТЬ ПОСЛЕ объявления блюпринта
@admin.route('/login', methods=['GET', 'POST'])
def login():
    # Используем current_user.is_authenticated правильно
    if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
        return redirect(url_for('admin.index_admin'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember_me = bool(request.form.get('remember_me'))
        
        if not username or not password:
            flash('Пожалуйста, заполните все поля', 'error')
            return render_template('admin/login.html')
        
        from db.models import admin_user
        user = admin_user.query.filter_by(username=username).first()
        
        if user and user.check_password(password) and user.is_active:
            login_user(user, remember=remember_me)
            flash('Вы успешно вошли в систему!', 'success')
            
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/admin'):
                return redirect(next_page)
            return redirect(url_for('admin.index_admin'))
        else:
            time.sleep(1)  # Задержка против брутфорса
            flash('Неверное имя пользователя или пароль', 'error')
    
    return render_template('admin/login.html')


@admin.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы успешно вышли из системы', 'success')
    return redirect(url_for('admin.login'))


@admin.route('/')
@login_required
def index_admin():
    from db.models import funds, fund_document, news  # импортируй свои модели
    
    funds_count = funds.query.count()
    documents_count = fund_document.query.count()  # или другая модель документов
    news_count = news.query.count()
    
    return render_template('admin/admin.html', 
                         funds_count=funds_count,
                         documents_count=documents_count,
                         news_count=news_count)


@admin.route('/funds')
@login_required
def funds_admin():
    fund = db.session.query(funds).order_by(funds.id).all()
    return render_template('admin/funds.html', funds=fund)


@admin.route('/funds/create', methods=['GET', 'POST'])
@login_required
def create_fund():
    # Получаем все существующие названия
    existing_funds = funds.query.with_entities(funds.name, funds.url_name).all()
    existing_names = [fund.name for fund in existing_funds]
    existing_urls = [fund.url_name for fund in existing_funds]
    
    if request.method == 'POST':
        try:
            name = request.form['name']
            url_name = request.form['url_name']
            
            # Серверная проверка
            if name in existing_names:
                flash('Фонд с таким названием уже существует', 'error')
                return render_template('admin/fund_form.html', 
                                     is_edit=False,
                                     existing_names=existing_names,
                                     existing_urls=existing_urls,
                                     form_data=request.form)
            
            if url_name in existing_urls:
                flash('Фонд с таким URL именем уже существует', 'error')
                return render_template('admin/fund_form.html',
                                     is_edit=False,
                                     existing_names=existing_names,
                                     existing_urls=existing_urls,
                                     form_data=request.form)
            
            # Создание основного объекта фонда
            new_fund = funds(
                name=name,
                short_name=request.form['short_name'],
                url_name=url_name,
                description=request.form['description'],
                strategy=request.form['strategy'],
                additional_info=request.form.get('additional_info', ''),
                cards_description=request.form['cards_description'],
                footer_description=request.form['footer_description'],
                cards_animation=bool(request.form.get('cards_animation')),
                cards_amount=int(request.form['cards_amount']),
                cards_period=int(request.form['cards_period']),
                for_qualified_investors=bool(request.form.get('for_qualified_investors'))
            )
            
            # Обработка загрузки изображений
            background_image = request.files.get('background_image')
            logo = request.files.get('logo')
            
            if background_image and background_image.filename:
                new_fund.background_image = background_image.read()
                new_fund.background_mimetype = background_image.mimetype
            
            if logo and logo.filename:
                new_fund.logo = logo.read()
                new_fund.logo_mimetype = logo.mimetype
            
            db.session.add(new_fund)
            db.session.flush()  # Получаем ID нового фонда
            
            # Добавление условий инвестирования
            conditions_titles = request.form.getlist('conditions_title[]')
            conditions_descriptions = request.form.getlist('conditions_description[]')
            conditions_orders = request.form.getlist('conditions_order[]')
            
            for i in range(len(conditions_titles)):
                if conditions_titles[i].strip():
                    order_value = int(conditions_orders[i]) if i < len(conditions_orders) else i + 1
                    condition = fund_conditions(
                        fund_id=new_fund.id,
                        title=conditions_titles[i],
                        description=conditions_descriptions[i] if i < len(conditions_descriptions) else '',
                        order=order_value
                    )
                    db.session.add(condition)
            
            # Добавление шагов инвестирования
            steps_titles = request.form.getlist('steps_title[]')
            steps_descriptions = request.form.getlist('steps_description[]')
            steps_times = request.form.getlist('steps_time[]')
            steps_orders = request.form.getlist('steps_order[]')
            
            for i in range(len(steps_titles)):
                if steps_titles[i].strip():
                    order_value = int(steps_orders[i]) if i < len(steps_orders) else i + 1
                    step = fund_steps(
                        fund_id=new_fund.id,
                        title=steps_titles[i],
                        description=steps_descriptions[i] if i < len(steps_descriptions) else '',
                        time_required=steps_times[i] if i < len(steps_times) else '',
                        order=order_value
                    )
                    db.session.add(step)
            
            # Добавление управляющего фондом
            manager_name = request.form.get('managers_name')
            if manager_name and manager_name.strip():
                manager = fund_manager(
                    fund_id=new_fund.id,
                    name=manager_name,
                    position=request.form.get('managers_position', ''),
                    comment=request.form.get('managers_comment', '')
                )
                
                # Обработка фото управляющего
                manager_photo = request.files.get('managers_photo')
                if manager_photo and manager_photo.filename:
                    manager.photo = manager_photo.read()
                    manager.photo_mimetype = manager_photo.mimetype
                
                db.session.add(manager)
            
            db.session.commit()
            flash('Фонд успешно создан', 'success')
            return redirect(url_for('admin.funds_admin'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при создании фонда: {str(e)}', 'error')
    
    # Для GET запроса создаем пустой объект фонда
    empty_fund = type('Fund', (), {
        'name': '',
        'short_name': '',
        'url_name': '',
        'description': '',
        'strategy': '',
        'additional_info': '',
        'cards_description': '',
        'footer_description': '',
        'cards_animation': False,
        'cards_amount': '',
        'cards_period': '',
        'for_qualified_investors': False,
        'conditions': [],
        'steps': [],
        'manager': None,
        'background_image': None,
        'background_mimetype': None,
        'logo': None,
        'logo_mimetype': None
    })()
    
    return render_template('admin/fund_form.html',
                         is_edit=False,
                         fund=empty_fund,
                         existing_names=existing_names,
                         existing_urls=existing_urls)


@admin.route('/funds/edit/<string:url_name>', methods=['GET', 'POST'])
@login_required
def edit_fund(url_name):
    fund = db.session.query(funds).filter_by(url_name=url_name).first_or_404()
    
    # Загружаем связанные данные
    fund.conditions = fund_conditions.query.filter_by(fund_id=fund.id).order_by(fund_conditions.order).all()
    fund.steps = fund_steps.query.filter_by(fund_id=fund.id).order_by(fund_steps.order).all()
    fund.manager = fund_manager.query.filter_by(fund_id=fund.id).first()
    
    existing_funds = funds.query.with_entities(funds.name, funds.url_name).all()
    existing_names = [f.name for f in existing_funds]
    existing_urls = [f.url_name for f in existing_funds]
    
    if request.method == 'POST':
        try:
            # Обновляем основные данные
            fund.name = request.form['name']
            fund.short_name = request.form['short_name']
            fund.url_name = request.form['url_name']
            fund.description = request.form['description']
            fund.strategy = request.form['strategy']
            fund.additional_info = request.form.get('additional_info', '')
            fund.cards_description = request.form['cards_description']
            fund.cards_animation = 'cards_animation' in request.form
            fund.cards_amount = int(request.form['cards_amount'])
            fund.cards_period = int(request.form['cards_period'])
            fund.footer_description = request.form['footer_description']
            fund.for_qualified_investors = 'for_qualified_investors' in request.form
            
            # Обновляем изображения если загружены новые
            background_image = request.files.get('background_image')
            logo = request.files.get('logo')
            
            if background_image and background_image.filename:
                fund.background_image = background_image.read()
                fund.background_mimetype = background_image.mimetype
            
            if logo and logo.filename:
                fund.logo = logo.read()
                fund.logo_mimetype = logo.mimetype
            
            # Удаляем старые условия и шаги
            fund_conditions.query.filter_by(fund_id=fund.id).delete()
            fund_steps.query.filter_by(fund_id=fund.id).delete()
            
            # Добавляем новые условия инвестирования
            conditions_titles = request.form.getlist('conditions_title[]')
            conditions_descriptions = request.form.getlist('conditions_description[]')
            conditions_orders = request.form.getlist('conditions_order[]')
            
            for i in range(len(conditions_titles)):
                if conditions_titles[i].strip():
                    order_value = int(conditions_orders[i]) if i < len(conditions_orders) else i + 1
                    condition = fund_conditions(
                        fund_id=fund.id,
                        title=conditions_titles[i],
                        description=conditions_descriptions[i] if i < len(conditions_descriptions) else '',
                        order=order_value
                    )
                    db.session.add(condition)
            
            # Добавляем новые шаги инвестирования
            steps_titles = request.form.getlist('steps_title[]')
            steps_descriptions = request.form.getlist('steps_description[]')
            steps_times = request.form.getlist('steps_time[]')
            steps_orders = request.form.getlist('steps_order[]')
            
            for i in range(len(steps_titles)):
                if steps_titles[i].strip():
                    order_value = int(steps_orders[i]) if i < len(steps_orders) else i + 1
                    step = fund_steps(
                        fund_id=fund.id,
                        title=steps_titles[i],
                        description=steps_descriptions[i] if i < len(steps_descriptions) else '',
                        time_required=steps_times[i] if i < len(steps_times) else '',
                        order=order_value
                    )
                    db.session.add(step)
            
            # Обработка управляющего фондом
            manager_id = request.form.get('manager_id')
            manager_name = request.form.get('managers_name')
            
            if manager_id:
                # Обновляем существующего управляющего
                manager = fund_manager.query.get(int(manager_id))
                if manager:
                    manager.name = manager_name if manager_name else ''
                    manager.position = request.form.get('managers_position', '')
                    manager.comment = request.form.get('managers_comment', '')
                    
                    # Обновление фото
                    manager_photo = request.files.get('managers_photo')
                    if manager_photo and manager_photo.filename:
                        manager.photo = manager_photo.read()
                        manager.photo_mimetype = manager_photo.mimetype
            elif manager_name and manager_name.strip():
                # Создаем нового управляющего
                manager = fund_manager(
                    fund_id=fund.id,
                    name=manager_name,
                    position=request.form.get('managers_position', ''),
                    comment=request.form.get('managers_comment', '')
                )
                
                manager_photo = request.files.get('managers_photo')
                if manager_photo and manager_photo.filename:
                    manager.photo = manager_photo.read()
                    manager.photo_mimetype = manager_photo.mimetype
                
                db.session.add(manager)
            
            db.session.commit()
            flash('Фонд успешно обновлен', 'success')
            return redirect(url_for('admin.funds_admin'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обновлении фонда: {str(e)}', 'error')
    
    return render_template('admin/fund_form.html', 
                         is_edit=True,
                         fund=fund, 
                         existing_names=existing_names,
                         existing_urls=existing_urls)


@admin.route('/funds/archive/<string:url_name>')
@login_required
def archive_fund(url_name):
    fund = db.session.query(funds).filter_by(url_name=url_name).first_or_404()
    fund.is_archived = not fund.is_archived
    db.session.commit()
    
    status = "архивирован" if fund.is_archived else "восстановлен из архива"
    flash(f'Фонд {status}', 'success')
    return redirect(url_for('admin.funds_admin'))


@admin.route('/funds/delete/<string:url_name>')
@login_required
def delete_fund(url_name):
    fund = db.session.query(funds).filter_by(url_name=url_name).first_or_404()
    db.session.delete(fund)
    db.session.commit()
    flash('Фонд удален', 'success')
    return redirect(url_for('admin.funds_admin'))


@admin.route('/funds/<fund_name>', methods=['GET'])
@login_required
def fund_admin(fund_name):
    # Получаем текущий фонд
    current_fund = db.session.query(funds).filter_by(url_name=fund_name).first()
    if not current_fund:
        abort(404, description="Фонд не найден")
    
    # Получаем список всех фондов
    short_names = db.session.query(funds).order_by(funds.id).all()
    
    return render_template('admin/fund.html',
                         current_fund=current_fund,
                         short_names=short_names)
   

@admin.route('/funds/<fund_name>/fund-values', methods=['GET', 'POST'])
@login_required
def handle_fund_values(fund_name):
    # Получаем фонд из базы данных
    fund = db.session.query(funds).filter_by(url_name=fund_name).first()
    short_names = db.session.query(funds).order_by(funds.id).all()
    current_fund = db.session.query(funds).filter_by(url_name=fund_name).first()
    
    if not current_fund or not fund:
        abort(404, description="Фонд не найден")

    # Получаем данные для текущего фонда и конвертируем время
    fund_data = fund_values.query.filter_by(fund_id=fund.id).order_by(fund_values.date.desc()).all()
    
    # Конвертируем upload_date в московское время для каждого элемента
    moscow_tz = pytz.timezone('Europe/Moscow')
    for item in fund_data:
        if item.upload_date:
            # Если время в UTC, конвертируем в московское
            if item.upload_date.tzinfo is None:
                utc_time = item.upload_date.replace(tzinfo=timezone.utc)
                item.moscow_upload_date = utc_time.astimezone(moscow_tz)
            else:
                item.moscow_upload_date = item.upload_date.astimezone(moscow_tz)
        else:
            item.moscow_upload_date = None

    error_message = request.args.get('error')
    success_message = request.args.get('success')

    # Получаем список доступных дат для календаря
    available_dates = [result[0].strftime('%Y-%m-%d') for result in 
                     db.session.query(fund_values.date.distinct())
                     .filter_by(fund_id=fund.id)
                     .order_by(fund_values.date.desc())
                     .all()]

    if request.method == 'POST':
        # Обработка добавления данных
        if 'scha' in request.form:
            scha = request.form.get('scha')
            share_price = request.form.get('share_price')
            benchmark = request.form.get('benchmark')
            date = request.form.get('date')

            if not all([scha, share_price, benchmark, date]):
                error_message = "Заполнены не все поля"
            else:
                try:
                    share_price = float(request.form['share_price'].replace(',', '.'))
                    benchmark = float(request.form['benchmark'].replace(',', '.'))
                    scha = float(request.form['scha'].replace(',', '.'))
                    datetime.strptime(date, '%Y-%m-%d')  # Проверка даты
                    
                    new_fund = fund_values(
                        fund_id=fund.id,
                        share_price=share_price,
                        benchmark=benchmark,
                        scha=scha,
                        date=date
                    )
                    
                    db.session.add(new_fund)
                    db.session.commit()
                    return redirect(url_for('admin.handle_fund_values', 
                                          fund_name=fund.url_name,
                                          success="Данные успешно добавлены"))
                    
                except ValueError:
                    error_message = "Некорректный формат чисел"
                except Exception as e:
                    db.session.rollback()
                    error_message = f"Ошибка: {str(e)}"

    return render_template('admin/fund_values.html', 
                         fund=fund,
                         fund_data=fund_data,
                         error=error_message,
                         success=success_message,
                         available_dates=available_dates,
                         fund_name=fund.name,
                         short_names=short_names,
                         current_fund=current_fund)


@admin.route('/update-fund-value', methods=['POST'])
@login_required
def update_fund_value():
    try:
        fund_value_id = request.form.get('fund_value_id')
        share_price = float(request.form['share_price'].replace(',', '.'))
        benchmark = float(request.form['benchmark'].replace(',', '.'))
        scha = float(request.form['scha'].replace(',', '.'))
        
        # Находим запись для обновления
        fund_value = fund_values.query.get(fund_value_id)
        
        if not fund_value:
            return jsonify({'success': False, 'error': 'Запись не найдена'})
        
        # Обновляем значения
        fund_value.share_price = share_price
        fund_value.benchmark = benchmark
        fund_value.scha = scha
        
        db.session.commit()
        return jsonify({'success': True})
        
    except ValueError:
        return jsonify({'success': False, 'error': 'Некорректный формат чисел'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})
    
    
@admin.route('/delete-fund-value-row', methods=['POST'])
@login_required
def delete_fund_value_row():
    try:
        fund_value_id = request.form.get('fund_value_id')
        
        if not fund_value_id:
            flash('Не указан ID записи', 'error')
            return redirect(request.referrer or url_for('admin.handle_fund_values', fund_name=request.args.get('fund_name')))
        
        # Находим и удаляем запись
        fund_value = fund_values.query.get(fund_value_id)
        
        if not fund_value:
            flash('Запись не найдена', 'error')
            return redirect(request.referrer or url_for('admin.handle_fund_values', fund_name=request.args.get('fund_name')))
        
        db.session.delete(fund_value)
        db.session.commit()
        flash('Данные успешно удалены', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении: {str(e)}', 'error')
    
    return redirect(request.referrer or url_for('admin.handle_fund_values', fund_name=request.args.get('fund_name')))


# Роут для работы с составом фонда
@admin.route('/funds/<fund_name>/fund-composition', methods=['GET', 'POST'])
@login_required
def handle_fund_composition(fund_name):
    # Получаем фонд из базы данных
    fund = db.session.query(funds).filter_by(url_name=fund_name).first()
    short_names = db.session.query(funds).order_by(funds.id).all()
    current_fund = db.session.query(funds).filter_by(url_name=fund_name).first()
    if not current_fund:
        abort(404, description="Фонд не найден")
    
    if not fund:
        abort(404, description="Фонд не найден")

    composition_data = []
    error_message = None
    error_message_delete = None
    success_message = None
    success_message_delete = None
    preview_data = None
    preview_date = None
    current_chart_type = 'pie'  # значение по умолчанию

    # Получаем список уникальных дат для фильтра
    composition_dates = [result[0] for result in 
                       db.session.query(fund_composition.date.distinct())
                       .filter_by(fund_id=fund.id)
                       .order_by(fund_composition.date.desc())
                       .all()]
    
    # Получаем выбранную дату
    selected_date = request.args.get('composition_date')
    if not selected_date and composition_dates:
        selected_date = composition_dates[0].strftime('%Y-%m-%d')
    
    if selected_date:
        composition_data = fund_composition.query.filter_by(
            fund_id=fund.id,
            date=selected_date
        ).order_by(fund_composition.amount.desc()).all()
        
        # Получаем тип диаграммы из первой записи (они все одинаковые для одной даты)
        if composition_data:
            current_chart_type = composition_data[0].chart_type

    if request.method == 'POST':
        # Обработка Excel файла (предпросмотр)
        if 'excel_file' in request.files and 'preview' in request.form:
            file = request.files['excel_file']
            preview_date = request.form.get('composition_date')
            chart_type = request.form.get('chart_type', 'pie')  # Получаем тип диаграммы
            
            if file.filename == '':
                error_message = "Файл не выбран"
            elif not preview_date:
                error_message = "Укажите дату для загружаемых данных"
            else:
                try:
                    df = pd.read_excel(file, engine='openpyxl')
                    
                    # Проверяем наличие обязательных колонок в зависимости от типа диаграммы
                    if chart_type == 'pie':
                        required_columns = ['Сектор', 'Доля']
                        if not all(col in df.columns for col in required_columns):
                            missing_cols = [col for col in required_columns if col not in df.columns]
                            error_message = f"Для круговой диаграммы обязательны колонки: {', '.join(missing_cols)}"
                        else:
                            # Проверяем сумму долей для круговой диаграммы
                            df['Доля'] = pd.to_numeric(df['Доля'], errors='coerce')
                            df = df.dropna(subset=['Сектор', 'Доля'])
                            total_share = df['Доля'].sum()
                            if not (0.99 <= total_share <= 1.01):
                                error_message = f"Сумма долей должна быть равна 100% (текущая сумма: {total_share:.2%})"
                            else:
                                if 'Эмитент' not in df.columns:
                                    df['Эмитент'] = None
                                if 'Сумма' not in df.columns:
                                    df['Сумма'] = 0.0
                                
                                # Добавляем тип диаграммы в данные предпросмотра
                                preview_records = df.to_dict(orient='records')
                                for record in preview_records:
                                    record['chart_type'] = chart_type
                                
                                session['preview_data'] = preview_records
                                session['preview_date'] = preview_date
                                preview_data = preview_records
                                success_message = "Файл успешно загружен для предпросмотра"
                    
                    else:  # Для гистограммы
                        if 'Сектор' not in df.columns:
                            error_message = "Для гистограммы обязательна колонка 'Сектор'"
                        else:
                            # Проверяем, есть ли хотя бы одна из колонок: Доля или Сумма
                            has_share = 'Доля' in df.columns
                            has_amount = 'Сумма' in df.columns
                            
                            if not (has_share or has_amount):
                                error_message = "Для гистограммы необходима колонка 'Доля' или 'Сумма'"
                            else:
                                # Обрабатываем числовые данные
                                if has_share:
                                    df['Доля'] = pd.to_numeric(df['Доля'], errors='coerce')
                                if has_amount:
                                    df['Сумма'] = pd.to_numeric(df['Сумма'], errors='coerce')
                                
                                df = df.dropna(subset=['Сектор'])
                                
                                if 'Эмитент' not in df.columns:
                                    df['Эмитент'] = None
                                if 'Доля' not in df.columns:
                                    df['Доля'] = 0.0
                                if 'Сумма' not in df.columns:
                                    df['Сумма'] = 0.0
                                
                                # Добавляем тип диаграммы в данные предпросмотра
                                preview_records = df.to_dict(orient='records')
                                for record in preview_records:
                                    record['chart_type'] = chart_type
                                
                                session['preview_data'] = preview_records
                                session['preview_date'] = preview_date
                                preview_data = preview_records
                                success_message = "Файл успешно загружен для предпросмотра"
                
                except Exception as e:
                    error_message = f"Ошибка при обработке файла: {str(e)}"

        # Публикация данных из предпросмотра
        elif 'publish' in request.form:
            if 'preview_data' in session and 'preview_date' in session:
                try:
                    preview_data = session['preview_data']
                    preview_date = session['preview_date']
                    
                    # Удаляем старые данные за эту дату
                    deleted_rows = fund_composition.query.filter_by(fund_id=fund.id, date=preview_date).delete()
                    
                    # Добавляем новые данные
                    for row in preview_data:
                        # Заменяем nan на None для строковых полей и на 0.0 для числовых
                        issuer_value = row.get('Эмитент')
                        if pd.isna(issuer_value):
                            issuer_value = None
                        
                        sector_value = row['Сектор']
                        if pd.isna(sector_value):
                            sector_value = None
                        
                        # Для числовых полей заменяем nan на 0.0
                        amount_value = row.get('Сумма', 0.0)
                        if pd.isna(amount_value):
                            amount_value = 0.0
                        else:
                            amount_value = float(amount_value)
                        
                        share_value = row.get('Доля', 0.0)
                        if pd.isna(share_value):
                            share_value = 0.0
                        else:
                            share_value = float(share_value)
                        
                        # Получаем тип диаграммы (сохраняем из предпросмотра)
                        chart_type = row.get('chart_type', 'pie')
                        
                        new_composition = fund_composition(
                            fund_id=fund.id,
                            date=preview_date,
                            issuer=issuer_value,
                            sector=sector_value,
                            amount=amount_value,
                            share=share_value,
                            chart_type=chart_type  # Сохраняем тип диаграммы
                        )
                        db.session.add(new_composition)
                    
                    db.session.commit()
                    session.pop('preview_data', None)
                    session.pop('preview_date', None)
                    success_message = f"Данные за {preview_date} успешно опубликованы"
                    return redirect(url_for('admin.handle_fund_composition', 
                                        fund_name=fund.url_name,
                                        success=success_message,
                                        composition_date=preview_date))
                
                except Exception as e:
                    db.session.rollback()
                    error_message = f"Ошибка при публикации данных: {str(e)}"
            else:
                error_message = "Нет данных для публикации"
                
        # Удаление данных состава фонда
        elif 'delete_action' in request.form:
            delete_date = request.form.get('delete_date_select') or request.form.get('delete_date_input')
            
            if not delete_date:
                error_message_delete = "Укажите дату для удаления"
            else:
                try:
                    exists = db.session.query(
                        fund_composition.query.filter_by(fund_id=fund.id, date=delete_date).exists()
                    ).scalar()
                    
                    if not exists:
                        error_message_delete = f"Нет данных состава фонда за {delete_date}"
                    else:
                        deleted_rows = fund_composition.query.filter_by(fund_id=fund.id, date=delete_date).delete()
                        db.session.commit()
                        success_message_delete = f"Данные состава фонда за {delete_date} успешно удалены ({deleted_rows} записей)"
                    
                    return redirect(url_for('admin.handle_fund_composition', 
                                        fund_name=fund.url_name,
                                        success_delete=success_message_delete, 
                                        error_delete=error_message_delete))
                    
                except Exception as e:
                    db.session.rollback()
                    error_message_delete = f"Ошибка при удалении данных: {str(e)}"
                    return redirect(url_for('admin.handle_fund_composition', 
                                        fund_name=fund.url_name,
                                        error_delete=error_message_delete))
                
    # Получаем сообщения из GET параметров (после редиректа)
    success_message = request.args.get('success', None)
    error_message = request.args.get('error', error_message)
    success_message_delete = request.args.get('success_delete', None)
    error_message_delete = request.args.get('error_delete', None)

    # Подготавливаем данные для диаграмм
    issuer_data = []
    sector_data = []
    has_issuer_data = False
    has_sector_data = False

    if composition_data:
        # Группируем по эмитентам
        issuer_dict = {}
        sector_dict = {}
        
        for item in composition_data:
            if item.issuer and (item.share > 0 or item.amount > 0):
                # Для гистограммы используем amount, для круговой - share
                value = item.amount if current_chart_type == 'column' else item.share
                issuer_dict[item.issuer] = issuer_dict.get(item.issuer, 0) + value
                has_issuer_data = True
            if item.sector and (item.share > 0 or item.amount > 0):
                value = item.amount if current_chart_type == 'column' else item.share
                sector_dict[item.sector] = sector_dict.get(item.sector, 0) + value
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
        
        issuer_data = prepare_chart_data(issuer_dict) if has_issuer_data else []
        sector_data = prepare_chart_data(sector_dict) if has_sector_data else []

    # Получаем дату состава для отображения
    composition_date = selected_date if selected_date else None
    if composition_date:
        try:
            composition_date = datetime.strptime(composition_date, '%Y-%m-%d').strftime('%d.%m.%Y')
        except:
            pass

    return render_template('admin/fund_composition.html', 
                        composition_data=composition_data,
                        error=error_message,
                        success=success_message,
                        composition_dates=composition_dates,
                        preview_data=preview_data,
                        preview_date=preview_date,
                        selected_date=selected_date,
                        success_delete=success_message_delete, 
                        error_delete=error_message_delete,
                        fund_name=fund.url_name,
                        short_names=short_names,
                        current_fund=current_fund,
                        # Данные для диаграмм
                        issuer_data=json.dumps(issuer_data),
                        sector_data=json.dumps(sector_data),
                        has_issuer_data=has_issuer_data,
                        has_sector_data=has_sector_data,
                        composition_date=composition_date,
                        # Тип диаграммы
                        chart_type=current_chart_type)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ['xlsx', 'xls', 'csv']


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


@admin.route('/funds/<fund_name>/documents', methods=['GET', 'POST'])
@login_required
def handle_documents(fund_name):
    # Получаем фонд из базы данных
    fund = db.session.query(funds).filter_by(url_name=fund_name).first()
    short_names = db.session.query(funds).order_by(funds.id).all()
    current_fund = db.session.query(funds).filter_by(url_name=fund_name).first()
    if not current_fund:
        abort(404, description="Фонд не найден")
    
    if not fund:
        abort(404, description="Фонд не найден")

    # Получаем все существующие типы документов
    existing_types = db.session.query(fund_document.document_type)\
                              .filter_by(fund_id=fund.id)\
                              .distinct().all()
    document_types = [t[0] for t in existing_types] if existing_types else []

    # Обработка удаления текста
    if request.args.get('clear_text'):
        fund.text_for_document = None
        db.session.commit()
        flash('Текст удален', 'text_form')
        return redirect(url_for('admin.handle_documents', fund_name=fund_name))

    if request.method == 'POST':
        # Обработка формы текста 
        if 'text_for_document' in request.form:
            new_text = request.form.get('text_for_document', '').strip()
            current_text = (fund.text_for_document or '').strip()
            
            if new_text == current_text:
                flash('Текст не был изменен', 'text_form')
            else:
                fund.text_for_document = new_text or None
                db.session.commit()
                if new_text:
                    flash('Текст для раздела документов обновлен', 'text_form')
                else:
                    flash('Текст удален', 'text_form')
            return redirect(url_for('admin.handle_documents', fund_name=fund_name))
        
        # Обработка формы pdy_date
        elif 'pdy_date' in request.form:
            pdy_date = request.form.get('pdy_date', '').strip()
            current_pdy_date = (fund.pdy_date or '').strip()
            
            if pdy_date == current_pdy_date:
                flash('Дата ПДУ не была изменена', 'pdy_form')
            else:
                # Сохраняем старую дату для сравнения
                old_pdy_date = fund.pdy_date
                fund.pdy_date = pdy_date or None
                
                # Если дата ПДУ изменилась, обновляем документы с типом расчета 'pdy_date'
                if pdy_date and pdy_date != old_pdy_date:
                    try:
                        # Находим все документы этого фонда с расчетом от ПДУ
                        documents_to_update = fund_document.query.filter_by(
                            fund_id=fund.id,
                            expiration_calculation_type='pdy_date'
                        ).all()
                        
                        updated_count = 0
                        new_pdy_date_obj = datetime.strptime(pdy_date, '%Y-%m-%d')
                        
                        for doc in documents_to_update:
                            doc.expiration_date = new_pdy_date_obj
                            updated_count += 1
                        
                        if updated_count > 0:
                            flash(f'Дата ПДУ обновлена. Обновлено документов: {updated_count}', 'pdy_form')
                        else:
                            flash('Дата ПДУ обновлена', 'pdy_form')
                            
                    except Exception as e:
                        db.session.rollback()
                        flash('Ошибка при обновлении документов', 'pdy_form')
                        current_app.logger.error(f'Error updating PDY documents: {str(e)}')
                        return redirect(url_for('admin.handle_documents', fund_name=fund_name))
                
                db.session.commit()
                if not pdy_date:
                    flash('Дата ПДУ удалена', 'pdy_form')
                    
            return redirect(url_for('admin.handle_documents', fund_name=fund_name))
        
        # Обработка формы документов
        elif 'document_name' in request.form:
            document_name = request.form.get('document_name', '').strip()
            document_type = request.form.get('document_type', '').strip()
            new_document_type = request.form.get('new_document_type', '').strip()
            expiration_date_type = request.form.get('expiration_date_type', 'manual')  # Добавляем получение типа даты
            expiration_date_str = request.form.get('expiration_date')

            # Валидация
            if not document_type and not new_document_type:
                flash('Тип документа обязателен для заполнения.', 'doc_form')
                return redirect(url_for('admin.handle_documents', fund_name=fund_name))
                
            if new_document_type:
                document_type = new_document_type.strip()
                if not document_type:
                    flash('Новый тип документа не может быть пустым.', 'doc_form')
                    return redirect(url_for('admin.handle_documents', fund_name=fund_name))

            if not document_name:
                flash('Название документа обязательно.', 'doc_form')
                return redirect(url_for('admin.handle_documents', fund_name=fund_name))

            # Обработка даты и файла
            expiration_date_obj = None
            expiration_calculation_type = None

            if expiration_date_type != 'manual':
                # Автоматический расчет даты
                expiration_calculation_type = expiration_date_type
                
                if expiration_date_type == 'pdy_date' and fund.pdy_date:
                    # Используем дату ПДУ как есть
                    expiration_date_obj = datetime.strptime(fund.pdy_date, '%Y-%m-%d')
                elif expiration_date_type == '6months':
                    # 6 месяцев от сегодня
                    expiration_date_obj = datetime.now() + timedelta(days=180)
                elif expiration_date_type == '3years':
                    # 3 года от сегодня
                    expiration_date_obj = datetime.now() + timedelta(days=1095)
            elif expiration_date_str:
                # Ручной ввод
                try:
                    expiration_date_obj = datetime.strptime(expiration_date_str, '%Y-%m-%d')
                    expiration_calculation_type = 'manual'
                    if expiration_date_obj.date() < datetime.utcnow().date():
                        flash('Дата окончания не может быть в прошлом.', 'doc_form')
                        return redirect(url_for('admin.handle_documents', fund_name=fund_name))
                except ValueError:
                    flash('Неверный формат даты. Используйте формат ГГГГ-ММ-ДД', 'doc_form')
                    return redirect(url_for('admin.handle_documents', fund_name=fund_name))

            if 'document_file' not in request.files:
                flash('Файл не выбран.', 'doc_form')
                return redirect(url_for('admin.handle_documents', fund_name=fund_name))

            file = request.files['document_file']
            if file.filename == '':
                flash('Файл не выбран.', 'doc_form')
                return redirect(url_for('admin.handle_documents', fund_name=fund_name))

            if not allowed_file(file.filename):
                flash('Разрешены только PDF-файлы.', 'doc_form')
                return redirect(url_for('admin.handle_documents', fund_name=fund_name))

            # Проверка размера файла
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            if file_size > current_app.config['MAX_CONTENT_LENGTH']:
                flash(f"Файл слишком большой. Максимальный размер: {current_app.config['MAX_CONTENT_LENGTH'] / (1024*1024):.0f} МБ.", 'doc_form')
                return redirect(url_for('admin.handle_documents', fund_name=fund_name))

            # Сохранение документа
            try:
                unique_filename = str(uuid.uuid4()) + '.pdf'
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(file_path)

                document_url = url_for('static', filename='documents/funds/' + unique_filename, _external=True)

                new_document = fund_document(
                    fund_id=fund.id,
                    name=document_name,
                    url=document_url,
                    document_type=document_type,
                    expiration_date=expiration_date_obj,
                    expiration_calculation_type=expiration_calculation_type,  # Сохраняем тип расчета
                    upload_date=datetime.now(pytz.timezone('Europe/Moscow')))
                
                db.session.add(new_document)
                db.session.commit()
                flash('Документ успешно добавлен!', 'doc_form')
                
            except Exception as e:
                db.session.rollback()
                if os.path.exists(file_path):
                    os.remove(file_path)
                current_app.logger.error(f'Error uploading document: {str(e)}')
                flash('Произошла ошибка при загрузке файла. Пожалуйста, попробуйте позже.', 'doc_form')
            
            return redirect(url_for('admin.handle_documents', fund_name=fund_name))
        
    # Получение документов
    documents = fund_document.query\
                           .filter_by(fund_id=fund.id)\
                           .order_by(fund_document.upload_date.desc())\
                           .all()
    
    # Конвертация времени
    moscow_tz = pytz.timezone('Europe/Moscow')
    for doc in documents:
        if doc.upload_date:
            doc.upload_date = doc.upload_date.astimezone(moscow_tz)
    
    return render_template(
        'admin/fund_documents.html', 
        documents=documents,
        document_types=document_types,
        fund_name=fund.url_name,
        fund_id=fund.id,
        short_names=short_names,
        current_fund=current_fund,
        text_for_document=fund.text_for_document,
        pdy_date=fund.pdy_date,
        datetime=datetime
    )


@admin.route('/funds/<fund_name>/documents/<int:document_id>', methods=['GET', 'POST'])
@login_required
def edit_fund_document(fund_name, document_id):
    # Получаем фонд и документ
    fund = db.session.query(funds).filter_by(url_name=fund_name).first()
    document = fund_document.query.get_or_404(document_id)
    
    if not fund or document.fund_id != fund.id:
        abort(404, description="Документ не найден")
    
    # Получаем все существующие типы документов для select
    existing_types = db.session.query(fund_document.document_type)\
                              .filter_by(fund_id=fund.id)\
                              .distinct().all()
    document_types = [t[0] for t in existing_types] if existing_types else []

    if request.method == 'POST':
        document_name = request.form.get('document_name', '').strip()
        document_type = request.form.get('document_type', '').strip()
        new_document_type = request.form.get('new_document_type', '').strip()
        expiration_date_str = request.form.get('expiration_date')
        file = request.files.get('document_file')
        remove_file = request.form.get('remove_file') == 'on'

        # Валидация
        if not document_type and not new_document_type:
            flash('Тип документа обязателен для заполнения.', 'error')
            return redirect(url_for('admin.edit_fund_document', fund_name=fund_name, document_id=document_id))
            
        if new_document_type:
            document_type = new_document_type.strip()
            if not document_type:
                flash('Новый тип документа не может быть пустым.', 'error')
                return redirect(url_for('admin.edit_fund_document', fund_name=fund_name, document_id=document_id))

        if not document_name:
            flash('Название документа обязательно.', 'error')
            return redirect(url_for('admin.edit_fund_document', fund_name=fund_name, document_id=document_id))

        # Обработка даты
        expiration_date_obj = None
        if expiration_date_str:
            try:
                expiration_date_obj = datetime.strptime(expiration_date_str, '%Y-%m-%d')
            except ValueError:
                flash('Неверный формат даты. Используйте формат ГГГГ-ММ-ДД', 'error')
                return redirect(url_for('admin.edit_fund_document', fund_name=fund_name, document_id=document_id))

        # Обработка файла
        if remove_file and document.url:
            try:
                filename = document.url.split('/')[-1]
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                if os.path.exists(file_path):
                    os.remove(file_path)
                document.url = None
            except Exception as e:
                current_app.logger.error(f'Ошибка удаления файла: {str(e)}')
                flash('Ошибка при удалении файла', 'error')

        if file and file.filename != '':
            if not allowed_file(file.filename):
                flash('Разрешены только PDF-файлы.', 'error')
                return redirect(url_for('admin.edit_fund_document', fund_name=fund_name, document_id=document_id))

            # Проверка размера файла
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            if file_size > current_app.config['MAX_CONTENT_LENGTH']:
                flash(f"Файл слишком большой. Максимальный размер: {current_app.config['MAX_CONTENT_LENGTH'] / (1024*1024):.0f} МБ.", 'error')
                return redirect(url_for('admin.edit_fund_document', fund_name=fund_name, document_id=document_id))

            # Удаляем старый файл если есть
            if document.url:
                try:
                    old_filename = document.url.split('/')[-1]
                    old_file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], old_filename)
                    if os.path.exists(old_file_path):
                        os.remove(old_file_path)
                except Exception as e:
                    current_app.logger.error(f'Ошибка удаления старого файла: {str(e)}')

            # Сохраняем новый файл
            try:
                unique_filename = str(uuid.uuid4()) + '.pdf'
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(file_path)
                document.url = url_for('static', filename='documents/funds/' + unique_filename, _external=True)
            except Exception as e:
                current_app.logger.error(f'Ошибка загрузки файла: {str(e)}')
                flash('Ошибка при загрузке файла', 'error')
                return redirect(url_for('admin.edit_fund_document', fund_name=fund_name, document_id=document_id))

        # Обновляем документ
        try:
            document.name = document_name
            document.document_type = document_type
            document.expiration_date = expiration_date_obj
            
            db.session.commit()
            flash('Документ успешно обновлен!', 'success')
            return redirect(url_for('admin.handle_documents', fund_name=fund_name))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Ошибка обновления документа: {str(e)}')
            flash('Ошибка при обновлении документа', 'error')

    return render_template('admin/edit_fund_document.html', 
                         document=document,
                         document_types=document_types,
                         fund_name=fund_name,
                         fund=fund)


@admin.route('/funds/<fund_name>/documents/<int:document_id>/delete', methods=['POST'])
@login_required
def delete_fund_document(fund_name, document_id):
    # Получаем фонд и документ
    fund = db.session.query(funds).filter_by(url_name=fund_name).first()
    document = fund_document.query.get_or_404(document_id)
    
    if not fund or document.fund_id != fund.id:
        abort(404, description="Документ не найден")
    
    try:
        # Удаляем файл с диска
        if document.url:
            filename = document.url.split('/')[-1]
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        
        # Удаляем запись из БД
        db.session.delete(document)
        db.session.commit()
        
        flash('Документ успешно удален!', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Ошибка удаления документа: {str(e)}')
        flash('Ошибка при удалении документа', 'error')
    
    return redirect(url_for('admin.handle_documents', fund_name=fund_name))


@admin.route('/documents')
@login_required
def documents():
    return render_template('admin/documents.html')


@admin.route('/documents/reports', methods=['GET', 'POST'])
@login_required
def documents_admin():
    if request.method == 'POST':
        document_name = request.form.get('document_name', '').strip()
        expiration_date_str = request.form.get('expiration_date')

        # Validate document name
        if not document_name:
            flash('Название документа обязательно.', 'error')
            return redirect(url_for('admin.documents_admin'))

        # Validate expiration date if provided
        expiration_date_obj = None
        if expiration_date_str:
            try:
                expiration_date_obj = datetime.strptime(expiration_date_str, '%Y-%m-%d')
                # Check that date is not in the past
                if expiration_date_obj.date() < datetime.utcnow().date():
                    flash('Дата окончания не может быть в прошлом.', 'error')
                    return redirect(url_for('admin.documents_admin'))
            except ValueError:
                flash('Неверный формат даты. Используйте формат ГГГГ-ММ-ДД', 'error')
                return redirect(url_for('admin.documents_admin'))

        # Validate file
        if 'document_file' not in request.files:
            flash('Файл не выбран.', 'error')
            return redirect(url_for('admin.documents_admin'))

        file = request.files['document_file']

        if file.filename == '':
            flash('Файл не выбран.', 'error')
            return redirect(url_for('admin.documents_admin'))

        if not allowed_file(file.filename):
            flash('Разрешены только PDF-файлы.', 'error')
            return redirect(url_for('admin.documents_admin'))

        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)

        if file_size > current_app.config['MAX_CONTENT_LENGTH']:
            flash(f"Файл слишком большой. Максимальный размер: {current_app.config['MAX_CONTENT_LENGTH'] / (1024*1024):.0f} МБ.", 'error')
            return redirect(url_for('admin.documents_admin'))

        try:
            # Generate unique filename and save file
            unique_filename = str(uuid.uuid4()) + '.pdf'
            file_path = os.path.join(current_app.config['REPORTS_UPLOAD_FOLDER'], unique_filename)
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            file.save(file_path)

            document_url = url_for('static', filename='documents/reports/' + unique_filename, _external=True)

            # Set Moscow time for upload date
            moscow_tz = pytz.timezone('Europe/Moscow')
            upload_date = datetime.now(moscow_tz)

            new_document = report_document(
                name=document_name,
                url=document_url,
                expiration_date=expiration_date_obj,
                upload_date=upload_date
            )
            
            db.session.add(new_document)
            db.session.commit()

            flash('Документ успешно добавлен!', 'success')
            return redirect(url_for('admin.documents_admin'))

        except Exception as e:
            db.session.rollback()
            if 'file_path' in locals() and os.path.exists(file_path):
                os.remove(file_path)
            current_app.logger.error(f'Error uploading document: {str(e)}')
            flash('Произошла ошибка при загрузке файла. Пожалуйста, попробуйте позже.', 'error')
            return redirect(url_for('admin.documents_admin'))

    # Handle GET request - show documents with date filtering
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    query = report_document.query
    
    try:
        if date_from:
            date_from = datetime.strptime(date_from, '%Y-%m-%d')
            # Convert to Moscow time for comparison
            moscow_tz = pytz.timezone('Europe/Moscow')
            date_from = moscow_tz.localize(date_from)
            query = query.filter(report_document.upload_date >= date_from)
        
        if date_to:
            date_to = datetime.strptime(date_to, '%Y-%m-%d')
            # Convert to Moscow time and set to end of day
            moscow_tz = pytz.timezone('Europe/Moscow')
            date_to = moscow_tz.localize(date_to.replace(hour=23, minute=59, second=59))
            query = query.filter(report_document.upload_date <= date_to)
    except ValueError:
        flash('Неверный формат даты', 'error')
    
    # Get documents and convert times to Moscow time for display
    documents = query.order_by(report_document.upload_date.desc()).all()
    moscow_tz = pytz.timezone('Europe/Moscow')
    for doc in documents:
        if doc.upload_date:
            doc.upload_date = doc.upload_date.astimezone(moscow_tz)
    
    return render_template(
        'admin/uk_documents.html', 
        documents=documents,
        current_date=datetime.now(pytz.timezone('Europe/Moscow')).date(),
        datetime=datetime
    )


@admin.route('/documents/regulations', methods=['GET', 'POST'])
@login_required
def regulations_document_admin():
    if request.method == 'POST':
        document_name = request.form.get('document_name', '').strip()
        date_act_from_str = request.form.get('date_act_from')
        date_act_to_str = request.form.get('date_act_to')  

        # Validate document name
        if not document_name:
            flash('Название документа обязательно.', 'error')
            return redirect(url_for('admin.regulations_document_admin'))

        # Validate expiration date if provided
        date_act_from_obj = None
        if date_act_from_str:
            try:
                date_act_from_obj = datetime.strptime(date_act_from_str, '%Y-%m-%d')
            except ValueError:
                flash('Неверный формат даты. Используйте формат ГГГГ-ММ-ДД', 'error')
                return redirect(url_for('admin.regulations_document_admin'))

        # Validate date_act_to if provided
        date_act_to_obj = None  
        if date_act_to_str:
            try:
                date_act_to_obj = datetime.strptime(date_act_to_str, '%Y-%m-%d')
            except ValueError:
                flash('Неверный формат даты. Используйте формат ГГГГ-ММ-ДД', 'error')
                return redirect(url_for('admin.regulations_document_admin'))

        # Validate file
        if 'document_file' not in request.files:
            flash('Файл не выбран.', 'error')
            return redirect(url_for('admin.regulations_document_admin'))

        file = request.files['document_file']

        if file.filename == '':
            flash('Файл не выбран.', 'error')
            return redirect(url_for('admin.regulations_document_admin'))

        if not allowed_file(file.filename):
            flash('Разрешены только PDF-файлы.', 'error')
            return redirect(url_for('admin.regulations_document_admin'))

        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)

        if file_size > current_app.config['MAX_CONTENT_LENGTH']:
            flash(f"Файл слишком большой. Максимальный размер: {current_app.config['MAX_CONTENT_LENGTH'] / (1024*1024):.0f} МБ.", 'error')
            return redirect(url_for('admin.regulations_document_admin'))

        try:
            # Generate unique filename and save file
            unique_filename = str(uuid.uuid4()) + '.pdf'
            file_path = os.path.join(current_app.config['REGULATIONS_UPLOAD_FOLDER'], unique_filename)
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            file.save(file_path)

            document_url = url_for('static', filename='documents/regulations/' + unique_filename, _external=True)

            # Set Moscow time for upload date
            moscow_tz = pytz.timezone('Europe/Moscow')
            upload_date = datetime.now(moscow_tz)

            new_document = regulations_document(
                name=document_name,
                url=document_url,
                date_act_from=date_act_from_obj,
                date_act_to=date_act_to_obj,  
                upload_date=upload_date
            )
            
            db.session.add(new_document)
            db.session.commit()

            flash('Документ успешно добавлен!', 'success')
            return redirect(url_for('admin.regulations_document_admin'))

        except Exception as e:
            db.session.rollback()
            if 'file_path' in locals() and os.path.exists(file_path):
                os.remove(file_path)
            current_app.logger.error(f'Error uploading document: {str(e)}')
            flash('Произошла ошибка при загрузке файла. Пожалуйста, попробуйте позже.', 'error')
            return redirect(url_for('admin.regulations_document_admin'))

    # Handle GET request - show documents with date filtering
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    query = regulations_document.query
    
    try:
        if date_from:
            date_from = datetime.strptime(date_from, '%Y-%m-%d')
            # Convert to Moscow time for comparison
            moscow_tz = pytz.timezone('Europe/Moscow')
            date_from = moscow_tz.localize(date_from)
            query = query.filter(regulations_document.upload_date >= date_from)
        
        if date_to:
            date_to = datetime.strptime(date_to, '%Y-%m-%d')
            # Convert to Moscow time and set to end of day
            moscow_tz = pytz.timezone('Europe/Moscow')
            date_to = moscow_tz.localize(date_to.replace(hour=23, minute=59, second=59))
            query = query.filter(regulations_document.upload_date <= date_to)
    except ValueError:
        flash('Неверный формат даты', 'error')
    
    # Get documents and convert times to Moscow time for display
    documents = query.order_by(regulations_document.upload_date.desc()).all()
    moscow_tz = pytz.timezone('Europe/Moscow')
    for doc in documents:
        if doc.upload_date:
            doc.upload_date = doc.upload_date.astimezone(moscow_tz)
    
    return render_template(
        'admin/regulations_documents.html', 
        documents=documents,
        current_date=datetime.now(pytz.timezone('Europe/Moscow')).date()
    )


@admin.route('/documents/inform_messages', methods=['GET', 'POST'])
@login_required
def inform_messages_admin():
    if request.method == 'POST':
        message_name = request.form.get('message_name', '').strip()
        document_title = request.form.get('document_title', '').strip()  # Новое поле
        inform_text = request.form.get('inform_text', '').strip()
        file = request.files.get('message_file')

        # Проверка на заполнение хотя бы одного поля
        if not message_name and not document_title and not inform_text and (not file or file.filename == ''):
            flash('Заполните хотя бы одно поле: название, заголовок, текст или загрузите файл', 'error')
            return redirect(url_for('admin.inform_messages_admin'))

        # Обработка файла (остается без изменений)
        file_url = None
        if file and file.filename != '':
            if not file.filename.lower().endswith('.pdf'):
                flash('Разрешены только PDF-файлы', 'error')
                return redirect(url_for('admin.inform_messages_admin'))

            try:
                unique_filename = str(uuid.uuid4()) + '.pdf'
                file_path = os.path.join(current_app.config['INFORM_MESSAGES_UPLOAD_FOLDER'], unique_filename)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                file.save(file_path)
                file_url = url_for('static', filename='documents/inform_messages/' + unique_filename, _external=True)
            except Exception as e:
                current_app.logger.error(f'Ошибка загрузки файла: {str(e)}')
                flash('Ошибка при загрузке файла', 'error')
                return redirect(url_for('admin.inform_messages_admin'))

        # Сохранение в базу с новым полем
        try:
            new_message = inform_message(
                name=message_name if message_name else "Информационное сообщение",
                document_title=document_title if document_title else None,  # Новое поле
                inform_text=inform_text if inform_text else None,
                url=file_url,
                upload_date=datetime.now()
            )
            
            db.session.add(new_message)
            db.session.commit()
            flash('Сообщение успешно добавлено!', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Ошибка сохранения в базу: {str(e)}')
            flash('Ошибка при сохранении сообщения', 'error')

        return redirect(url_for('admin.inform_messages_admin'))

    # GET запрос - показать список сообщений
    messages = inform_message.query.order_by(inform_message.upload_date.desc()).all()
    return render_template('admin/inform_messages.html', messages=messages)


@admin.route('/documents/inform_messages/<int:message_id>', methods=['GET', 'POST'])
@login_required
def edit_inform_message(message_id):
    message = inform_message.query.get_or_404(message_id)

    if request.method == 'POST':
        message_name = request.form.get('message_name', '').strip()
        document_title = request.form.get('document_title', '').strip()  # Новое поле
        inform_text = request.form.get('inform_text', '').strip()
        file = request.files.get('message_file')
        remove_file = request.form.get('remove_file') == 'on'

        # Проверка заполнения полей с учетом нового поля
        if not message_name and not document_title and not inform_text and not message.url and (not file or file.filename == ''):
            flash('Заполните хотя бы одно поле: название, заголовок, текст или загрузите файл', 'error')
            return redirect(url_for('admin.edit_inform_message', message_id=message.id))

        # Обработка файла (остается без изменений)
        if remove_file and message.url:
            try:
                file_path = os.path.join(current_app.config['INFORM_MESSAGES_UPLOAD_FOLDER'], 
                                      os.path.basename(message.url))
                if os.path.exists(file_path):
                    os.remove(file_path)
                message.url = None
            except Exception as e:
                current_app.logger.error(f'Ошибка удаления файла: {str(e)}')
                flash('Ошибка при удалении файла', 'error')

        if file and file.filename != '':
            if not file.filename.lower().endswith('.pdf'):
                flash('Разрешены только PDF-файлы', 'error')
                return redirect(url_for('admin.edit_inform_message', message_id=message.id))

            try:
                # Удаляем старый файл если есть
                if message.url:
                    old_file_path = os.path.join(current_app.config['INFORM_MESSAGES_UPLOAD_FOLDER'], 
                                             os.path.basename(message.url))
                    if os.path.exists(old_file_path):
                        os.remove(old_file_path)

                # Сохраняем новый файл
                unique_filename = str(uuid.uuid4()) + '.pdf'
                file_path = os.path.join(current_app.config['INFORM_MESSAGES_UPLOAD_FOLDER'], unique_filename)
                file.save(file_path)
                message.url = url_for('static', filename='documents/inform_messages/' + unique_filename, _external=True)
            except Exception as e:
                current_app.logger.error(f'Ошибка загрузки файла: {str(e)}')
                flash('Ошибка при загрузке файла', 'error')
                return redirect(url_for('admin.edit_inform_message', message_id=message.id))

        # Обновление данных с новым полем
        try:
            message.name = message_name if message_name else "Информационное сообщение"
            message.document_title = document_title if document_title else None  # Новое поле
            message.inform_text = inform_text if inform_text else None

            db.session.commit()
            flash('Сообщение успешно обновлено!', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Ошибка обновления: {str(e)}')
            flash('Ошибка при обновлении сообщения', 'error')

        return redirect(url_for('admin.inform_messages_admin'))  # Перенаправляем на список сообщений

    return render_template('admin/edit_inform_message.html', message=message)


@admin.route('/documents/inform_messages/<int:message_id>/delete', methods=['POST'])
@login_required
def delete_inform_message(message_id):
    message = inform_message.query.get_or_404(message_id)
    
    try:
        if message.url:
            file_path = os.path.join(current_app.config['INFORM_MESSAGES_UPLOAD_FOLDER'], 
                                  os.path.basename(message.url))
            if os.path.exists(file_path):
                os.remove(file_path)
        
        db.session.delete(message)
        db.session.commit()
        flash('Сообщение успешно удалено!', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Ошибка удаления: {str(e)}')
        flash('Ошибка при удалении сообщения', 'error')
    
    return redirect(url_for('admin.inform_messages_admin'))


@admin.route('/news')
@login_required
def news_admin():
    # Получаем все новости, отсортированные по дате публикации (новые сначала)
    all_news = news.query.order_by(news.publish_date.desc()).all()
    
    # Конвертируем время в московское для отображения
    moscow_tz = pytz.timezone('Europe/Moscow')
    for news_item in all_news:
        if news_item.publish_date:
            # Если время в UTC, конвертируем в Москву
            if news_item.publish_date.tzinfo is None:
                news_item.publish_date = pytz.utc.localize(news_item.publish_date)
            news_item.publish_date_moscow = news_item.publish_date.astimezone(moscow_tz)
    
    return render_template('admin/news_admin.html', news_list=all_news)


@admin.route('/news/create', methods=['GET', 'POST'])
@login_required
def create_news():
    if request.method == 'POST':
        try:
            # Получаем основные данные
            news_date_str = request.form.get('news_date')
            if not news_date_str:
                flash('Дата новости обязательна', 'error')
                return render_template('admin/create_news.html', current_date=datetime.now().strftime('%Y-%m-%d'))
            
            news_date = datetime.strptime(news_date_str, '%Y-%m-%d').date()
            title = request.form.get('title', '').strip()
            
            if not title:
                flash('Заголовок обязателен', 'error')
                return render_template('admin/create_news.html', current_date=datetime.now().strftime('%Y-%m-%d'))
            
            # Обработка обложки
            cover_image = None
            cover_mimetype = None
            cover_file = request.files.get('cover_image')
            
            if cover_file and cover_file.filename != '':
                cover_image = cover_file.read()
                cover_mimetype = cover_file.mimetype
            else:
                flash('Обложка обязательна', 'error')
                return render_template('admin/create_news.html', current_date=datetime.now().strftime('%Y-%m-%d'))
            
            # Создаем основную запись новости с UTC временем
            new_news = news(
                news_date=news_date,
                title=title,
                cover_image=cover_image,
                cover_mimetype=cover_mimetype,
                publish_date=datetime.utcnow()  # Сохраняем в UTC
            )
            
            db.session.add(new_news)
            db.session.flush()  # Получаем ID новости
            
            # Обработка блоков контента
            block_count = int(request.form.get('block_count', 1))
            
            for i in range(block_count):
                block_type = request.form.get(f'block_{i}_type')
                
                if block_type == 'text':
                    text_content = request.form.get(f'block_{i}_text', '').strip()
                    if text_content:
                        block = news_block(
                            news_id=new_news.id,
                            block_type='text',
                            content=text_content,
                            order_index=i
                        )
                        db.session.add(block)
                
                elif block_type == 'image':
                    image_file = request.files.get(f'block_{i}_image')
                    if image_file and image_file.filename != '':
                        # Сохраняем бинарные данные в отдельное поле
                        image_data = image_file.read()
                        block = news_block(
                            news_id=new_news.id,
                            block_type='image',
                            content=image_file.filename,
                            image_data=image_data,
                            mimetype=image_file.mimetype,
                            order_index=i
                        )
                        db.session.add(block)
                    else:
                        flash(f'Изображение в блоке {i+1} обязательно', 'error')
                        db.session.rollback()
                        return render_template('admin/create_news.html', current_date=datetime.now().strftime('%Y-%m-%d'))
            
            # Сохраняем все изменения
            db.session.commit()
            
            flash('Новость успешно создана!', 'success')
            return redirect(url_for('admin.news_admin'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при создании новости: {str(e)}', 'error')
            return render_template('admin/create_news.html', current_date=datetime.now().strftime('%Y-%m-%d'))
    
    # GET запрос - показываем форму
    current_date = datetime.now().strftime('%Y-%m-%d')
    return render_template('admin/create_news.html', current_date=current_date)


@admin.route('/news/<int:news_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_news(news_id):
    news_item = news.query.get_or_404(news_id)
    
    if request.method == 'POST':
        try:
            # Получаем основные данные
            news_date_str = request.form.get('news_date')
            if not news_date_str:
                flash('Дата новости обязательна', 'error')
                return redirect(url_for('admin.edit_news', news_id=news_id))
            
            news_item.news_date = datetime.strptime(news_date_str, '%Y-%m-%d').date()
            news_item.title = request.form.get('title', '').strip()
            
            if not news_item.title:
                flash('Заголовок обязателен', 'error')
                return redirect(url_for('admin.edit_news', news_id=news_id))
            
            # Обработка обложки (если загружена новая)
            cover_file = request.files.get('cover_image')
            if cover_file and cover_file.filename:
                news_item.cover_image = cover_file.read()
                news_item.cover_mimetype = cover_file.mimetype
            
            # НЕ УДАЛЯЕМ СТАРЫЕ БЛОКИ - сохраняем существующие данные
            # Получаем текущие блоки для сохранения изображений
            existing_blocks = {block.id: block for block in news_item.blocks}
            
            # Обработка блоков контента
            block_count = int(request.form.get('block_count', 1))
            
            # Собираем ID блоков, которые остаются после редактирования
            remaining_block_ids = set()
            
            for i in range(block_count):
                block_type = request.form.get(f'block_{i}_type')
                block_id = request.form.get(f'block_{i}_id', '')
                
                if block_type == 'text':
                    text_content = request.form.get(f'block_{i}_text', '').strip()
                    if text_content:
                        if block_id and block_id.isdigit() and int(block_id) in existing_blocks:
                            # Обновляем существующий текстовый блок
                            existing_block = existing_blocks[int(block_id)]
                            existing_block.content = text_content
                            existing_block.order_index = i
                            remaining_block_ids.add(existing_block.id)
                        else:
                            # Создаем новый текстовый блок
                            block = news_block(
                                news_id=news_item.id,
                                block_type='text',
                                content=text_content,
                                order_index=i
                            )
                            db.session.add(block)
                
                elif block_type == 'image':
                    image_file = request.files.get(f'block_{i}_image')
                    
                    if block_id and block_id.isdigit() and int(block_id) in existing_blocks:
                        # Существующий блок с изображением
                        existing_block = existing_blocks[int(block_id)]
                        
                        if image_file and image_file.filename:
                            # Обновляем изображение
                            existing_block.image_data = image_file.read()
                            existing_block.mimetype = image_file.mimetype
                            existing_block.content = image_file.filename
                        # Если файл не выбран - сохраняем старое изображение (ничего не делаем)
                        
                        existing_block.order_index = i
                        remaining_block_ids.add(existing_block.id)
                    
                    else:
                        # Новый блок с изображением
                        if image_file and image_file.filename:
                            block = news_block(
                                news_id=news_item.id,
                                block_type='image',
                                content=image_file.filename,
                                image_data=image_file.read(),
                                mimetype=image_file.mimetype,
                                order_index=i
                            )
                            db.session.add(block)
            
            # Удаляем только те блоки, которые были удалены в форме
            for block_id, block in existing_blocks.items():
                if block_id not in remaining_block_ids:
                    db.session.delete(block)
            
            db.session.commit()
            flash('Новость успешно обновлена!', 'success')
            return redirect(url_for('admin.news_admin'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Error editing news {news_id}: {str(e)}')
            flash(f'Ошибка при обновлении новости: {str(e)}', 'error')
    
    # GET запрос - показываем форму редактирования
    moscow_tz = pytz.timezone('Europe/Moscow')
    if news_item.publish_date:
        if news_item.publish_date.tzinfo is None:
            news_item.publish_date = pytz.utc.localize(news_item.publish_date)
        news_item.publish_date_moscow = news_item.publish_date.astimezone(moscow_tz)
    
    # Подготавливаем данные для формы
    blocks_data = []
    for i, block in enumerate(news_item.blocks):
        block_data = {
            'id': block.id,  # ВАЖНО: передаем ID блока
            'type': block.block_type,
            'content': block.content,
            'order': i
        }
        if block.block_type == 'image':
            block_data['mimetype'] = block.mimetype
            block_data['image_data'] = block.image_data
        blocks_data.append(block_data)
    
    return render_template('admin/edit_news.html', 
                         news=news_item, 
                         blocks_data=blocks_data,
                         current_date=news_item.news_date.strftime('%Y-%m-%d'))


@admin.route('/news/<int:news_id>/delete')
@login_required
def delete_news(news_id):
    try:
        news_item = news.query.get_or_404(news_id)
        news_title = news_item.title
        
        # Удаляем связанные блоки
        news_block.query.filter_by(news_id=news_id).delete()
        
        # Удаляем саму новость
        db.session.delete(news_item)
        db.session.commit()
        
        flash(f'Новость «{news_title}» успешно удалена', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error deleting news {news_id}: {str(e)}')
        flash(f'Ошибка при удалении новости: {str(e)}', 'error')
    
    return redirect(url_for('admin.news_admin'))


@admin.route('/analytics')
@login_required
def analytics_admin():
    # Получаем все аналитики, отсортированные по дате публикации (новые сначала)
    all_analytics = analytics.query.order_by(analytics.publish_date.desc()).all()
    
    # Конвертируем время в московское для отображения
    moscow_tz = pytz.timezone('Europe/Moscow')
    for analytics_item in all_analytics:
        if analytics_item.publish_date:
            # Если время в UTC, конвертируем в Москву
            if analytics_item.publish_date.tzinfo is None:
                analytics_item.publish_date = pytz.utc.localize(analytics_item.publish_date)
            analytics_item.publish_date_moscow = analytics_item.publish_date.astimezone(moscow_tz)
    
    return render_template('admin/analytics_admin.html', analytics_list=all_analytics)


@admin.route('/analytics/create', methods=['GET', 'POST'])
@login_required
def create_analytics():
    if request.method == 'POST':
        try:
            # Получаем основные данные
            analytics_date_str = request.form.get('analytics_date')
            if not analytics_date_str:
                flash('Дата аналитики обязательна', 'error')
                return render_template('admin/create_analytics.html', current_date=datetime.now().strftime('%Y-%m-%d'))
            
            analytics_date = datetime.strptime(analytics_date_str, '%Y-%m-%d').date()
            title = request.form.get('title', '').strip()
            
            if not title:
                flash('Заголовок обязателен', 'error')
                return render_template('admin/create_analytics.html', current_date=datetime.now().strftime('%Y-%m-%d'))
            
            # Обработка обложки
            cover_image = None
            cover_mimetype = None
            cover_file = request.files.get('cover_image')
            
            if cover_file and cover_file.filename != '':
                cover_image = cover_file.read()
                cover_mimetype = cover_file.mimetype
            else:
                flash('Обложка обязательна', 'error')
                return render_template('admin/create_analytics.html', current_date=datetime.now().strftime('%Y-%m-%d'))
            
            # Создаем основную запись аналитики с UTC временем
            new_analytics = analytics(
                analytics_date=analytics_date,
                title=title,
                cover_image=cover_image,
                cover_mimetype=cover_mimetype,
                publish_date=datetime.utcnow()  # Сохраняем в UTC
            )
            
            db.session.add(new_analytics)
            db.session.flush()  # Получаем ID аналитики
            
            # Обработка блоков контента
            block_count = int(request.form.get('block_count', 1))
            
            for i in range(block_count):
                block_type = request.form.get(f'block_{i}_type')
                
                if block_type == 'text':
                    text_content = request.form.get(f'block_{i}_text', '').strip()
                    if text_content:
                        block = analytics_block(
                            analytics_id=new_analytics.id,
                            block_type='text',
                            content=text_content,
                            order_index=i
                        )
                        db.session.add(block)
                
                elif block_type == 'image':
                    image_file = request.files.get(f'block_{i}_image')
                    if image_file and image_file.filename != '':
                        # Сохраняем бинарные данные в отдельное поле
                        image_data = image_file.read()
                        block = analytics_block(
                            analytics_id=new_analytics.id,
                            block_type='image',
                            content=image_file.filename,
                            image_data=image_data,
                            mimetype=image_file.mimetype,
                            order_index=i
                        )
                        db.session.add(block)
                    else:
                        flash(f'Изображение в блоке {i+1} обязательно', 'error')
                        db.session.rollback()
                        return render_template('admin/create_analytics.html', current_date=datetime.now().strftime('%Y-%m-%d'))
            
            # Сохраняем все изменения
            db.session.commit()
            
            flash('Аналитика успешно создана!', 'success')
            return redirect(url_for('admin.analytics_admin'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при создании аналитики: {str(e)}', 'error')
            return render_template('admin/create_analytics.html', current_date=datetime.now().strftime('%Y-%m-%d'))
    
    # GET запрос - показываем форму
    current_date = datetime.now().strftime('%Y-%m-%d')
    return render_template('admin/create_analytics.html', current_date=current_date)


@admin.route('/analytics/<int:analytics_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_analytics(analytics_id):
    analytics_item = analytics.query.get_or_404(analytics_id)
    
    if request.method == 'POST':
        try:
            # Получаем основные данные
            analytics_date_str = request.form.get('analytics_date')
            if not analytics_date_str:
                flash('Дата аналитики обязательна', 'error')
                return redirect(url_for('admin.edit_analytics', analytics_id=analytics_id))
            
            analytics_item.analytics_date = datetime.strptime(analytics_date_str, '%Y-%m-%d').date()
            analytics_item.title = request.form.get('title', '').strip()
            
            if not analytics_item.title:
                flash('Заголовок обязателен', 'error')
                return redirect(url_for('admin.edit_analytics', analytics_id=analytics_id))
            
            # Обработка обложки (если загружена новая)
            cover_file = request.files.get('cover_image')
            if cover_file and cover_file.filename:
                analytics_item.cover_image = cover_file.read()
                analytics_item.cover_mimetype = cover_file.mimetype
            
            # НЕ УДАЛЯЕМ СТАРЫЕ БЛОКИ - сохраняем существующие данные
            # Получаем текущие блоки для сохранения изображений
            existing_blocks = {block.id: block for block in analytics_item.blocks}
            
            # Обработка блоков контента
            block_count = int(request.form.get('block_count', 1))
            
            # Собираем ID блоков, которые остаются после редактирования
            remaining_block_ids = set()
            
            for i in range(block_count):
                block_type = request.form.get(f'block_{i}_type')
                block_id = request.form.get(f'block_{i}_id', '')
                
                if block_type == 'text':
                    text_content = request.form.get(f'block_{i}_text', '').strip()
                    if text_content:
                        if block_id and block_id.isdigit() and int(block_id) in existing_blocks:
                            # Обновляем существующий текстовый блок
                            existing_block = existing_blocks[int(block_id)]
                            existing_block.content = text_content
                            existing_block.order_index = i
                            remaining_block_ids.add(existing_block.id)
                        else:
                            # Создаем новый текстовый блок
                            block = analytics_block(
                                analytics_id=analytics_item.id,
                                block_type='text',
                                content=text_content,
                                order_index=i
                            )
                            db.session.add(block)
                
                elif block_type == 'image':
                    image_file = request.files.get(f'block_{i}_image')
                    
                    if block_id and block_id.isdigit() and int(block_id) in existing_blocks:
                        # Существующий блок с изображением
                        existing_block = existing_blocks[int(block_id)]
                        
                        if image_file and image_file.filename:
                            # Обновляем изображение
                            existing_block.image_data = image_file.read()
                            existing_block.mimetype = image_file.mimetype
                            existing_block.content = image_file.filename
                        # Если файл не выбран - сохраняем старое изображение (ничего не делаем)
                        
                        existing_block.order_index = i
                        remaining_block_ids.add(existing_block.id)
                    
                    else:
                        # Новый блок с изображением
                        if image_file and image_file.filename:
                            block = analytics_block(
                                analytics_id=analytics_item.id,
                                block_type='image',
                                content=image_file.filename,
                                image_data=image_file.read(),
                                mimetype=image_file.mimetype,
                                order_index=i
                            )
                            db.session.add(block)
            
            # Удаляем только те блоки, которые были удалены в форме
            for block_id, block in existing_blocks.items():
                if block_id not in remaining_block_ids:
                    db.session.delete(block)
            
            db.session.commit()
            flash('Аналитика успешно обновлена!', 'success')
            return redirect(url_for('admin.analytics_admin'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Error editing analytics {analytics_id}: {str(e)}')
            flash(f'Ошибка при обновлении аналитики: {str(e)}', 'error')
    
    # GET запрос - показываем форму редактирования
    moscow_tz = pytz.timezone('Europe/Moscow')
    if analytics_item.publish_date:
        if analytics_item.publish_date.tzinfo is None:
            analytics_item.publish_date = pytz.utc.localize(analytics_item.publish_date)
        analytics_item.publish_date_moscow = analytics_item.publish_date.astimezone(moscow_tz)
    
    # Подготавливаем данные для формы
    blocks_data = []
    for i, block in enumerate(analytics_item.blocks):
        block_data = {
            'id': block.id,  # ВАЖНО: передаем ID блока
            'type': block.block_type,
            'content': block.content,
            'order': i
        }
        if block.block_type == 'image':
            block_data['mimetype'] = block.mimetype
            block_data['image_data'] = block.image_data
        blocks_data.append(block_data)
    
    return render_template('admin/edit_analytics.html', 
                         analytics=analytics_item, 
                         blocks_data=blocks_data,
                         current_date=analytics_item.analytics_date.strftime('%Y-%m-%d'))


@admin.route('/analytics/<int:analytics_id>/delete')
@login_required
def delete_analytics(analytics_id):
    try:
        analytics_item = analytics.query.get_or_404(analytics_id)
        analytics_title = analytics_item.title
        
        # Удаляем связанные блоки
        analytics_block.query.filter_by(analytics_id=analytics_id).delete()
        
        # Удаляем саму аналитику
        db.session.delete(analytics_item)
        db.session.commit()
        
        flash(f'Аналитика «{analytics_title}» успешно удалена', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error deleting analytics {analytics_id}: {str(e)}')
        flash(f'Ошибка при удалении аналитики: {str(e)}', 'error')
    
    return redirect(url_for('admin.analytics_admin'))


@admin.route('/events')
@login_required
def events_admin():
    all_events = company_history_event.query.order_by(company_history_event.date.desc()).all()
    return render_template('admin/events_admin.html', events_list=all_events)


@admin.route('/events/create', methods=['GET', 'POST'])
@login_required
def create_event():
    if request.method == 'POST':
        try:
            # Получаем данные из формы
            date_str = request.form.get('date', '').strip()
            title = request.form.get('title', '').strip()
            short_note = request.form.get('short_note', '').strip() or None
            
            # Валидация обязательных полей
            if not date_str or not title:
                flash('Дата и текст события обязательны!', 'error')
                return render_template('admin/event_form.html', event=None)
            
            try:
                # Преобразуем строку даты в объект Date
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Некорректный формат даты. Используйте календарь для выбора.', 'error')
                return render_template('admin/event_form.html', event=None)
            
            # Обработка фото - КАК В ПРИМЕРЕ С НОВОСТЯМИ
            photo_data = None
            photo_mimetype = None
            photo_file = request.files.get('photo')
            
            # Фото необязательное, поэтому только если файл действительно есть
            if photo_file and photo_file.filename != '':
                photo_data = photo_file.read()
                photo_mimetype = photo_file.mimetype
                print(f"DEBUG: Фото загружено - имя: {photo_file.filename}, размер: {len(photo_data)} байт, тип: {photo_mimetype}")
            
            # Создаем событие
            event = company_history_event(
                date=date_obj,
                title=title,
                short_note=short_note,
                photo=photo_data,  # Может быть None
                photo_mimetype=photo_mimetype  # Может быть None
            )
            
            db.session.add(event)
            db.session.commit()
            
            flash('Событие успешно добавлено!', 'success')
            return redirect(url_for('admin.events_admin'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при создании события: {str(e)}', 'error')
    
    return render_template('admin/event_form.html', event=None)


@admin.route('/events/<int:event_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_event(event_id):
    event = company_history_event.query.get_or_404(event_id)
    
    if request.method == 'POST':
        try:
            # Получаем данные из формы
            date_str = request.form.get('date', '').strip()
            event.title = request.form.get('title', '').strip()
            event.short_note = request.form.get('short_note', '').strip() or None
            
            # Валидация
            if not date_str or not event.title:
                flash('Дата и текст события обязательны!', 'error')
                return render_template('admin/event_form.html', event=event)
            
            try:
                # Преобразуем строку даты в объект Date
                event.date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Некорректный формат даты. Используйте календарь для выбора.', 'error')
                return render_template('admin/event_form.html', event=event)
            
            # Обработка удаления фото
            if 'delete_photo' in request.form and request.form['delete_photo'] == 'yes':
                event.photo = None
                event.photo_mimetype = None
                print("DEBUG: Фото удалено по запросу пользователя")
            
            # Обработка нового фото - КАК В ПРИМЕРЕ С НОВОСТЯМИ
            photo_file = request.files.get('photo')
            if photo_file and photo_file.filename != '':
                # Загружаем новое фото
                event.photo = photo_file.read()
                event.photo_mimetype = photo_file.mimetype
                print(f"DEBUG: Новое фото загружено - имя: {photo_file.filename}, размер: {len(event.photo)} байт")
            
            db.session.commit()
            flash('Событие успешно обновлено!', 'success')
            return redirect(url_for('admin.events_admin'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обновлении события: {str(e)}', 'error')
            return render_template('admin/event_form.html', event=event)
    
    return render_template('admin/event_form.html', event=event)
    

@admin.route('/events/<int:event_id>/delete')
@login_required
def delete_event(event_id):
    event = company_history_event.query.get_or_404(event_id)
    
    try:
        db.session.delete(event)
        db.session.commit()
        flash('Событие успешно удалено!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {str(e)}', 'error')
    
    return redirect(url_for('admin.events_admin'))