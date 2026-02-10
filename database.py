import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, BigInteger, Text, JSON, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, date, timedelta
import json

if not os.path.exists('data'):
    os.makedirs('data')

Base = declarative_base()

class ChatConfig(Base):
    __tablename__ = 'chat_configs'
    
    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, unique=True)
    chat_title = Column(String(255), nullable=True)
    enabled = Column(Boolean, default=False)
    check_every = Column(Integer, default=10)  # Проверять каждые N сообщений
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SubscriptionChannel(Base):
    __tablename__ = 'subscription_channels'
    
    id = Column(Integer, primary_key=True)
    chat_id = Column(String(100), unique=True)
    title = Column(String(255))
    username = Column(String(255), nullable=True)
    link = Column(String(500))
    button_text = Column(String(100), default="📢 Подписаться на канал")
    is_private = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class UserSubscription(Base):
    __tablename__ = 'user_subscriptions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger)
    username = Column(String(100))
    channel_id = Column(String(100))
    subscribed = Column(Boolean, default=False)
    muted = Column(Boolean, default=False)
    mute_time = Column(DateTime, nullable=True)
    mute_duration = Column(Integer, default=0)
    message_count = Column(Integer, default=0)  # Счетчик сообщений
    last_check = Column(DateTime, default=datetime.utcnow)
    subscription_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class UserMessageCount(Base):
    __tablename__ = 'user_message_counts'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger)
    chat_id = Column(BigInteger)
    message_count = Column(Integer, default=0)
    last_message = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (Index('idx_user_chat', 'user_id', 'chat_id', unique=True),)

class Statistics(Base):
    __tablename__ = 'statistics'
    
    id = Column(Integer, primary_key=True)
    date = Column(DateTime, default=datetime.utcnow)
    chat_id = Column(BigInteger)
    new_subscriptions = Column(Integer, default=0)
    mutes_given = Column(Integer, default=0)
    messages_deleted = Column(Integer, default=0)

class Warning(Base):
    __tablename__ = 'warnings'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger)
    chat_id = Column(BigInteger)
    warnings_count = Column(Integer, default=1)
    last_warning = Column(DateTime, default=datetime.utcnow)
    reason = Column(Text, nullable=True)

class MuteRecord(Base):
    __tablename__ = 'mute_records'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger)
    chat_id = Column(BigInteger)
    muted_by = Column(BigInteger)
    mute_time = Column(DateTime, default=datetime.utcnow)
    unmute_time = Column(DateTime, nullable=True)
    duration_minutes = Column(Integer, default=0)
    reason = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)

class BanRecord(Base):
    __tablename__ = 'ban_records'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger)
    chat_id = Column(BigInteger)
    banned_by = Column(BigInteger)
    ban_time = Column(DateTime, default=datetime.utcnow)
    unban_time = Column(DateTime, nullable=True)
    reason = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)

class Moderator(Base):
    __tablename__ = 'moderators'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True)
    username = Column(String(100))
    added_by = Column(BigInteger)
    added_at = Column(DateTime, default=datetime.utcnow)
    can_ban = Column(Boolean, default=True)
    can_mute = Column(Boolean, default=True)
    can_warn = Column(Boolean, default=True)
    can_delete = Column(Boolean, default=True)

class Database:
    def __init__(self):
        self.engine = create_engine(f'sqlite:///data/bot_database.db', pool_size=20, max_overflow=30)
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
    
    # Настройки чатов
    def get_chat_config(self, chat_id):
        config = self.session.query(ChatConfig).filter_by(chat_id=chat_id).first()
        return config
    
    def add_or_update_chat(self, chat_id, chat_title=None, enabled=True, check_every=10):
        config = self.get_chat_config(chat_id)
        if not config:
            config = ChatConfig(
                chat_id=chat_id, 
                chat_title=chat_title, 
                enabled=enabled,
                check_every=check_every
            )
            self.session.add(config)
        else:
            config.enabled = enabled
            config.check_every = check_every
            if chat_title:
                config.chat_title = chat_title
            config.updated_at = datetime.utcnow()
        self.session.commit()
        return config
    
    def update_chat_settings(self, chat_id, **kwargs):
        config = self.get_chat_config(chat_id)
        if config:
            for key, value in kwargs.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            config.updated_at = datetime.utcnow()
            self.session.commit()
        return config
    
    def enable_chat(self, chat_id, chat_title=None):
        return self.add_or_update_chat(chat_id, chat_title, True)
    
    def disable_chat(self, chat_id):
        config = self.get_chat_config(chat_id)
        if config:
            config.enabled = False
            config.updated_at = datetime.utcnow()
            self.session.commit()
        return config
    
    def is_chat_enabled(self, chat_id):
        config = self.get_chat_config(chat_id)
        return config.enabled if config else False
    
    def get_check_every(self, chat_id):
        config = self.get_chat_config(chat_id)
        return config.check_every if config else 10
    
    def get_all_enabled_chats(self):
        return self.session.query(ChatConfig).filter_by(enabled=True).all()
    
    def get_all_chats(self):
        return self.session.query(ChatConfig).all()
    
    # Каналы для подписки
    def get_subscription_channel(self):
        return self.session.query(SubscriptionChannel).first()
    
    def has_subscription_channel(self):
        return bool(self.get_subscription_channel())
    
    def add_subscription_channel(self, chat_id, title, username, link, button_text="📢 Подписаться на канал"):
        old_channel = self.get_subscription_channel()
        if old_channel:
            self.session.delete(old_channel)
        
        channel = SubscriptionChannel(
            chat_id=chat_id,
            title=title,
            username=username,
            link=link,
            button_text=button_text,
            is_private=not username
        )
        self.session.add(channel)
        self.session.commit()
        return channel
    
    def update_channel_button_text(self, button_text):
        channel = self.get_subscription_channel()
        if channel:
            channel.button_text = button_text
            self.session.commit()
            return channel
        return None
    
    def delete_subscription_channel(self):
        channel = self.get_subscription_channel()
        if channel:
            self.session.delete(channel)
            self.session.commit()
            return True
        return False
    
    # Подписки пользователей с системой проверки
    def increment_message_count(self, user_id, chat_id):
        # Получаем или создаем запись о счетчике сообщений
        msg_count = self.session.query(UserMessageCount).filter_by(
            user_id=user_id,
            chat_id=chat_id
        ).first()
        
        if not msg_count:
            msg_count = UserMessageCount(
                user_id=user_id,
                chat_id=chat_id,
                message_count=1
            )
            self.session.add(msg_count)
        else:
            msg_count.message_count += 1
            msg_count.last_message = datetime.utcnow()
        
        self.session.commit()
        return msg_count.message_count
    
    def should_check_subscription(self, user_id, chat_id):
        config = self.get_chat_config(chat_id)
        if not config or not config.enabled:
            return False
        
        msg_count = self.session.query(UserMessageCount).filter_by(
            user_id=user_id,
            chat_id=chat_id
        ).first()
        
        if not msg_count:
            return True  # Первое сообщение - проверить
        
        # Проверяем каждые N сообщений
        if config.check_every == 0:
            return False  # Только первое сообщение
        elif config.check_every == 1:
            return True  # Каждое сообщение
        else:
            return msg_count.message_count % config.check_every == 0
    
    def reset_message_count(self, user_id, chat_id):
        msg_count = self.session.query(UserMessageCount).filter_by(
            user_id=user_id,
            chat_id=chat_id
        ).first()
        
        if msg_count:
            msg_count.message_count = 0
            self.session.commit()
    
    def update_user_subscription(self, user_id, username, subscribed=False):
        channel = self.get_subscription_channel()
        if not channel:
            return None
        
        user = self.session.query(UserSubscription).filter_by(
            user_id=user_id, 
            channel_id=channel.chat_id
        ).first()
        
        if not user:
            user = UserSubscription(
                user_id=user_id,
                username=username,
                channel_id=channel.chat_id,
                subscribed=subscribed,
                muted=not subscribed,
                last_check=datetime.utcnow()
            )
            self.session.add(user)
        else:
            user.subscribed = subscribed
            user.username = username
            user.muted = not subscribed
            user.last_check = datetime.utcnow()
            if subscribed:
                user.subscription_time = datetime.utcnow()
                user.mute_time = None
            else:
                user.mute_time = datetime.utcnow()
        
        self.session.commit()
        return user
    
    def is_user_subscribed(self, user_id):
        channel = self.get_subscription_channel()
        if not channel:
            return True
        
        user = self.session.query(UserSubscription).filter_by(
            user_id=user_id, 
            channel_id=channel.chat_id
        ).first()
        
        return user.subscribed if user else False
    
    def get_today_subscriptions(self):
        today = datetime.utcnow().date()
        start_of_day = datetime.combine(today, datetime.min.time())
        
        channel = self.get_subscription_channel()
        if not channel:
            return 0
        
        return self.session.query(UserSubscription).filter(
            UserSubscription.channel_id == channel.chat_id,
            UserSubscription.subscription_time >= start_of_day,
            UserSubscription.subscribed == True
        ).count()
    
    # Модераторы
    def add_moderator(self, user_id, username, added_by, can_ban=True, can_mute=True, can_warn=True, can_delete=True):
        moderator = Moderator(
            user_id=user_id,
            username=username,
            added_by=added_by,
            can_ban=can_ban,
            can_mute=can_mute,
            can_warn=can_warn,
            can_delete=can_delete
        )
        self.session.add(moderator)
        self.session.commit()
        return moderator
    
    def remove_moderator(self, user_id):
        moderator = self.session.query(Moderator).filter_by(user_id=user_id).first()
        if moderator:
            self.session.delete(moderator)
            self.session.commit()
            return True
        return False
    
    def get_moderator(self, user_id):
        return self.session.query(Moderator).filter_by(user_id=user_id).first()
    
    def is_moderator(self, user_id):
        return bool(self.get_moderator(user_id))
    
    def get_all_moderators(self):
        return self.session.query(Moderator).all()
    
    def update_moderator_permissions(self, user_id, **permissions):
        moderator = self.get_moderator(user_id)
        if moderator:
            for perm, value in permissions.items():
                if hasattr(moderator, perm):
                    setattr(moderator, perm, value)
            self.session.commit()
            return moderator
        return None
    
    # Мут система
    def add_mute(self, user_id, chat_id, muted_by, duration_minutes=0, reason=None):
        mute = MuteRecord(
            user_id=user_id,
            chat_id=chat_id,
            muted_by=muted_by,
            duration_minutes=duration_minutes,
            reason=reason
        )
        
        if duration_minutes > 0:
            mute.unmute_time = datetime.utcnow() + timedelta(minutes=duration_minutes)
        
        self.session.add(mute)
        self.session.commit()
        return mute
    
    def remove_mute(self, user_id, chat_id):
        mute = self.session.query(MuteRecord).filter_by(
            user_id=user_id,
            chat_id=chat_id,
            is_active=True
        ).first()
        
        if mute:
            mute.is_active = False
            mute.unmute_time = datetime.utcnow()
            self.session.commit()
            return True
        return False
    
    def is_user_muted(self, user_id, chat_id):
        mute = self.session.query(MuteRecord).filter_by(
            user_id=user_id,
            chat_id=chat_id,
            is_active=True
        ).first()
        
        if mute and mute.duration_minutes > 0:
            if mute.unmute_time and mute.unmute_time < datetime.utcnow():
                mute.is_active = False
                self.session.commit()
                return False
        
        return bool(mute and mute.is_active)
    
    # Бан система
    def add_ban(self, user_id, chat_id, banned_by, reason=None):
        ban = BanRecord(
            user_id=user_id,
            chat_id=chat_id,
            banned_by=banned_by,
            reason=reason
        )
        self.session.add(ban)
        self.session.commit()
        return ban
    
    def remove_ban(self, user_id, chat_id):
        ban = self.session.query(BanRecord).filter_by(
            user_id=user_id,
            chat_id=chat_id,
            is_active=True
        ).first()
        
        if ban:
            ban.is_active = False
            ban.unban_time = datetime.utcnow()
            self.session.commit()
            return True
        return False
    
    def is_user_banned(self, user_id, chat_id):
        ban = self.session.query(BanRecord).filter_by(
            user_id=user_id,
            chat_id=chat_id,
            is_active=True
        ).first()
        return bool(ban)
    
    # Предупреждения
    def add_warning(self, user_id, chat_id, reason=None):
        warning = self.session.query(Warning).filter_by(
            user_id=user_id,
            chat_id=chat_id
        ).first()
        
        if warning:
            warning.warnings_count += 1
            warning.last_warning = datetime.utcnow()
            warning.reason = reason
        else:
            warning = Warning(
                user_id=user_id,
                chat_id=chat_id,
                warnings_count=1,
                reason=reason
            )
            self.session.add(warning)
        
        self.session.commit()
        return warning.warnings_count
    
    def remove_warning(self, user_id, chat_id):
        warning = self.session.query(Warning).filter_by(
            user_id=user_id,
            chat_id=chat_id
        ).first()
        
        if warning:
            if warning.warnings_count > 1:
                warning.warnings_count -= 1
            else:
                self.session.delete(warning)
            self.session.commit()
            return True
        return False
    
    def clear_warnings(self, user_id, chat_id):
        warning = self.session.query(Warning).filter_by(
            user_id=user_id,
            chat_id=chat_id
        ).first()
        
        if warning:
            self.session.delete(warning)
            self.session.commit()
            return True
        return False
    
    def get_warnings(self, user_id, chat_id):
        warning = self.session.query(Warning).filter_by(
            user_id=user_id,
            chat_id=chat_id
        ).first()
        return warning.warnings_count if warning else 0
    
    # Статистика
    def update_statistics(self, chat_id, new_subscription=0, mutes_given=0, messages_deleted=0):
        today = datetime.utcnow().date()
        start_of_day = datetime.combine(today, datetime.min.time())
        end_of_day = datetime.combine(today, datetime.max.time())
        
        stats = self.session.query(Statistics).filter(
            Statistics.chat_id == chat_id,
            Statistics.date >= start_of_day,
            Statistics.date <= end_of_day
        ).first()
        
        if not stats:
            stats = Statistics(
                chat_id=chat_id,
                date=datetime.utcnow(),
                new_subscriptions=new_subscription,
                mutes_given=mutes_given,
                messages_deleted=messages_deleted
            )
            self.session.add(stats)
        else:
            stats.new_subscriptions += new_subscription
            stats.mutes_given += mutes_given
            stats.messages_deleted += messages_deleted
        
        self.session.commit()
    
    def get_statistics_period(self, chat_id, start_date, end_date):
        end_date_with_time = datetime.combine(end_date, datetime.max.time())
        return self.session.query(Statistics).filter(
            Statistics.chat_id == chat_id,
            Statistics.date >= start_date,
            Statistics.date <= end_date_with_time
        ).all()