"""
Celery task for S3 export processing
"""

import csv
import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Union

import boto3
from celery import Task
from sqlalchemy.orm import Session, scoped_session
from superset import db
from superset.connectors.sqla.models import SqlaTable
from superset.extensions import celery_app
from superset.models.core import Database

from .models import ExportJob

logger = logging.getLogger(__name__)


class ExportTask(Task):
    """Base task with error handling"""

    autoretry_for = (Exception,)
    retry_kwargs = {"max_retries": 3, "countdown": 60}
    retry_backoff = True


@celery_app.task(base=ExportTask, bind=True)
def process_export(
    self,
    job_id: str,
    datasource_id: int,
    datasource_type: str,
    sql_query: str,
    user_id: int,
    config: dict,
) -> dict:
    """Process S3 export job with RLS enforcement."""

    # Import the flask_app that was created at module init
    from superset.tasks.celery_app import flask_app

    # Use test_request_context like Superset does
    with flask_app.test_request_context():
        from superset import db
        from superset.models.core import Database

        from .email import send_export_email
        from .models import ExportJob, ExportStatus

        session = db.session
        job = session.query(ExportJob).filter_by(id=job_id).first()  # type: ignore

        if not job:
            logger.error(f"Job {job_id} not found")
            return {"status": "failed", "error": "Job not found"}

        try:
            # Update status to processing
            job.status = ExportStatus.PROCESSING
            job.retry_count = self.request.retries
            session.commit()  # type: ignore

            logger.info(f"Processing export job {job_id} for user {user_id}")

            # Step 1: Get datasource with RLS context
            datasource = _get_datasource(datasource_id, datasource_type)
            if not datasource:
                raise ValueError(f"Datasource {datasource_id} not found")

            # Step 2: Execute query with RLS (Superset handles this automatically)
            database: Database = datasource.database
            rows_processed, file_size = _stream_to_s3(
                database=database,
                sql_query=sql_query,
                job=job,
                config=config,
                session=session,
            )

            # Step 3: Generate pre-signed URL
            download_url = _generate_presigned_url(
                s3_key=job.s3_key,
                config=config,
                expiry_hours=config.get("EXPIRY_HOURS", 24),
            )

            # Step 4: Update job as completed
            job.status = ExportStatus.COMPLETED
            job.download_url = download_url
            job.row_count = rows_processed
            job.file_size = file_size
            job.completed_at = datetime.now(timezone.utc)
            job.expires_at = datetime.now(timezone.utc) + timedelta(
                hours=config.get("EXPIRY_HOURS", 24)
            )
            session.commit()  # type: ignore

            # Step 5: Send email notification
            send_export_email(job, config)

            logger.info(f"Export job {job_id} completed: {rows_processed} rows, {file_size} bytes")

            return {
                "status": "completed",
                "job_id": str(job_id),
                "row_count": rows_processed,
                "file_size": file_size,
            }

        except Exception as e:
            logger.exception(f"Export job {job_id} failed: {str(e)}")

            # Update job as failed
            job.status = ExportStatus.FAILED
            job.error_message = str(e)[:5000]  # Truncate long errors
            job.completed_at = datetime.now(timezone.utc)
            session.commit()  # type: ignore

            # Send failure email
            try:
                send_export_email(job, config)
            except Exception as email_err:
                logger.error(f"Failed to send error email: {email_err}")

            # Re-raise for Celery retry
            raise

        finally:
            session.close()  # type: ignore


def _get_datasource(datasource_id: int, datasource_type: str):
    """Get datasource (table or query) from Superset"""
    if datasource_type == "table":
        return db.session.query(SqlaTable).filter_by(id=datasource_id).first()  # type: ignore
    else:
        # For saved queries, would need different handling
        raise NotImplementedError(f"Datasource type {datasource_type} not yet supported")


def _stream_to_s3(
    database: Database,
    sql_query: str,
    job: ExportJob,
    config: dict,
    session: Union[Session, scoped_session],
    chunk_size: int = 10000,
) -> tuple[int, int]:
    """
    Stream query results to S3 as CSV.

    Returns:
        tuple: (row_count, file_size_bytes)
    """
    # Initialize S3 client
    s3_client = boto3.client(
        "s3",
        endpoint_url=config.get("S3_ENDPOINT_URL"),  # For Garage/MinIO
        aws_access_key_id=config["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=config["AWS_SECRET_ACCESS_KEY"],
        region_name=config.get("S3_REGION", "us-east-1"),
    )

    # Generate S3 key
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    s3_key = f"exports/{job.user_id}/{timestamp}_{job.id}.csv"
    job.s3_key = s3_key
    session.commit()  # type: ignore

    # Create multipart upload
    bucket = config["S3_BUCKET"]
    mpu = s3_client.create_multipart_upload(Bucket=bucket, Key=s3_key)
    upload_id = mpu["UploadId"]

    parts = []
    part_number = 1
    row_count = 0
    total_size = 0

    try:
        # Execute query and stream results
        with database.get_sqla_engine() as engine, engine.connect() as connection:  # type: ignore
            result = connection.execute(sql_query)

            # Get column names
            columns = result.keys()

            # Buffer for chunked uploads (5MB minimum for S3 multipart)
            buffer = io.StringIO()
            writer = csv.writer(buffer)

            # Write header
            writer.writerow(columns)

            # Stream rows in chunks
            while True:
                chunk = result.fetchmany(chunk_size)
                if not chunk:
                    break

                for row in chunk:
                    writer.writerow(row)
                    row_count += 1

                # Upload when buffer reaches 5MB
                if buffer.tell() > 5 * 1024 * 1024:
                    part_data = buffer.getvalue().encode("utf-8")
                    part_size = len(part_data)

                    response = s3_client.upload_part(
                        Bucket=bucket,
                        Key=s3_key,
                        PartNumber=part_number,
                        UploadId=upload_id,
                        Body=part_data,
                    )

                    parts.append(
                        {
                            "PartNumber": part_number,
                            "ETag": response["ETag"],
                        }
                    )

                    total_size += part_size
                    part_number += 1

                    # Reset buffer
                    buffer = io.StringIO()
                    writer = csv.writer(buffer)

                    logger.info(
                        f"Job {job.id}: Uploaded part {part_number - 1}, {row_count} rows so far"
                    )

        # Upload remaining data
        if buffer.tell() > 0:
            part_data = buffer.getvalue().encode("utf-8")
            part_size = len(part_data)

            response = s3_client.upload_part(
                Bucket=bucket,
                Key=s3_key,
                PartNumber=part_number,
                UploadId=upload_id,
                Body=part_data,
            )

            parts.append(
                {
                    "PartNumber": part_number,
                    "ETag": response["ETag"],
                }
            )

            total_size += part_size

        # Complete multipart upload
        s3_client.complete_multipart_upload(
            Bucket=bucket,
            Key=s3_key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )

        logger.info(f"Job {job.id}: S3 upload complete - {row_count} rows, {total_size} bytes")

        return row_count, total_size

    except Exception:
        # Abort multipart upload on failure
        try:
            s3_client.abort_multipart_upload(
                Bucket=bucket,
                Key=s3_key,
                UploadId=upload_id,
            )
        except Exception as abort_err:
            logger.error(f"Failed to abort multipart upload: {abort_err}")

        raise


def _generate_presigned_url(
    s3_key: str,
    config: dict,
    expiry_hours: int = 24,
) -> str:
    """
    Generate pre-signed URL for S3 object download.

    Args:
        s3_key: S3 object key
        config: S3 configuration
        expiry_hours: URL expiry in hours

    Returns:
        str: Pre-signed URL
    """
    s3_client = boto3.client(
        "s3",
        endpoint_url=config.get("S3_ENDPOINT_URL"),
        aws_access_key_id=config["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=config["AWS_SECRET_ACCESS_KEY"],
        region_name=config.get("S3_REGION", "us-east-1"),
    )

    url = s3_client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": config["S3_BUCKET"],
            "Key": s3_key,
        },
        ExpiresIn=expiry_hours * 3600,
    )

    return url
