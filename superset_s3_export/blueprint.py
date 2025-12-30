"""
S3 Export API Blueprint
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from flask import Blueprint, current_app, request
from flask_appbuilder.security.decorators import has_access_api
from marshmallow import Schema, ValidationError, fields

logger = logging.getLogger(__name__)

# Create blueprint
s3_export_blueprint = Blueprint("s3_export", __name__, url_prefix="/api/v1/s3-export")


class ExportRequestSchema(Schema):
    """Schema for export request validation"""

    datasource_id = fields.Int(required=True)
    datasource_type = fields.Str(required=True, validate=lambda x: x in ["table", "query"])
    sql_query = fields.Str(required=True)
    dataset_name = fields.Str(required=True)
    chart_id = fields.Int(required=False, allow_none=True)
    dashboard_id = fields.Int(required=False, allow_none=True)


@s3_export_blueprint.route("/create", methods=["POST"])
@has_access_api
def create_export() -> tuple[dict[str, Any], int]:
    """
    Create a new S3 export job.

    Request body:
    {
        "datasource_id": 123,
        "datasource_type": "table",
        "sql_query": "SELECT * FROM table WHERE ...",
        "dataset_name": "Sales Report",
        "chart_id": 456,  // optional
        "dashboard_id": 789  // optional
    }

    Response:
    {
        "job_id": "abc-123-def",
        "status": "pending",
        "message": "Export queued! You'll receive an email at user@example.com when ready."
    }
    """
    # Lazy imports - import inside function to avoid circular dependency
    from superset import db, security_manager
    from superset.exceptions import SupersetSecurityException
    from superset.utils.core import get_user_id

    from .models import ExportJob, ExportStatus
    from .tasks import process_export

    try:
        # Get current user
        user = security_manager.get_user_by_id(get_user_id())
        if not user:
            return {"error": "User not authenticated"}, 401

        # Validate request
        schema = ExportRequestSchema()
        try:
            data = cast(dict[str, Any], schema.load(request.json))
        except ValidationError as err:
            return {"error": "Invalid request", "details": err.messages}, 400

        # Get S3 export config
        config = current_app.config.get("S3_EXPORT_CONFIG")
        if not config:
            logger.error("S3_EXPORT_CONFIG not found in app config")
            return {"error": "S3 export not configured"}, 500

        # Validate datasource access (RLS enforcement)
        datasource = _validate_datasource_access(
            datasource_id=data["datasource_id"],
            datasource_type=data["datasource_type"],
            user=user,
        )

        if not datasource:
            return {
                "error": "Access denied",
                "message": "You don't have permission to export this dataset",
            }, 403

        # Create export job
        job = ExportJob(
            user_id=user.id,
            user_email=user.email,
            dataset_name=data["dataset_name"],
            chart_id=data.get("chart_id"),
            dashboard_id=data.get("dashboard_id"),
            status=ExportStatus.PENDING,
        )

        db.session.add(job)  # type: ignore
        db.session.commit()  # type: ignore

        logger.info(f"Created export job {job.id} for user {user.id}")

        # Queue Celery task
        process_export.apply_async(  # type: ignore
            args=[
                str(job.id),
                data["datasource_id"],
                data["datasource_type"],
                data["sql_query"],
                user.id,
                config,
            ],
        )

        return {
            "job_id": str(job.id),
            "status": job.status.value,
            "message": f"Export queued! You'll receive an email at {user.email} when ready.",
            "created_at": job.created_at.isoformat(),
        }, 202  # 202 Accepted

    except SupersetSecurityException as e:
        logger.warning(f"Security exception in export: {str(e)}")
        return {"error": "Access denied", "message": str(e)}, 403

    except Exception as e:
        logger.exception(f"Failed to create export job: {str(e)}")
        db.session.rollback()  # type: ignore
        return {
            "error": "Failed to create export",
            "message": "An internal error occurred. Please try again later.",
        }, 500


@s3_export_blueprint.route("/status/<job_id>", methods=["GET"])
@has_access_api
def get_status(job_id: str) -> tuple[dict[str, Any], int]:
    """
    Get export job status (optional endpoint for manual checking).

    Response:
    {
        "job_id": "abc-123-def",
        "status": "processing",
        "dataset_name": "Sales Report",
        "row_count": 2500000,
        "file_size": 125000000,
        "created_at": "2025-01-01T10:00:00",
        "download_url": "https://..."  // only when completed
    }
    """
    # Lazy imports
    from superset import db, security_manager
    from superset.utils.core import get_user_id

    from .models import ExportJob

    try:
        # Get current user
        user = security_manager.get_user_by_id(get_user_id())
        if not user:
            return {"error": "User not authenticated"}, 401

        # Get job
        job = db.session.query(ExportJob).filter_by(id=job_id).first()  # type: ignore

        if not job:
            return {"error": "Job not found"}, 404

        # Check ownership
        if job.user_id != user.id:
            return {"error": "Access denied"}, 403

        # Return job status
        return job.to_dict(), 200

    except Exception as e:
        logger.exception(f"Failed to get job status: {str(e)}")
        return {"error": "Failed to retrieve status", "message": str(e)}, 500


def _validate_datasource_access(
    datasource_id: int,
    datasource_type: str,
    user: Any,
) -> Any:
    """
    Validate user has access to datasource.

    This enforces Superset's RBAC and RLS rules.

    Returns:
        Datasource object if access granted, None otherwise
    """
    # Lazy imports
    from superset import db, security_manager
    from superset.connectors.sqla.models import SqlaTable

    try:
        if datasource_type == "table":
            datasource = db.session.query(SqlaTable).filter_by(id=datasource_id).first()  # type: ignore

            if not datasource:
                logger.warning(f"Datasource {datasource_id} not found")
                return None

            # Check datasource permissions using Superset's security manager
            # This automatically enforces RLS rules
            if not security_manager.can_access_datasource(datasource):
                logger.warning(f"User {user.id} denied access to datasource {datasource_id}")
                return None

            return datasource

        else:
            # For saved queries, would need different handling
            raise NotImplementedError(f"Datasource type {datasource_type} not yet supported")

    except Exception as e:
        logger.exception(f"Error validating datasource access: {str(e)}")
        return None


def check_rate_limit(user_id: int, max_per_hour: int = 5) -> bool:
    """
    Check if user has exceeded rate limit.

    Args:
        user_id: User ID
        max_per_hour: Maximum exports per hour

    Returns:
        bool: True if within limit, False otherwise
    """
    # Lazy imports
    from superset import db

    from .models import ExportJob

    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

    count = (
        db.session.query(ExportJob)  # type: ignore
        .filter(
            ExportJob.user_id == user_id,
            ExportJob.created_at >= one_hour_ago,
        )
        .count()
    )

    return count < max_per_hour
