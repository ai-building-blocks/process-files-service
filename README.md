# S3 Document Processor

Automatically processes documents from S3/MinIO buckets and converts them to markdown format. This service provides a robust API for managing document processing with real-time status tracking.

## Features

- 🚀 Automatic document processing from S3/MinIO
- 📝 Markdown conversion with status tracking
- 🔄 Real-time processing status updates
- 🌐 RESTful API with OpenAPI documentation
- 🐳 Docker support with multi-container setup
- 📊 File listing and status monitoring
- ⚡ Async processing for better performance

## Quick Start with Docker

1. **Setup Environment**
```bash
# Copy and edit environment variables
cp .env.template .env

# Configure your S3/MinIO credentials in .env:
S3_ENDPOINT=http://localhost:9000  # Use your MinIO endpoint
S3_ACCESS_KEY=your_access_key
S3_SECRET_KEY=your_secret_key
SOURCE_BUCKET=source-docs
DESTINATION_BUCKET=processed-docs
S3_USE_PATH_STYLE=true  # Required for MinIO/path-style S3 endpoints
S3_VERIFY_SSL=false     # Disable SSL verification for local development
SOURCE_PREFIX=downloads/      # Source folder prefix for documents
DESTINATION_PREFIX=processed/ # Destination folder for processed files

# Create required buckets and folders in MinIO:
mc alias set myminio http://localhost:9000 your_access_key your_secret_key
mc mb myminio/source-docs
mc mb myminio/processed-docs
```

2. **Start Services**
```bash
# Build and start services
docker compose up --build -d

# View logs
docker compose logs -f
```

3. **Verify Setup**
```bash
# Check if services are running
docker compose ps

# Test API health
curl http://localhost:8070/health

# View API documentation
open http://localhost:8070/docs
```

## Testing the Setup

1. **Check API Connection**
```bash
# Health check
curl http://localhost:8070/health
# Expected: {"status": "healthy"}

# List files
curl http://localhost:8070/api/files?source=bucket
# Lists files in source bucket

curl http://localhost:8070/api/files?source=parsed
# Lists processed files
```

2. **Monitor Processing**
```bash
# Check processing status
curl http://localhost:8070/api/files/status
# Shows status of all files

# Trigger processing
curl -X POST http://localhost:8070/api/process
# Starts processing of new files
```

3. **View Processed Files**
```bash
# Get specific file details
curl http://localhost:8070/api/files/{file_id}?source=parsed
```

## Manual Setup

If you prefer to run without Docker:

1. **Install Dependencies**
```bash
# Install uv package manager
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create and activate virtual environment
uv venv
source .venv/bin/activate  # On Unix/MacOS
. .venv/Scripts/activate   # On Windows

# Install package
uv pip install -e ".[dev]"
```

2. **Start Services**
```bash
# Start API server
python -m uvicorn src.main:app --host 0.0.0.0 --port 8070 --reload

# Start worker (in another terminal)
python -m src.worker
```

## API Endpoints

### File Management
- `GET /api/files?source={bucket|parsed}` - List files
  - Query params:
    - `source`: 'bucket' for source files, 'parsed' for processed files
  - Returns: List of files with status

- `GET /api/files/{file_id}?source={bucket|parsed}` - Get specific file
  - Path params:
    - `file_id`: ULID of the file
  - Query params:
    - `source`: 'bucket' or 'parsed'
  - Returns: File details

- `GET /api/files/status` - Check processing status
  - Returns: Status of all files in processing

- `POST /api/process` - Trigger file processing
  - Returns: Processing status

### System
- `GET /health` - Health check endpoint
  - Returns: Service health status

## Environment Variables

Required in `.env`:
```bash
# S3/MinIO Configuration
S3_ENDPOINT=http://minio:9000
S3_ACCESS_KEY=your_access_key
S3_SECRET_KEY=your_secret_key
SOURCE_BUCKET=source-docs
DESTINATION_BUCKET=processed-docs

# API Configuration
API_HOST=0.0.0.0
API_PORT=8070
WORKER_PORT=8071

# Service URLs
CONVERTER_SERVICE_URL=http://converter:8000/convert
WORKER_URL=http://worker:8081
```

## Development

### Running Tests
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src

# Run specific test file
pytest tests/test_api.py

# Run with verbose output
pytest -v
```

### Code Quality
```bash
# Run linter
ruff check .

# Run type checker
mypy src/

# Format code
ruff format .
```

### Local Development
```bash
# Install in editable mode with dev dependencies
uv pip install -e ".[dev]"

# Run API with auto-reload
uvicorn src.main:app --reload

# Run worker in development mode
python -m src.worker
```

## Troubleshooting

### Common Issues

1. **S3 Connection Failed**
   - Check S3_ENDPOINT in .env
   - Verify credentials
   - Ensure buckets exist

2. **Worker Not Processing**
   - Check worker logs: `docker compose logs worker`
   - Verify WORKER_URL in .env
   - Check worker health endpoint

3. **API Not Responding**
   - Check API logs: `docker compose logs api`
   - Verify ports are not in use
   - Check API_PORT in .env

### Logs
```bash
# View all logs
docker compose logs

# Follow specific service
docker compose logs -f api
docker compose logs -f worker

# View last 100 lines
docker compose logs --tail=100
```

## Contributing

1. Fork the repository
2. Create your feature branch
3. Run tests and linting
4. Submit a pull request

## License

MIT

## Support

- GitHub Issues: [Report a bug](https://github.com/yourusername/s3-document-processor/issues)
- Documentation: See `/docs` endpoint when running
