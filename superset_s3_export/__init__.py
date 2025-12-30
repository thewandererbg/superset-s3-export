"""
Superset S3 Export Plugin

A Superset plugin for exporting large datasets (1M-10M+ rows) to S3
with email notifications.
"""

__version__ = "0.1.0"

from flask import Flask

from .blueprint import s3_export_blueprint
from .models import ExportJob, ExportStatus


class SupersetS3ExportPlugin:
    """
    Plugin to enable S3 exports with email notifications.

    Usage in superset_config.py:

        from superset_s3_export import SupersetS3ExportPlugin

        # Register plugin
        EXTRA_FLASK_APP_CONFIG = {
            'S3_EXPORT_PLUGIN': SupersetS3ExportPlugin()
        }

        # Configure S3 and email
        S3_EXPORT_CONFIG = {
            'AWS_ACCESS_KEY_ID': os.getenv('AWS_ACCESS_KEY_ID'),
            'AWS_SECRET_ACCESS_KEY': os.getenv('AWS_SECRET_ACCESS_KEY'),
            'S3_BUCKET': 'superset-exports',
            'S3_REGION': 'us-east-1',
            'S3_ENDPOINT_URL': 'https://garage.yourdomain.com',  # For Garage/MinIO
            'EXPIRY_HOURS': 24,
            'RESEND_API_KEY': os.getenv('RESEND_API_KEY'),
            'FROM_EMAIL': 'noreply@yourdomain.com',
        }

        # Register Celery tasks
        class CeleryConfig:
            imports = ('superset.sql_lab', 'superset_s3_export.tasks')

        CELERY_CONFIG = CeleryConfig
    """

    def __init__(self):
        self.name = "S3 Export Plugin"
        self.version = __version__

    def init_app(self, app: Flask) -> None:
        """
        Initialize plugin with Flask app.

        This registers the blueprint and validates configuration.
        """
        # Validate config
        config = app.config.get("S3_EXPORT_CONFIG")
        if not config:
            app.logger.warning(
                "S3_EXPORT_CONFIG not found in app config. "
                "S3 export plugin will not function correctly."
            )
            return

        # Validate required config keys
        required_keys = [
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "S3_BUCKET",
            "RESEND_API_KEY",
        ]

        missing_keys = [key for key in required_keys if not config.get(key)]
        if missing_keys:
            app.logger.error(f"S3_EXPORT_CONFIG missing required keys: {', '.join(missing_keys)}")
            return

        # Register blueprint
        app.register_blueprint(s3_export_blueprint)

        app.logger.info(f"✓ {self.name} v{self.version} initialized successfully")
        app.logger.info(f"  S3 bucket: {config.get('S3_BUCKET')}")
        app.logger.info(f"  Endpoint: {config.get('S3_ENDPOINT_URL', 'AWS S3')}")
        app.logger.info(f"  URL expiry: {config.get('EXPIRY_HOURS', 24)} hours")


__all__ = [
    "SupersetS3ExportPlugin",
    "ExportJob",
    "ExportStatus",
]
