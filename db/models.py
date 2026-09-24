from . import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

class funds(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True) 
    short_name = db.Column(db.String(100), nullable=False) 
    url_name = db.Column(db.String(50), nullable=False) 
    description = db.Column(db.Text, nullable=False)  
    background_image = db.Column(db.LargeBinary(length=16777215), nullable=False) 
    background_mimetype = db.Column(db.String(50))  
    logo = db.Column(db.LargeBinary(length=16777215), nullable=False) 
    logo_mimetype = db.Column(db.String(50))
    strategy = db.Column(db.Text, nullable=False)  
    additional_info = db.Column(db.Text, nullable=True)
    text_for_document = db.Column(db.Text, nullable=True)
    pdy_date = db.Column(db.Text, nullable=True)
    cards_description = db.Column(db.String(255), nullable=False)
    cards_animation = db.Column(db.Boolean, default=False, nullable=False)
    cards_amount = db.Column(db.Integer, nullable=False)
    cards_period = db.Column(db.Integer, nullable=False)
    is_archived = db.Column(db.Boolean, default=False, nullable=False) 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    footer_description = db.Column(db.Text, nullable=False)
    for_qualified_investors = db.Column(db.Boolean, default=False, nullable=False)
    # Внешние включи
    fund_values = db.relationship('fund_values', backref='fund', lazy=True)
    conditions = db.relationship('fund_conditions', backref='fund', lazy=True, order_by='fund_conditions.order')
    steps = db.relationship('fund_steps', backref='fund', lazy=True, order_by='fund_steps.order')
    manager = db.relationship('fund_manager', backref='fund', lazy=True, uselist=False)
    compositions = db.relationship('fund_composition', backref='fund', lazy=True)

class fund_conditions(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fund_id = db.Column(db.Integer, db.ForeignKey('funds.id'), nullable=False)
    title = db.Column(db.String(100)) 
    description = db.Column(db.String(255))  
    order = db.Column(db.Integer)  

class fund_manager(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fund_id = db.Column(db.Integer, db.ForeignKey('funds.id'), nullable=False)
    name = db.Column(db.String(100)) 
    position = db.Column(db.String(100)) 
    photo = db.Column(db.LargeBinary(length=16777215))  
    photo_mimetype = db.Column(db.String(50))
    comment = db.Column(db.Text)  

class fund_steps(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fund_id = db.Column(db.Integer, db.ForeignKey('funds.id'), nullable=False)
    title = db.Column(db.String(100))  
    description = db.Column(db.String(255)) 
    time_required = db.Column(db.String(50)) 
    order = db.Column(db.Integer)  

class fund_faq(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fund_id = db.Column(db.Integer, db.ForeignKey('funds.id'), nullable=False)
    question = db.Column(db.String(255))  
    answer = db.Column(db.Text)  
    order = db.Column(db.Integer) 

class fund_values(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fund_id = db.Column(db.Integer, db.ForeignKey('funds.id')) 
    date = db.Column(db.Date, nullable=False)
    share_price = db.Column(db.Float)
    benchmark = db.Column(db.Float)
    scha = db.Column(db.Float)
    upload_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('fund_id', 'date', name='fund_date_uc'),)

class fund_composition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fund_id = db.Column(db.Integer, db.ForeignKey('funds.id'))
    date = db.Column(db.Date, nullable=False)
    issuer = db.Column(db.String(255))
    sector = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    share = db.Column(db.Float, nullable=False)
    chart_type = db.Column(db.String(20), nullable=False, default='pie')
    
class fund_document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fund_id = db.Column(db.Integer, db.ForeignKey('funds.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    document_type = db.Column(db.String(100), nullable=False)
    upload_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expiration_date = db.Column(db.DateTime, nullable=True)
    __table_args__ = (db.Index('idx_document_type', 'document_type'),)
    expiration_calculation_type = db.Column(db.String(20), nullable=True)

class report_document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    upload_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expiration_date = db.Column(db.DateTime, nullable=True)

class regulations_document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    upload_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    date_act_from = db.Column(db.DateTime, nullable=True)
    date_act_to = db.Column(db.DateTime, nullable=True)

class inform_message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    inform_text = db.Column(db.Text, nullable=True)
    document_title = db.Column(db.String(255), nullable=True)
    url = db.Column(db.String(500), nullable=True)
    upload_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow) 

class news(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    news_date = db.Column(db.Date, nullable=False) 
    publish_date = db.Column(db.DateTime, default=datetime.utcnow) 
    title = db.Column(db.String(200), nullable=False)
    cover_image = db.Column(db.LargeBinary(length=16777215)) 
    cover_mimetype = db.Column(db.String(50))

class news_block(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    news_id = db.Column(db.Integer, db.ForeignKey('news.id'), nullable=False)
    block_type = db.Column(db.String(20), nullable=False)  
    content = db.Column(db.Text, nullable=False)  
    image_data = db.Column(db.LargeBinary(length=16777215))  
    mimetype = db.Column(db.String(50))  
    order_index = db.Column(db.Integer, nullable=False, default=0)
    news = db.relationship('news', backref=db.backref('blocks', lazy=True, order_by='news_block.order_index'))

class analytics(db.Model):
    __tablename__ = 'analytics'
    id = db.Column(db.Integer, primary_key=True)
    analytics_date = db.Column(db.Date, nullable=False) 
    publish_date = db.Column(db.DateTime, default=datetime.utcnow) 
    title = db.Column(db.String(200), nullable=False)
    cover_image = db.Column(db.LargeBinary(length=16777215))  
    cover_mimetype = db.Column(db.String(50))

class analytics_block(db.Model):
    __tablename__ = 'analytics_block'
    id = db.Column(db.Integer, primary_key=True)
    analytics_id = db.Column(db.Integer, db.ForeignKey('analytics.id'), nullable=False)  
    block_type = db.Column(db.String(20), nullable=False)  
    content = db.Column(db.Text, nullable=False)  
    image_data = db.Column(db.LargeBinary(length=16777215))  
    mimetype = db.Column(db.String(50))  
    order_index = db.Column(db.Integer, nullable=False, default=0)
    analytics = db.relationship('analytics', backref=db.backref('blocks', lazy=True, order_by='analytics_block.order_index'))  

class admin_user(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return str(self.id)

class company_history_event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False) 
    title = db.Column(db.Text, nullable=False)     
    photo = db.Column(db.LargeBinary(length=16777215), nullable=True) 
    photo_mimetype = db.Column(db.String(50), nullable=True)
    short_note = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)