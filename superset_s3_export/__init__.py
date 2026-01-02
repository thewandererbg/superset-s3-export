"""
Superset S3 Export Plugin
"""

__version__ = "0.1.0"

import os

from flask import Flask, render_template
from flask_appbuilder import BaseView, expose


class S3ExportView(BaseView):
    """Custom page for S3 exports"""

    route_base = "/s3exports"
    default_view = "list"

    @expose("/")
    def list(self):
        """Show export form"""
        return render_template("s3_export_list.html")


class SupersetS3ExportPlugin:
    """Plugin to enable S3 exports with email notifications."""

    def __init__(self):
        self.name = "S3 Export Plugin"
        self.version = __version__

    def init_app(self, app: Flask) -> None:
        """Initialize plugin with Flask app."""
        from .blueprint import s3_export_blueprint

        config = app.config.get("S3_EXPORT_CONFIG")
        if not config:
            app.logger.warning("S3_EXPORT_CONFIG not found")
            return

        required_keys = [
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "S3_BUCKET",
            "RESEND_API_KEY",
        ]

        missing_keys = [key for key in required_keys if not config.get(key)]
        if missing_keys:
            app.logger.error(f"Missing config keys: {', '.join(missing_keys)}")
            return

        # Register template folder (CRITICAL!)
        template_folder = os.path.join(os.path.dirname(__file__), "templates")
        if app.jinja_loader is not None:
            app.jinja_loader.searchpath.append(template_folder)

        # Register API blueprint
        app.register_blueprint(s3_export_blueprint)

        # Register view and menu
        from superset.extensions import appbuilder

        appbuilder.add_view(
            S3ExportView,
            "Exports",
            icon="fa-cloud-download",
            category="",
        )

        app.logger.info(f"✓ {self.name} initialized")
        app.logger.info("  UI: /s3exports/")
        app.logger.info(f"  Templates: {template_folder}")


__all__ = ["SupersetS3ExportPlugin"]
