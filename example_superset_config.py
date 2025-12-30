"""
Example Superset configuration for S3 Export Plugin

Add this to your superset_config.py
"""

import os

from superset_s3_export import SupersetS3ExportPlugin

# ==============================================================================
# S3 Export Plugin Configuration
# ==============================================================================

# 1. Register the plugin
EXTRA_FLASK_APP_CONFIG = {"S3_EXPORT_PLUGIN": SupersetS3ExportPlugin()}

# 2. Configure S3 storage and email
S3_EXPORT_CONFIG = {
    # S3 Configuration
    "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID"),
    "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY"),
    "S3_BUCKET": os.getenv("S3_BUCKET", "superset-exports"),
    "S3_REGION": os.getenv("S3_REGION", "us-east-1"),
    # For self-hosted S3 (Garage, MinIO, CloudFlare R2)
    # Leave blank for AWS S3
    "S3_ENDPOINT_URL": os.getenv("S3_ENDPOINT_URL"),  # e.g., 'https://garage.yourdomain.com'
    # Download link expiry (hours)
    "EXPIRY_HOURS": int(os.getenv("EXPORT_EXPIRY_HOURS", 24)),
    # Email Configuration (Resend)
    "RESEND_API_KEY": os.getenv("RESEND_API_KEY"),
    "FROM_EMAIL": os.getenv("FROM_EMAIL", "noreply@yourdomain.com"),
}


# 3. Register Celery tasks
class CeleryConfig:
    """Celery configuration"""

    # Add S3 export tasks to imports
    imports = (
        "superset.sql_lab",
        "superset_s3_export.tasks",
    )

    # Optional: Configure separate queue for exports
    # task_routes = {
    #     'superset_s3_export.tasks.process_export': {'queue': 'exports'},
    # }


CELERY_CONFIG = CeleryConfig

# ==============================================================================
# Environment Variables Required
# ==============================================================================
#
# Create a .env file in your Superset directory:
#
# # S3 Configuration
# AWS_ACCESS_KEY_ID=your_access_key_id
# AWS_SECRET_ACCESS_KEY=your_secret_access_key
# S3_BUCKET=superset-exports
# S3_REGION=us-east-1
# S3_ENDPOINT_URL=https://garage.yourdomain.com  # Optional, for self-hosted S3
#
# # Email Configuration
# RESEND_API_KEY=re_xxxxxxxxxxxxx
# FROM_EMAIL=noreply@yourdomain.com
#
# # Export Settings
# EXPORT_EXPIRY_HOURS=24
#
# ==============================================================================

# ==============================================================================
# Optional: Rate Limiting
# ==============================================================================
#
# Uncomment to enable rate limiting (5 exports per hour per user)
# Add to blueprint.py create_export() function:
#
# from superset_s3_export.blueprint import check_rate_limit
#
# if not check_rate_limit(user.id, max_per_hour=5):
#     return jsonify({
#         "error": "Rate limit exceeded",
#         "message": "Maximum 5 exports per hour. Please try again later."
#     }), 429
#
# ==============================================================================

# ==============================================================================
# Celery Worker Start Command
# ==============================================================================
#
# Start Celery worker with:
#
#   celery -A superset.tasks.celery_app:app worker --loglevel=info
#
# Or with dedicated export queue:
#
#   celery -A superset.tasks.celery_app:app worker -Q exports --loglevel=info
#
# ==============================================================================
