"""Create s3_export_jobs table

Revision ID: s3export_001
Revises:
Create Date: 2025-01-01 00:00:00

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "s3export_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Create s3_export_jobs table"""
    op.create_table(
        "s3_export_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("user_email", sa.String(length=320), nullable=False),
        sa.Column("dataset_name", sa.String(length=500), nullable=False),
        sa.Column("chart_id", sa.Integer(), nullable=True),
        sa.Column("dashboard_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("PENDING", "PROCESSING", "COMPLETED", "FAILED", name="exportstatus"),
            nullable=False,
        ),
        sa.Column("s3_key", sa.String(length=1024), nullable=True),
        sa.Column("download_url", sa.Text(), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("row_count", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["ab_user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for common queries
    op.create_index("ix_s3_export_jobs_user_id", "s3_export_jobs", ["user_id"])
    op.create_index("ix_s3_export_jobs_status", "s3_export_jobs", ["status"])
    op.create_index("ix_s3_export_jobs_created_at", "s3_export_jobs", ["created_at"])


def downgrade():
    """Drop s3_export_jobs table"""
    op.drop_index("ix_s3_export_jobs_created_at", table_name="s3_export_jobs")
    op.drop_index("ix_s3_export_jobs_status", table_name="s3_export_jobs")
    op.drop_index("ix_s3_export_jobs_user_id", table_name="s3_export_jobs")
    op.drop_table("s3_export_jobs")
    op.execute("DROP TYPE exportstatus")
