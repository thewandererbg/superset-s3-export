# Development Setup Guide

This guide is for **developers** working on the plugin itself, not for end-users installing it.

## Two Installation Modes

### 1. Production Installation (End Users)
```bash
# Users install plugin into existing Superset
source /path/to/superset/venv/bin/activate
uv pip install superset-s3-export
```

### 2. Development Installation (Plugin Developers)
```bash
# Developers install plugin + Superset + dev tools
cd superset-s3-export
uv pip install -e ".[dev]"
```

## Development Environment Setup

### Prerequisites

**Install Python development headers** (required for building Superset's C extensions):

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y \
    python3-dev \
    python3.12-dev \
    build-essential \
    gcc \
    g++ \
    libpq-dev \
    libssl-dev

# Fedora/RHEL
sudo dnf install -y \
    python3-devel \
    python3.12-devel \
    gcc \
    gcc-c++ \
    postgresql-devel \
    openssl-devel

# macOS
xcode-select --install
brew install postgresql openssl
```

### Step-by-Step Setup

**1. Clone/Extract the plugin:**
```bash
cd superset-s3-export
```

**2. Create virtual environment:**
```bash
# Create venv
python3.12 -m venv .venv

# Activate
source .venv/bin/activate

# Verify Python version
python --version  # Should be 3.12.x
```

**3. Install plugin with dev dependencies:**
```bash
# This installs: plugin + Superset + pytest + black + ruff + mypy
uv pip install -e ".[dev]"

# This will take 5-10 minutes as it builds Superset's C extensions
```

**4. Verify installation:**
```bash
# Check Superset installed
python -c "import superset; print(f'Superset {superset.__version__}')"

# Check plugin installed
python -c "from superset_s3_export import SupersetS3ExportPlugin; print('✓ Plugin OK')"

# Check dev tools installed
ruff --version
pytest --version
```

### Fix Linter Errors

After installing with `[dev]` dependencies, your linter should work properly:

**VS Code (Pylance):**
```json
// .vscode/settings.json
{
    "python.analysis.extraPaths": [
        ".venv/lib/python3.12/site-packages"
    ],
    "python.defaultInterpreterPath": ".venv/bin/python"
}
```

**PyCharm:**
1. File → Settings → Project → Python Interpreter
2. Select `.venv/bin/python`
3. Restart IDE

**Vim/Neovim (with pyright):**
```bash
# Ensure pyright uses the venv
export VIRTUAL_ENV="$(pwd)/.venv"
```

## Development Workflow

### 1. Make Code Changes

Edit any file in `superset_s3_export/`:
- `models.py`
- `tasks.py`
- `blueprint.py`
- `email.py`

### 2. Format Code

```bash
# Format with black
black superset_s3_export/

# Lint with ruff
ruff check superset_s3_export/

# Auto-fix issues
ruff check --fix superset_s3_export/
```

### 3. Type Check

```bash
# Run mypy
mypy superset_s3_export/
```

### 4. Test Changes

**Quick manual test:**
```bash
# Start Python REPL
python

>>> from superset_s3_export import SupersetS3ExportPlugin
>>> plugin = SupersetS3ExportPlugin()
>>> print(plugin.name)
'S3 Export Plugin'
```

**Test imports work:**
```bash
python -c "
from superset_s3_export.models import ExportJob, ExportStatus
from superset_s3_export.tasks import process_export
from superset_s3_export.blueprint import s3_export_blueprint
from superset_s3_export.email import send_export_email
print('✓ All imports work')
"
```

### 5. Run Tests (when you write them)

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=superset_s3_export --cov-report=html

# Run specific test file
pytest tests/test_models.py

# Run with verbose output
pytest -v
```

## Testing with Real Superset

### Setup Test Superset Instance

**1. Initialize Superset database:**
```bash
# Set environment variables
export SUPERSET_CONFIG_PATH=$(pwd)/test_superset_config.py
export FLASK_APP=superset

# Create database
superset db upgrade

# Create admin user
superset fab create-admin \
    --username admin \
    --firstname Admin \
    --lastname User \
    --email admin@example.com \
    --password admin

# Initialize
superset init
```

**2. Create test config:**
```bash
cat > test_superset_config.py << 'EOF'
import os
from superset_s3_export import SupersetS3ExportPlugin

# Basic Superset config
SECRET_KEY = 'test_secret_key_change_in_production'
SQLALCHEMY_DATABASE_URI = 'postgresql://superset:superset@localhost/superset_test'

# Register plugin
EXTRA_FLASK_APP_CONFIG = {
    'S3_EXPORT_PLUGIN': SupersetS3ExportPlugin()
}

# S3 Export config (use test values)
S3_EXPORT_CONFIG = {
    'AWS_ACCESS_KEY_ID': os.getenv('TEST_AWS_ACCESS_KEY_ID', 'test'),
    'AWS_SECRET_ACCESS_KEY': os.getenv('TEST_AWS_SECRET_ACCESS_KEY', 'test'),
    'S3_BUCKET': 'test-bucket',
    'S3_ENDPOINT_URL': 'http://localhost:9000',  # Local MinIO
    'EXPIRY_HOURS': 1,
    'RESEND_API_KEY': os.getenv('TEST_RESEND_API_KEY', 'test'),
    'FROM_EMAIL': 'test@example.com',
}

# Celery config
class CeleryConfig:
    broker_url = 'redis://localhost:6379/0'
    result_backend = 'redis://localhost:6379/0'
    imports = ('superset.sql_lab', 'superset_s3_export.tasks')

CELERY_CONFIG = CeleryConfig
EOF
```

**3. Run test Superset:**
```bash
# Terminal 1: Start Superset
superset run -p 8088 --with-threads --reload --debugger

# Terminal 2: Start Celery worker
celery -A superset.tasks.celery_app:app worker --loglevel=debug

# Terminal 3: Test API
curl http://localhost:8088/api/v1/s3-export/status/test
```

## Testing with Mock Services

For development without external dependencies:

**1. Mock S3 with MinIO:**
```bash
# Run MinIO locally
docker run -p 9000:9000 -p 9001:9001 \
    -e MINIO_ROOT_USER=minioadmin \
    -e MINIO_ROOT_PASSWORD=minioadmin \
    minio/minio server /data --console-address ":9001"

# Create bucket
pip install minio
python << EOF
from minio import Minio
client = Minio('localhost:9000',
    access_key='minioadmin',
    secret_key='minioadmin',
    secure=False)
client.make_bucket('test-bucket')
print('✓ Bucket created')
EOF
```

**2. Mock Resend emails:**
```bash
# Use MailHog for local email testing
docker run -d -p 1025:1025 -p 8025:8025 mailhog/mailhog

# Update email.py temporarily to use SMTP instead of Resend
# Or just skip email sending in tests
```

## Debugging

### Enable Debug Logging

```python
# In test_superset_config.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Debug Celery Task

```python
# Run task synchronously for debugging
from superset_s3_export.tasks import process_export

result = process_export(
    job_id='test-job-id',
    datasource_id=1,
    datasource_type='table',
    sql_query='SELECT 1',
    user_id=1,
    config={...},
)
print(result)
```

### Debug with pdb

```python
# Add breakpoint in code
import pdb; pdb.set_trace()

# Or use Python 3.7+ breakpoint()
breakpoint()
```

## Common Development Issues

### Issue: "ModuleNotFoundError: No module named 'superset'"

**Solution:**
```bash
# Make sure you installed with [dev]
uv pip install -e ".[dev]"

# Verify
python -c "import superset; print('OK')"
```

### Issue: Red squiggly lines in IDE

**Solution:**
1. Ensure `[dev]` dependencies installed
2. Point IDE to `.venv/bin/python`
3. Restart IDE/language server

### Issue: "Failed to build python-geohash"

**Solution:**
```bash
# Install Python dev headers (see Prerequisites above)
sudo apt-get install python3-dev python3.12-dev build-essential

# Then reinstall
uv pip install -e ".[dev]"
```

### Issue: Imports work but types not resolved

**Solution:**
```bash
# Install type stubs
uv pip install types-requests types-boto3

# Or generate stubs
stubgen -p superset_s3_export -o stubs/
```

## Contributing

### Before Committing

```bash
# Format code
black superset_s3_export/

# Lint
ruff check superset_s3_export/

# Type check
mypy superset_s3_export/

# Run tests
pytest
```

### Commit Message Format

```
type(scope): brief description

Longer description if needed.

Fixes #123
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

## IDE Configuration

### VS Code

```json
// .vscode/settings.json
{
    "python.defaultInterpreterPath": ".venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.ruffEnabled": true,
    "python.formatting.provider": "black",
    "editor.formatOnSave": true,
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": ["tests"]
}
```

### PyCharm

1. Settings → Project → Python Interpreter → Add → Virtualenv Environment
2. Select `.venv`
3. Settings → Tools → Python Integrated Tools → Testing: pytest
4. Settings → Tools → Black → Enable
5. Settings → Editor → Inspections → Python → Enable type checking

## Summary

**For development:**
```bash
# 1. Install Python dev headers
sudo apt-get install python3-dev build-essential

# 2. Create venv
python3.12 -m venv .venv
source .venv/bin/activate

# 3. Install with dev dependencies
uv pip install -e ".[dev]"

# 4. Verify
python -c "import superset; from superset_s3_export import SupersetS3ExportPlugin"
```

**For production users:**
```bash
# Just install into existing Superset environment
source /path/to/superset/venv/bin/activate
uv pip install superset-s3-export
```

Now your linter should work! 🎉
