"""
S3 Export Job Model
"""

import enum
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from superset import db


class ExportStatus(enum.Enum):
    """Export job status"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ExportJob(db.Model):
    """
    Tracks S3 export jobs with email notifications.
    Jobs auto-expire after 24 hours (handled by S3 pre-signed URL expiry).
    """

    __tablename__ = "s3_export_jobs"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # User info (from Superset's ab_user table)
    user_id = Column(Integer, nullable=False)
    user_email = Column(String(320), nullable=False)  # RFC 5321 max email length

    # Export metadata
    dataset_name = Column(String(500), nullable=False)
    chart_id = Column(Integer, nullable=True)  # Optional: link to chart
    dashboard_id = Column(Integer, nullable=True)  # Optional: link to dashboard

    # Status tracking
    status = Column(Enum(ExportStatus), nullable=False, default=ExportStatus.PENDING)

    # S3 details
    s3_key = Column(String(1024), nullable=True)  # S3 object key
    download_url = Column(Text, nullable=True)  # Pre-signed URL (can be long)

    # File info
    file_size = Column(BigInteger, nullable=True)  # Bytes
    row_count = Column(BigInteger, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)  # When download URL expires

    # Error handling
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)

    def __repr__(self):
        return f"<ExportJob {self.id} ({self.status.value})>"

    def to_dict(self):
        """Serialize to dictionary"""
        return {
            "id": str(self.id),
            "user_email": self.user_email,
            "dataset_name": self.dataset_name,
            "status": self.status.value,
            "download_url": self.download_url,
            "file_size": self.file_size,
            "row_count": self.row_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "error_message": self.error_message,
        }
