# Superset S3 Export Plugin

Export large datasets (1M-10M+ rows) from Apache Superset to S3 with email notifications.

## Features

✅ **Unlimited scale** - Export 10M, 100M, 1B+ rows  
✅ **Memory efficient** - Streams data in chunks, no memory bloat  
✅ **Async processing** - Celery background workers  
✅ **Email notifications** - Receive download link when ready  
✅ **Reuses Superset auth** - OAuth, RBAC, RLS automatically applied  
✅ **S3 compatible** - Works with AWS S3, Garage, MinIO, R2

## Installation

### Prerequisites

- Apache Superset 6.0+
- PostgreSQL database
- S3-compatible storage (AWS S3, Garage, MinIO, CloudFlare R2)
- Resend API key (for emails)
- Celery worker running

### Install with uv

```bash
# Install the plugin
uv pip install git+https://github.com/thewandererbg/superset-s3-export.git

# Or install from local directory
cd superset-s3-export
uv pip install -e .
```

### Configuration

Add to your `superset_config.py`:

```python
import os
from superset_s3_export import SupersetS3ExportPlugin

# 1. Register plugin
EXTRA_FLASK_APP_CONFIG = {
    'S3_EXPORT_PLUGIN': SupersetS3ExportPlugin()
}

# 2. Configure S3 and email
S3_EXPORT_CONFIG = {
    # S3 credentials (env vars use S3_ prefix, dict keys match boto3 API)
    'AWS_ACCESS_KEY_ID': os.getenv('S3_ACCESS_KEY_ID'),
    'AWS_SECRET_ACCESS_KEY': os.getenv('S3_SECRET_ACCESS_KEY'),
    'S3_BUCKET': os.getenv('S3_BUCKET', 'superset-exports'),
    'S3_REGION': os.getenv('S3_REGION', 'garage'),
    'S3_ENDPOINT_URL': os.getenv('S3_ENDPOINT_URL'),
    
    # Download link expiry
    'EXPIRY_HOURS': int(os.getenv('EXPORT_EXPIRY_HOURS', '24')),
    
    # Email (Resend)
    'RESEND_API_KEY': os.getenv('RESEND_API_KEY'),
    'FROM_EMAIL': os.getenv('FROM_EMAIL', 'noreply@yourdomain.com'),
}

# 3. Register Celery tasks
class CeleryConfig:
    imports = ('superset.sql_lab', 'superset_s3_export.tasks')

CELERY_CONFIG = CeleryConfig
```

### Environment Variables

```bash
# .env file
S3_ACCESS_KEY_ID=your_access_key
S3_SECRET_ACCESS_KEY=your_secret_key
S3_ENDPOINT_URL=https://garage.yourdomain.com  # Optional, for self-hosted
RESEND_API_KEY=re_xxxxxxxxxxxxx
```

### Database Migration

Run the migration to create the `s3_export_jobs` table:

```bash
# Run Superset migrations
superset db upgrade

# The plugin migration will run automatically
```

### Start Celery Worker

```bash
# Start worker for export tasks
celery -A superset.tasks.celery_app:app worker --loglevel=info

# Or with specific queue (optional)
celery -A superset.tasks.celery_app:app worker -Q exports --loglevel=info
```

## Usage

### API Endpoint

**Create export job:**

```bash
POST /api/v1/s3-export/create
Content-Type: application/json
Authorization: Bearer <superset_jwt_token>

{
  "datasource_id": 123,
  "datasource_type": "table",
  "sql_query": "SELECT * FROM sales WHERE region = 'US'",
  "dataset_name": "US Sales Report",
  "chart_id": 456  // optional
}
```

**Response:**

```json
{
  "job_id": "abc-123-def-456",
  "status": "pending",
  "message": "Export queued! You'll receive an email at user@company.com when ready.",
  "created_at": "2025-01-01T10:00:00"
}
```

**Check status (optional):**

```bash
GET /api/v1/s3-export/status/<job_id>
```

### User Flow

1. User clicks "Export to S3" in Superset chart
2. Toast notification: "Export queued! Check your email."
3. Email arrives (5-30 minutes later) with download link
4. User clicks link → Direct S3 download

## Architecture

```
User → Superset UI
  ↓
POST /api/v1/s3-export/create
  ↓
Celery Queue
  ↓
Background Worker:
  - Query database (RLS applied)
  - Stream to S3 (chunked)
  - Generate pre-signed URL
  - Send email
  ↓
User receives email with download link
```

## Configuration Options

| Option                  | Required | Default                  | Description                       |
| ----------------------- | -------- | ------------------------ | --------------------------------- |
| `AWS_ACCESS_KEY_ID`     | Yes      | -                        | S3 access key                     |
| `AWS_SECRET_ACCESS_KEY` | Yes      | -                        | S3 secret key                     |
| `S3_BUCKET`             | Yes      | -                        | S3 bucket name                    |
| `S3_REGION`             | No       | `us-east-1`              | S3 region                         |
| `S3_ENDPOINT_URL`       | No       | -                        | Custom S3 endpoint (Garage/MinIO) |
| `EXPIRY_HOURS`          | No       | `24`                     | Download URL expiry in hours      |
| `RESEND_API_KEY`        | Yes      | -                        | Resend API key                    |
| `FROM_EMAIL`            | No       | `noreply@yourdomain.com` | Email sender address              |

## Development

### Setup with uv

```bash
# Clone repository
git clone https://github.com/thewandererbg/superset-s3-export.git
cd superset-s3-export

# Install with dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Format code
black superset_s3_export/
ruff check superset_s3_export/

# Type check
mypy superset_s3_export/
```

## Troubleshooting

**Emails not arriving?**

- Check Resend dashboard for delivery status
- Verify `FROM_EMAIL` domain is verified in Resend
- Check spam folder

**S3 upload failing?**

- Verify S3 credentials and permissions
- Check `S3_ENDPOINT_URL` is correct for self-hosted S3
- Ensure bucket exists and is accessible

**RLS not working?**

- Verify datasource permissions in Superset
- Check Superset logs for security exceptions
- Ensure user has access to the datasource

**Celery tasks not processing?**

- Check Celery worker is running
- Verify `CELERY_CONFIG.imports` includes `'superset_s3_export.tasks'`
- Check Celery logs: `celery -A superset.tasks.celery_app:app worker --loglevel=debug`

## Cost Estimates

**Storage:** ~$0.023/GB/month (S3 Standard)  
**Transfer:** ~$0.09/GB (S3 to internet)  
**Emails:** ~$0.001/email (Resend)

**Example:** 10GB export = $0.23 storage + $0.90 transfer + $0.001 email = **~$1.13**

**Cost optimization:**

- Use CloudFlare R2: ~$0.015/GB, $0 egress
- Use Garage (self-hosted): No cloud costs
- Auto-delete exports after 24 hours

## License

Apache 2.0

## Support

- GitHub Issues: https://github.com/thewandererbg/superset-s3-export/issues
- Documentation: https://github.com/thewandererbg/superset-s3-export#readme
