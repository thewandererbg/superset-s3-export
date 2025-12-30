# Quick Reference Guide

## TL;DR - Installation

### For End Users (Installing Plugin)
```bash
# 1. Activate your Superset environment
source /path/to/superset/venv/bin/activate

# 2. Install plugin (only boto3 + requests)
uv pip install superset-s3-export

# 3. Configure (see example_superset_config.py)
# 4. Run migration
superset db upgrade

# 5. Start Celery worker
celery -A superset.tasks.celery_app:app worker --loglevel=info
```

### For Developers (Working on Plugin)
```bash
# 1. Install Python dev headers
sudo apt-get install python3-dev build-essential

# 2. Create venv and install with dev dependencies
python3.12 -m venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"  # Installs Superset + dev tools

# 3. Run tests
pytest

# 4. Format code
black superset_s3_export/
ruff check superset_s3_export/
```

---

## Package Structure

```
superset-s3-export/
├── superset_s3_export/          # Main package
│   ├── __init__.py              # Plugin registration
│   ├── models.py                # ExportJob model
│   ├── blueprint.py             # REST API
│   ├── tasks.py                 # Celery worker
│   ├── email.py                 # Resend emails
│   └── migrations/              # Alembic migration
│
├── tests/                       # Test suite
│   ├── conftest.py              # Pytest fixtures
│   └── test_models.py           # Model tests
│
├── pyproject.toml               # Package config (uv/pip)
├── README.md                    # User documentation
├── INSTALLATION.md              # Setup guide
├── DEVELOPMENT.md               # Developer guide
└── TROUBLESHOOTING.md           # Common issues
```

---

## Dependencies Explained

### Production Dependencies (Required)
```toml
dependencies = [
    "boto3>=1.28.0",      # S3 client
    "requests>=2.31.0",   # Resend API
]
```

**Note:** Celery, SQLAlchemy, Alembic, Flask come from Superset.

### Development Dependencies (Optional)
```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",              # Testing
    "black>=23.7.0",              # Formatting
    "ruff>=0.0.285",              # Linting
    "mypy>=1.5.0",                # Type checking
    "apache-superset>=6.0.0",     # For dev/testing only
]
```

---

## Configuration Quick Reference

```python
# In superset_config.py
from superset_s3_export import SupersetS3ExportPlugin

EXTRA_FLASK_APP_CONFIG = {
    'S3_EXPORT_PLUGIN': SupersetS3ExportPlugin()
}

S3_EXPORT_CONFIG = {
    'AWS_ACCESS_KEY_ID': 'xxx',
    'AWS_SECRET_ACCESS_KEY': 'xxx',
    'S3_BUCKET': 'superset-exports',
    'S3_ENDPOINT_URL': 'https://garage.yourdomain.com',  # For Garage
    'EXPIRY_HOURS': 24,
    'RESEND_API_KEY': 'xxx',
    'FROM_EMAIL': 'noreply@yourdomain.com',
}

class CeleryConfig:
    imports = ('superset.sql_lab', 'superset_s3_export.tasks')

CELERY_CONFIG = CeleryConfig
```

---

## API Quick Reference

### Create Export Job
```bash
POST /api/v1/s3-export/create
Authorization: Bearer <token>
Content-Type: application/json

{
  "datasource_id": 123,
  "datasource_type": "table",
  "sql_query": "SELECT * FROM table WHERE ...",
  "dataset_name": "Sales Report"
}
```

**Response:**
```json
{
  "job_id": "abc-123",
  "status": "pending",
  "message": "Export queued! Check your email."
}
```

### Check Status (Optional)
```bash
GET /api/v1/s3-export/status/<job_id>
```

---

## Testing Quick Reference

### Run Tests
```bash
# All tests
pytest

# With coverage
pytest --cov=superset_s3_export

# Specific test
pytest tests/test_models.py -v

# Watch mode
pytest-watch
```

### Format & Lint
```bash
# Format
black superset_s3_export/

# Lint
ruff check superset_s3_export/

# Auto-fix
ruff check --fix superset_s3_export/

# Type check
mypy superset_s3_export/
```

---

## Database Quick Reference

### Migration
```bash
# Run migration
superset db upgrade

# Check table created
psql -d superset -c "\d s3_export_jobs"

# Check jobs
psql -d superset -c "SELECT id, status, dataset_name FROM s3_export_jobs ORDER BY created_at DESC LIMIT 5;"
```

### Table Schema
```sql
s3_export_jobs
├── id (uuid, pk)
├── user_id (int, fk)
├── user_email (varchar)
├── dataset_name (varchar)
├── status (enum: pending/processing/completed/failed)
├── s3_key (varchar)
├── download_url (text)
├── file_size (bigint)
├── row_count (bigint)
├── created_at (timestamp)
├── completed_at (timestamp)
├── expires_at (timestamp)
└── error_message (text)
```

---

## Troubleshooting Quick Reference

### "Failed to build python-geohash"
**Cause:** Installing plugin without existing Superset
**Fix:** Install Superset first, or use `uv pip install -e ".[dev]"` for development

### "ModuleNotFoundError: No module named 'superset'"
**Cause:** Wrong Python environment
**Fix:** Activate Superset's venv first

### "Table s3_export_jobs does not exist"
**Cause:** Migration not run
**Fix:** `superset db upgrade`

### "Celery tasks not running"
**Cause:** Celery worker not started or tasks not registered
**Fix:** 
```bash
# Start worker
celery -A superset.tasks.celery_app:app worker --loglevel=info

# Check tasks registered
celery -A superset.tasks.celery_app:app inspect registered | grep s3_export
```

### "Linter showing errors everywhere"
**Cause:** Superset not installed in dev environment
**Fix:** `uv pip install -e ".[dev]"` (installs Superset + dev tools)

---

## File Locations

### Development
- **Code:** `superset_s3_export/`
- **Tests:** `tests/`
- **Config:** `pyproject.toml`
- **Venv:** `.venv/`

### Production
- **Plugin:** Installed in Superset's site-packages
- **Config:** `/path/to/superset_config.py`
- **Logs:** `/var/log/superset/`
- **Database:** PostgreSQL (table: `s3_export_jobs`)

---

## Common Commands Cheat Sheet

```bash
# Development
uv pip install -e ".[dev]"      # Install with dev deps
pytest                           # Run tests
black .                          # Format code
ruff check .                     # Lint code
mypy superset_s3_export/        # Type check

# Production
uv pip install .                 # Install plugin
superset db upgrade              # Run migration
superset run -p 8088             # Start Superset
celery ... worker                # Start worker

# Debugging
python -c "import superset; print(superset.__version__)"
python -c "from superset_s3_export import SupersetS3ExportPlugin"
psql -d superset -c "SELECT * FROM s3_export_jobs LIMIT 5;"
```

---

## Documentation Files

- **README.md** - Overview and user guide
- **INSTALLATION.md** - Setup instructions
- **DEVELOPMENT.md** - Developer guide ← **Read this for dev setup!**
- **TROUBLESHOOTING.md** - Common issues
- **PROJECT_SUMMARY.md** - Project overview
- **This file** - Quick reference

---

## Key Differences: User vs Developer

| Aspect | End User | Plugin Developer |
|--------|----------|------------------|
| **Install** | `uv pip install` | `uv pip install -e ".[dev]"` |
| **Superset** | Already installed | Installed by `[dev]` |
| **Python headers** | Not needed | Required |
| **IDE linting** | N/A | Works after `[dev]` |
| **Tests** | Not needed | Run with `pytest` |
| **Environment** | Existing Superset venv | New `.venv` for dev |

---

## Next Steps

### For Users
1. ✅ Read INSTALLATION.md
2. ✅ Configure environment variables
3. ✅ Update superset_config.py
4. ✅ Run migration
5. ✅ Test API

### For Developers
1. ✅ Read DEVELOPMENT.md
2. ✅ Install Python dev headers
3. ✅ Install with `[dev]` dependencies
4. ✅ Run tests
5. ✅ Fix linter by pointing IDE to `.venv`

---

## Support

- **Issues:** See TROUBLESHOOTING.md
- **Development:** See DEVELOPMENT.md
- **Installation:** See INSTALLATION.md
- **GitHub:** (your repo URL)
