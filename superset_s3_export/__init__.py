"""
Superset S3 Export Plugin
"""

__version__ = "0.1.0"

from flask import Flask, render_template
from flask_appbuilder import BaseView, expose
from superset.extensions import appbuilder


class S3ExportView(BaseView):
    """Custom page for S3 exports"""

    route_base = "/s3exports"
    default_view = "list"

    @expose("/")
    def list(self):
        """Show list of charts for export"""
        return render_template("s3_export_list.html")


class SupersetS3ExportPlugin:
    """Plugin to enable S3 exports with email notifications."""

    def __init__(self):
        self.name = "S3 Export Plugin"
        self.version = __version__

    def init_app(self, app: Flask) -> None:
        """Initialize plugin with Flask app."""
        # Lazy import to avoid circular imports
        from .blueprint import s3_export_blueprint

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

        # Register blueprint (API endpoints)
        app.register_blueprint(s3_export_blueprint)

        # Register view and menu item (UI page)
        appbuilder.add_view_no_menu(S3ExportView)
        appbuilder.add_link(
            "S3 Exports",
            href="/s3exports/",
            icon="fa-cloud-upload",
            category="",  # Top level menu
            category_icon="",
        )

        app.logger.info(f"✓ {self.name} v{self.version} initialized successfully")
        app.logger.info(f"  S3 bucket: {config.get('S3_BUCKET')}")
        app.logger.info(f"  Endpoint: {config.get('S3_ENDPOINT_URL', 'AWS S3')}")
        app.logger.info(f"  URL expiry: {config.get('EXPIRY_HOURS', 24)} hours")
        app.logger.info("  UI page: /s3exports/")


__all__ = [
    "SupersetS3ExportPlugin",
]
