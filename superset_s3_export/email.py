"""
Email notifications using Resend
"""

import logging
from typing import Optional

import requests

from .models import ExportJob, ExportStatus

logger = logging.getLogger(__name__)


def send_export_email(job: ExportJob, config: dict) -> bool:
    """
    Send email notification for export job.

    Sends success email with download link or failure email with error details.

    Args:
        job: ExportJob instance
        config: S3_EXPORT_CONFIG dict containing RESEND_API_KEY

    Returns:
        bool: True if email sent successfully, False otherwise
    """
    resend_api_key = config.get("RESEND_API_KEY")
    if not resend_api_key:
        logger.error("RESEND_API_KEY not found in config")
        return False

    from_email = config.get("FROM_EMAIL", "noreply@yourdomain.com")

    try:
        if job.status == ExportStatus.COMPLETED:
            subject, html_body = _build_success_email(job)
        elif job.status == ExportStatus.FAILED:
            subject, html_body = _build_failure_email(job)
        else:
            logger.warning(f"Unexpected job status for email: {job.status}")
            return False

        # Send via Resend API
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_email,
                "to": [job.user_email],
                "subject": subject,
                "html": html_body,
            },
            timeout=10,
        )

        if response.status_code == 200:
            logger.info(f"Email sent successfully for job {job.id}")
            return True
        else:
            logger.error(
                f"Failed to send email for job {job.id}: {response.status_code} - {response.text}"
            )
            return False

    except Exception as e:
        logger.exception(f"Exception sending email for job {job.id}: {str(e)}")
        return False


def _build_success_email(job: ExportJob) -> tuple[str, str]:
    """Build success email with download link"""

    subject = f"✓ Your export is ready: {job.dataset_name}"

    # Format file size
    file_size_str = _format_file_size(job.file_size)

    # Format row count
    row_count_str = f"{job.row_count:,}" if job.row_count else "Unknown"

    # Format expiry time
    expiry_str = job.expires_at.strftime("%b %d, %Y at %H:%M UTC") if job.expires_at else "24 hours"

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">

    <div style="background: #f8f9fa; border-radius: 8px; padding: 30px; margin-bottom: 20px;">
        <h1 style="color: #2c3e50; margin: 0 0 20px 0; font-size: 24px;">
            Your export is ready! 🎉
        </h1>

        <p style="font-size: 16px; margin: 0 0 20px 0;">
            Your dataset <strong>{job.dataset_name}</strong> has been exported and is ready to download.
        </p>

        <div style="background: white; border-radius: 6px; padding: 20px; margin: 20px 0;">
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="padding: 8px 0; color: #6c757d; font-size: 14px;">Dataset:</td>
                    <td style="padding: 8px 0; font-weight: 600; font-size: 14px;">{job.dataset_name}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #6c757d; font-size: 14px;">Rows:</td>
                    <td style="padding: 8px 0; font-weight: 600; font-size: 14px;">{row_count_str}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #6c757d; font-size: 14px;">File size:</td>
                    <td style="padding: 8px 0; font-weight: 600; font-size: 14px;">{file_size_str}</td>
                </tr>
            </table>
        </div>

        <a href="{job.download_url}"
           style="display: inline-block; background: #007bff; color: white; text-decoration: none; padding: 14px 32px; border-radius: 6px; font-weight: 600; font-size: 16px; margin: 10px 0;">
            Download CSV File
        </a>

        <p style="color: #6c757d; font-size: 14px; margin: 20px 0 0 0;">
            ⏰ This link expires on <strong>{expiry_str}</strong>
        </p>
    </div>

    <div style="color: #6c757d; font-size: 12px; border-top: 1px solid #dee2e6; padding-top: 20px;">
        <p style="margin: 5px 0;">
            Job ID: <code style="background: #f8f9fa; padding: 2px 6px; border-radius: 3px;">{job.id}</code>
        </p>
        <p style="margin: 5px 0;">
            This is an automated message from Superset S3 Export Plugin.
        </p>
    </div>

</body>
</html>
"""

    return subject, html_body


def _build_failure_email(job: ExportJob) -> tuple[str, str]:
    """Build failure email with error details"""

    subject = f"✗ Export failed: {job.dataset_name}"

    # Truncate error message for display
    error_display = job.error_message[:500] if job.error_message else "Unknown error"
    if job.error_message and len(job.error_message) > 500:
        error_display += "..."

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">

    <div style="background: #fff3cd; border-left: 4px solid #ffc107; border-radius: 8px; padding: 30px; margin-bottom: 20px;">
        <h1 style="color: #856404; margin: 0 0 20px 0; font-size: 24px;">
            Export Failed
        </h1>

        <p style="font-size: 16px; margin: 0 0 20px 0;">
            Unfortunately, your export for <strong>{job.dataset_name}</strong> could not be completed.
        </p>

        <div style="background: white; border-radius: 6px; padding: 20px; margin: 20px 0;">
            <p style="color: #6c757d; font-size: 14px; margin: 0 0 10px 0;">
                <strong>Error details:</strong>
            </p>
            <pre style="background: #f8f9fa; padding: 15px; border-radius: 4px; overflow-x: auto; font-size: 13px; margin: 0; white-space: pre-wrap; word-wrap: break-word;">{error_display}</pre>
        </div>

        <div style="background: white; border-radius: 6px; padding: 20px; margin: 20px 0;">
            <p style="font-size: 14px; margin: 0 0 10px 0;">
                <strong>What to do next:</strong>
            </p>
            <ul style="margin: 0; padding-left: 20px; font-size: 14px;">
                <li>Check if your query is valid and the dataset still exists</li>
                <li>Try exporting a smaller date range or fewer columns</li>
                <li>Contact your Superset administrator if the issue persists</li>
            </ul>
        </div>
    </div>

    <div style="color: #6c757d; font-size: 12px; border-top: 1px solid #dee2e6; padding-top: 20px;">
        <p style="margin: 5px 0;">
            Job ID: <code style="background: #f8f9fa; padding: 2px 6px; border-radius: 3px;">{job.id}</code>
        </p>
        <p style="margin: 5px 0;">
            Retry count: {job.retry_count}
        </p>
        <p style="margin: 5px 0;">
            This is an automated message from Superset S3 Export Plugin.
        </p>
    </div>

</body>
</html>
"""

    return subject, html_body


def _format_file_size(size_bytes: Optional[int]) -> str:
    """Format file size in human-readable format"""
    if size_bytes is None or size_bytes == 0:
        return "Unknown"

    size = float(size_bytes)

    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0

    return f"{size:.2f} PB"
