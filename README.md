# S3 Document Processor

Automatically processes documents from S3/MinIO buckets and converts them to markdown format.

## Setup

```bash
# Install dependencies
pip install .

# Copy and edit environment variables
cp .env.template .env

# Start the API server
python -m uvicorn src.main:app --reload

# In another terminal, start the worker
python src/worker.py
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
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check .
```

## License

MIT
