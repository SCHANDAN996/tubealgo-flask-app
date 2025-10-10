# tubealgo/models/youtube_models.py

from .. import db
from datetime import date

class YouTubeChannel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    channel_id_youtube = db.Column(db.String(100), unique=True, nullable=False)
    channel_title = db.Column(db.String(200), nullable=False)
    thumbnail_url = db.Column(db.String(255))

class ChannelSnapshot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    channel_db_id = db.Column(db.Integer, db.ForeignKey('you_tube_channel.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    subscribers = db.Column(db.Integer, nullable=False)
    views = db.Column(db.BigInteger, nullable=False)
    video_count = db.Column(db.Integer, nullable=False)
    
    channel = db.relationship('YouTubeChannel', backref='snapshots')
    __table_args__ = (db.UniqueConstraint('channel_db_id', 'date', name='_channel_date_uc'),)

class Competitor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    channel_id_youtube = db.Column(db.String(100), nullable=False)
    channel_title = db.Column(db.String(200), nullable=False)
    thumbnail_url = db.Column(db.String(255))
    position = db.Column(db.Integer, nullable=False)
    last_known_video_id = db.Column(db.String(50), nullable=True)