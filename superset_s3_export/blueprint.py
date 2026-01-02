"""
S3 Export API Blueprint
"""

import logging
from typing import Any, cast

from flask import Blueprint, current_app, request
from marshmallow import Schema, ValidationError, fields

logger = logging.getLogger(__name__)

# Create blueprint
s3_export_blueprint = Blueprint("s3_export", __name__, url_prefix="/api/v1/s3-export")


class DatasetExportRequestSchema(Schema):
    """Schema for dataset-based export"""

    dataset_id = fields.Str(required=True)
    filters = fields.Dict(required=True)
    email = fields.Email(required=True)


@s3_export_blueprint.route("/create", methods=["POST"])
def create_export() -> tuple[dict[str, Any], int]:
    """
    Create a new S3 export job.

    Request:
    {
        "dataset_id": "sales_data",
        "filters": {
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "region": "US"
        },
        "email": "user@example.com"
    }
    """
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
        try:
            schema = DatasetExportRequestSchema()
            data = cast(dict[str, Any], schema.load(request.json))
        except ValidationError as err:
            return {"error": "Invalid request", "details": err.messages}, 400

        dataset_id = data["dataset_id"]
        filters = data["filters"]
        email = data["email"]

        # Get dataset config
        datasets = current_app.config.get("S3_EXPORT_DATASETS", [])
        dataset_config = next((d for d in datasets if d["id"] == dataset_id), None)

        if not dataset_config:
            return {"error": "Dataset not found"}, 404

        # Validate filters
        if dataset_config["filters"].get("date_range"):
            if not filters.get("start_date") or not filters.get("end_date"):
                return {"error": "Date range required"}, 400

        if dataset_config["filters"].get("regions"):
            if filters.get("region") not in dataset_config["filters"]["regions"]:
                return {"error": "Invalid region"}, 400

        # Build SQL from template
        try:
            sql_query = dataset_config["sql_template"].format(**filters)
        except KeyError as e:
            return {"error": f"Missing filter parameter: {str(e)}"}, 400

        # Get S3 export config
        config = current_app.config.get("S3_EXPORT_CONFIG")
        if not config:
            logger.error("S3_EXPORT_CONFIG not found in app config")
            return {"error": "S3 export not configured"}, 500

        # Validate datasource access
        datasource = _validate_datasource_access(
            datasource_id=dataset_config["datasource_id"],
            datasource_type=dataset_config["datasource_type"],
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
            user_email=email,
            dataset_name=dataset_config["name"],
            status=ExportStatus.PENDING,
        )

        db.session.add(job)  # type: ignore
        db.session.commit()  # type: ignore

        logger.info(f"Created export job {job.id} for user {user.id}")

        # Queue Celery task
        process_export.apply_async(  # type: ignore
            args=[
                str(job.id),
                dataset_config["datasource_id"],
                dataset_config["datasource_type"],
                sql_query,
                user.id,
                config,
            ],
        )

        return {
            "job_id": str(job.id),
            "status": job.status.value,
            "message": f"Export queued! You'll receive an email at {email} when ready.",
            "created_at": job.created_at.isoformat(),
        }, 202

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
def get_status(job_id: str) -> tuple[dict[str, Any], int]:
    """Get export job status"""
    from superset import db, security_manager
    from superset.utils.core import get_user_id

    from .models import ExportJob

    try:
        user = security_manager.get_user_by_id(get_user_id())
        if not user:
            return {"error": "User not authenticated"}, 401

        job = db.session.query(ExportJob).filter_by(id=job_id).first()  # type: ignore

        if not job:
            return {"error": "Job not found"}, 404

        if job.user_id != user.id:
            return {"error": "Access denied"}, 403

        return job.to_dict(), 200

    except Exception as e:
        logger.exception(f"Failed to get job status: {str(e)}")
        return {"error": "Failed to retrieve status", "message": str(e)}, 500


@s3_export_blueprint.route("/datasets", methods=["GET"])
def get_datasets():
    """Get available export datasets from config"""
    from flask import jsonify

    datasets = current_app.config.get("S3_EXPORT_DATASETS", [])

    # Return simplified view (no SQL templates for security)
    public_datasets = [
        {
            "id": d["id"],
            "name": d["name"],
            "description": d.get("description", ""),
            "filters": d["filters"],
        }
        for d in datasets
    ]

    return jsonify({"datasets": public_datasets})


def _validate_datasource_access(
    datasource_id: int,
    datasource_type: str,
    user: Any,
) -> Any:
    """Validate user has access to datasource"""
    from superset import db, security_manager
    from superset.connectors.sqla.models import SqlaTable

    try:
        if datasource_type == "table":
            datasource = db.session.query(SqlaTable).filter_by(id=datasource_id).first()  # type: ignore

            if not datasource:
                logger.warning(f"Datasource {datasource_id} not found")
                return None

            if not security_manager.can_access_datasource(datasource):
                logger.warning(f"User {user.id} denied access to datasource {datasource_id}")
                return None

            return datasource

        else:
            raise NotImplementedError(f"Datasource type {datasource_type} not yet supported")

    except Exception as e:
        logger.exception(f"Error validating datasource access: {str(e)}")
        return None
