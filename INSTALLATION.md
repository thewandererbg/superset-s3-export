# Installation & Setup Guide

## Quick Start

### 1. Install Plugin with uv

```bash
# Option A: Install from git
uv pip install git+https://github.com/thewandererbg/superset-s3-export.git

# Option B: Install from local directory (for development)
cd superset-s3-export
uv pip install -e .
```

### 2. Configure Environment Variables

Create `.env` file:

```bash
# S3 Configuration (Garage)
AWS_ACCESS_KEY_ID=your_garage_key
AWS_SECRET_ACCESS_KEY=your_garage_secret
S3_BUCKET=superset-exports
S3_ENDPOINT_URL=https://garage.yourdomain.com
S3_REGION=garage  # or your region

# Email Configuration (Resend)
RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxx
FROM_EMAIL=noreply@yourdomain.com

# Export Settings
EXPORT_EXPIRY_HOURS=24
```

### 3. Update superset_config.py

Add to your `superset_config.py`:

```python
import os
from superset_s3_export import SupersetS3ExportPlugin

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Register plugin
EXTRA_FLASK_APP_CONFIG = {
    'S3_EXPORT_PLUGIN': SupersetS3ExportPlugin()
}

# Configure plugin
S3_EXPORT_CONFIG = {
    'AWS_ACCESS_KEY_ID': os.getenv('AWS_ACCESS_KEY_ID'),
    'AWS_SECRET_ACCESS_KEY': os.getenv('AWS_SECRET_ACCESS_KEY'),
    'S3_BUCKET': os.getenv('S3_BUCKET'),
    'S3_REGION': os.getenv('S3_REGION', 'us-east-1'),
    'S3_ENDPOINT_URL': os.getenv('S3_ENDPOINT_URL'),
    'EXPIRY_HOURS': int(os.getenv('EXPORT_EXPIRY_HOURS', 24)),
    'RESEND_API_KEY': os.getenv('RESEND_API_KEY'),
    'FROM_EMAIL': os.getenv('FROM_EMAIL'),
}

# Register Celery tasks
class CeleryConfig:
    imports = ('superset.sql_lab', 'superset_s3_export.tasks')

CELERY_CONFIG = CeleryConfig
```

### 4. Run Database Migration

```bash
# Apply migrations
superset db upgrade

# Verify table created
psql -d superset -c "\dt s3_export_jobs"
```

### 5. Start Celery Worker

```bash
# Start worker
celery -A superset.tasks.celery_app:app worker --loglevel=info

# Or in production with supervisor/systemd
celery -A superset.tasks.celery_app:app worker \
  --loglevel=info \
  --concurrency=4 \
  --max-tasks-per-child=100
```

### 6. Start Superset

```bash
superset run -p 8088 --with-threads --reload --debugger
```

## Verification

### Test API Endpoint

```bash
# Get auth token first
TOKEN=$(curl -X POST http://localhost:8088/api/v1/security/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin", "provider": "db"}' \
  | jq -r .access_token)

# Create export job
curl -X POST http://localhost:8088/api/v1/s3-export/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "datasource_id": 1,
    "datasource_type": "table",
    "sql_query": "SELECT * FROM your_table LIMIT 1000",
    "dataset_name": "Test Export"
  }'
```

### Check Logs

```bash
# Superset logs
tail -f superset.log

# Celery logs
tail -f celery.log

# PostgreSQL logs (for job status)
psql -d superset -c "SELECT * FROM s3_export_jobs ORDER BY created_at DESC LIMIT 5;"
```

## Garage-Specific Configuration

### Garage Bucket Setup

```bash
# Create bucket
garage bucket create superset-exports

# Allow access
garage bucket allow --read --write superset-exports

# Get credentials
garage key info your-key-name
```

### Test Garage Connection

```python
import boto3

s3 = boto3.client(
    's3',
    endpoint_url='https://garage.yourdomain.com',
    aws_access_key_id='your_key',
    aws_secret_access_key='your_secret',
)

# Test connection
buckets = s3.list_buckets()
print(buckets)

# Test upload
s3.put_object(
    Bucket='superset-exports',
    Key='test.txt',
    Body=b'Hello World'
)

# Test pre-signed URL
url = s3.generate_presigned_url(
    'get_object',
    Params={'Bucket': 'superset-exports', 'Key': 'test.txt'},
    ExpiresIn=3600
)
print(url)
```

## Production Deployment

### Systemd Service (Celery)

Create `/etc/systemd/system/superset-celery.service`:

```ini
[Unit]
Description=Superset Celery Worker
After=network.target postgresql.service

[Service]
Type=forking
User=superset
Group=superset
WorkingDirectory=/opt/superset
Environment="PATH=/opt/superset/venv/bin"
EnvironmentFile=/opt/superset/.env
ExecStart=/opt/superset/venv/bin/celery -A superset.tasks.celery_app:app worker \
  --loglevel=info \
  --concurrency=4 \
  --max-tasks-per-child=100 \
  --pidfile=/var/run/celery.pid \
  --logfile=/var/log/superset/celery.log

[Install]
WantedBy=multi-user.target
```

Start service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable superset-celery
sudo systemctl start superset-celery
sudo systemctl status superset-celery
```

### Monitoring

```bash
# Check export job counts
psql -d superset -c "
  SELECT status, COUNT(*) 
  FROM s3_export_jobs 
  WHERE created_at > NOW() - INTERVAL '24 hours'
  GROUP BY status;
"

# Check average processing time
psql -d superset -c "
  SELECT AVG(EXTRACT(EPOCH FROM (completed_at - created_at))) as avg_seconds
  FROM s3_export_jobs
  WHERE status = 'COMPLETED' 
    AND completed_at > NOW() - INTERVAL '24 hours';
"

# Check failure rate
psql -d superset -c "
  SELECT 
    COUNT(CASE WHEN status = 'FAILED' THEN 1 END)::float / COUNT(*)::float * 100 as failure_rate
  FROM s3_export_jobs
  WHERE created_at > NOW() - INTERVAL '24 hours';
"
```

## Troubleshooting

### Problem: Migration not running

```bash
# Check if migration file is discovered
python -c "from superset_s3_export.migrations import s3export_001_create_table; print('✓ Migration found')"

# Run migration manually
superset db upgrade
```

### Problem: Celery tasks not executing

```bash
# Check Celery is discovering tasks
celery -A superset.tasks.celery_app:app inspect registered | grep s3_export

# Check Celery queue
celery -A superset.tasks.celery_app:app inspect active
```

### Problem: S3 upload failing

```bash
# Test S3 connection
python3 << EOF
import boto3
s3 = boto3.client('s3', endpoint_url='https://garage.yourdomain.com')
try:
    s3.head_bucket(Bucket='superset-exports')
    print('✓ Bucket accessible')
except Exception as e:
    print(f'✗ Error: {e}')
EOF
```

### Problem: Emails not sending

```bash
# Test Resend API
curl -X POST https://api.resend.com/emails \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "from": "noreply@yourdomain.com",
    "to": ["test@example.com"],
    "subject": "Test",
    "html": "<p>Test email</p>"
  }'
```

## Next Steps

1. **Add Frontend UI** - Create export button in Superset chart menu
2. **Add Rate Limiting** - Prevent abuse (5 exports/hour per user)
3. **Add Cleanup Job** - Auto-delete expired S3 files
4. **Add Monitoring** - Track export metrics and failures
5. **Add Tests** - Unit and integration tests

## Support

- Check logs: `/var/log/superset/`
- Check database: `SELECT * FROM s3_export_jobs;`
- GitHub Issues: https://github.com/thewandererbg/superset-s3-export/issues
