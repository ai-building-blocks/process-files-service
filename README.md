# S3 Document Processor

Automatically processes documents from S3/MinIO buckets and converts them to markdown format.

## Quick Start with Docker

```bash
# Copy and edit environment variables
cp .env.template .env

# Build and start services
docker compose up -d

# View logs
docker compose logs -f
```

The API will be available at http://localhost:8080/docs

## Manual Setup

If you prefer to run without Docker:

```bash
# Install dependencies using uv
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv
source .venv/bin/activate  # On Unix/MacOS
uv pip install .

# Start the services
python -m uvicorn src.main:app --reload
python src/worker.py  # In another terminal
```

## Environment Variables

Required in `.env`:
- `S3_ENDPOINT` - S3 or MinIO endpoint URL
- `S3_ACCESS_KEY` - Access key
- `S3_SECRET_KEY` - Secret key
- `SOURCE_BUCKET` - Source bucket name
- `DESTINATION_BUCKET` - Destination bucket name
- `CONVERTER_SERVICE_URL` - Document converter service URL

## API Endpoints

- `GET /files` - List files (source=bucket|parsed)
- `GET /files/{id}` - Get specific file
- `GET /files/status` - Check processing status

Full API docs available at `/docs` when running.

## Development

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check .

# Build Docker image
docker build -t s3-document-processor .
```

## Docker Commands

```bash
# Build image
docker build -t s3-document-processor .

# Run API server
docker run -p 8080:8080 --env-file .env s3-document-processor api

# Run worker
docker run --env-file .env s3-document-processor worker

# Run with docker compose (recommended)
docker compose up -d
```

## License

MIT
