from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
#comment for triggering

db = SQLAlchemy()

class Incident(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.String(10), unique=True, nullable=False) # e.g., INC-001
    service = db.Column(db.String(100), nullable=False)
    severity = db.Column(db.Enum('SEV1', 'SEV2', 'SEV3'), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='Open') # Open, Investigating, etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class IncidentLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.String(10), nullable=False)
    action = db.Column(db.String(50))
    message = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
