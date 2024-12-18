# S3 Document Processor for RAG Pipelines

A specialized document processing service that prepares content for RAG (Retrieval-Augmented Generation) pipelines by converting various document formats into markdown. This service acts as the initial transformation layer, preparing documents for subsequent processing steps such as vector embedding, graph database insertion, or other LLM-oriented storage solutions.

Following The Great Unlearning principles, this service embraces AI-first development patterns with self-contained modules, clear natural language documentation, and context-first design. The implementation prioritizes clarity and maintainability in an AI-assisted development workflow.

## Features

- 🚀 Automated document processing from S3/MinIO sources
- 📝 Intelligent markdown conversion optimized for RAG pipelines
- 🔄 Real-time processing status tracking
- 🌐 RESTful API with OpenAPI documentation
- 🐳 Docker support with multi-container setup
- 📊 Comprehensive file monitoring and status reporting
- ⚡ Asynchronous processing for high throughput
- 🔗 Designed for integration with downstream RAG components
- 🧠 AI-first architecture following The Great Unlearning principles


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
LOG_LEVEL=INFO         # Set to DEBUG for more verbose logging

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

- `POST /api/files/{identifier}/process` - Process specific file
  - Path params:
    - `identifier`: File ID (ULID) or original filename
  - Request body:
    - `identifier_type`: "id" or "filename" (default: "id")
  - Returns: Processing status and message

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

4. **Pipeline Integration Issues**
   - Verify output format matches downstream requirements
   - Check file permissions in destination bucket
   - Monitor processing queue status
   - Validate markdown output structure

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
4. Document and update following [the great unlearning principles](https://github.com/greatunlearning)
5. Submit a pull request

## The Great Unlearning Implementation

This project follows The Great Unlearning principles for AI-first development:

### Prompt-Oriented Architecture (POA)
The project structure is organized to facilitate AI interaction:
```
s3-document-processor/
├── intent.md             # Service purpose and business context
├── implementation/       # Core implementation
│   ├── api/             # API components
│   ├── worker/          # Processing worker
│   └── converter/       # Document conversion logic
├── tests/               # Self-contained test suites
├── prompts/             # Common modification scenarios
│   ├── api-changes.md
│   ├── converter-updates.md
│   └── pipeline-integration.md
└── docs/                # LLM-friendly documentation
```

### Context Window Optimization (CWO)
Each component is designed to fit within typical LLM context windows:
- API endpoints are self-contained
- Worker logic is modular
- Converter implementations are focused
- Documentation is structured in digestible sections

### Self-Regenerating Modules (SRM)
Components are designed for AI modification:
- Clear business rules in natural language
- Explicit dependencies
- Self-contained validation
- Minimal external coupling

### LLM-Friendly Documentation Pattern (LFDP)
Documentation serves both human and AI readers:
- Natural language descriptions
- Implementation examples
- Common modification scenarios
- Integration patterns
- Test cases

### Context-First Design (CFD)
Each module contains complete context:
- Business requirements
- Technical constraints
- Integration points
- Validation rules

### Prompt-Driven Testing (PDT)
Tests are designed for AI maintenance:
- Natural language scenarios
- Complete context
- Clear boundaries
- Generatable test cases

The project structure and documentation follow these patterns to ensure effective collaboration between human developers and AI assistants. This approach facilitates easier maintenance, updates, and extensions of the service while maintaining high code quality and system reliability.

For more information about The Great Unlearning principles and their implementation in this project, see [`the great unlearning repo`](https://github.com/greatunlearning).

## Testing

### Running the Test Script

The repository includes a shell script for testing file processing:

```bash
# Make the script executable
chmod +x process_file.sh

# Process a specific file
./process_file.sh your_file.pdf
```

The script will:
1. Submit the file for processing
2. Monitor the processing status
3. Show progress updates
4. Exit with success (0) or failure (1)

Example output:
```
Triggering processing for file: test.pdf
Process ID: 01HKG2J5NXMY8ZRQW3B6MVRW4N
Status: downloading
Still processing...
Status: processing
Still processing...
Status: completed
Processing completed successfully
```

### Manual Testing

You can also test the API endpoints directly:

1. **Submit a file for processing**
```bash
curl -X POST "http://localhost:8070/api/files/test.pdf/process" \
     -H "Content-Type: application/json" \
     -d '{"identifier_type": "filename"}'
```

2. **Check processing status**
```bash
curl "http://localhost:8070/api/files/{process_id}/status"
```

3. **List all files**
```bash
curl "http://localhost:8070/api/files?source=bucket"
```

4. **View processing status for all files**
```bash
curl "http://localhost:8070/api/status"
```

### Common Test Cases

1. **Happy Path**
   - Upload supported file types
   - Process files of varying sizes
   - Check successful conversion

2. **Error Handling**
   - Submit unsupported file types
   - Test with missing files
   - Check timeout behavior
   - Verify error messages

3. **Edge Cases**
   - Very large files
   - Files with special characters
   - Concurrent processing requests
   - Network interruptions

### Automated Testing

For automated testing, use pytest:

```bash
# Install test dependencies
uv pip install pytest pytest-asyncio pytest-cov

# Run all tests
pytest

# Run with coverage
pytest --cov=src

# Run specific test file
pytest tests/test_api.py
```

### Performance Testing

Monitor system performance during processing:

1. **Resource Usage**
```bash
# Watch Docker container stats
docker stats

# Monitor specific container
docker stats api worker
```

2. **Processing Times**
```bash
# Time the processing script
time ./process_file.sh test.pdf
```

3. **Concurrent Load**
```bash
# Process multiple files simultaneously
for file in *.pdf; do
    ./process_file.sh "$file" &
done
wait
```

### Troubleshooting Tests

If tests fail:

1. Check logs:
```bash
docker compose logs api
docker compose logs worker
```

2. Verify services:
```bash
docker compose ps
curl http://localhost:8070/health
```

3. Check file permissions:
```bash
ls -l data/temp/
ls -l data/processed/
```

4. Validate S3 access:
```bash
mc ls myminio/source-docs
mc ls myminio/processed-docs
```

## License

MIT

## Support

- GitHub Issues: [Report a bug](https://github.com/ai-building-blocks/process-files-service/issues)
- Documentation: See `/docs` endpoint when running
- Integration Support: See architecture documentation in `/docs/architecture.md`
- Pipeline Configuration: Review `/docs/pipeline-setup.md` for RAG integration details

## Current Status

See [todo.md](todo.md) for current development tasks and [journal.md](journal.md) for detailed progress.

Known Limitations:
- Duplicate file processing needs optimization with change detection
- State transitions need proper handling for edge cases
- Last processed tracking needed for incremental processing
- See todo.md for planned improvements
