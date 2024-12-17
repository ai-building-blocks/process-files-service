# S3 Document Pre-processor for RAG

A robust service for pre-processing documents stored in S3/MinIO buckets, specifically designed as a preparation step for Retrieval-Augmented Generation (RAG) systems. The service automatically converts various document formats to normalized markdown, tracks document versions, and maintains a clean mapping between original and processed files.

## Key Features

- **Automated Document Processing**: Monitors S3/MinIO buckets for new or modified files
- **Format Conversion**: Converts documents to markdown format for RAG compatibility
- **Version Control**: Tracks document versions and maintains history
- **File Normalization**: Standardizes filenames using ULIDs while preserving original names
- **RESTful API**: Easy integration with other services
- **Change Detection**: Efficiently processes only modified or new files
- **Incremental Updates**: Supports retrieving only recent changes based on timestamps/ULIDs

## Quick Start

1. Clone the repository

2. Install uv (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. Create and activate virtual environment:
   ```bash
   uv venv
   source .venv/bin/activate  # On Unix/MacOS
   # or
   .venv\Scripts\activate  # On Windows
   ```

4. Install dependencies:
   ```bash
   uv pip install -r requirements.txt
   ```

5. Copy `.env.template` to `.env` and configure:
   ```env
   S3_ENDPOINT=your-s3-endpoint
   S3_ACCESS_KEY=your-access-key
   S3_SECRET_KEY=your-secret-key
   SOURCE_BUCKET=your-source-bucket
   DESTINATION_BUCKET=your-destination-bucket
   CONVERTER_SERVICE_URL=http://localhost:8000/convert
   ```

6. Start the service:
   ```bash
   uvicorn src.main:app --reload
   ```

7. Start the worker (in a separate terminal):
   ```bash
   python src/worker.py
   ```

Note: Always ensure you're in the virtual environment (step 3) before running any commands. You'll know you're in the virtual environment when you see (.venv) at the start of your terminal prompt.

## API Endpoints

### List Files
```
GET /files?source=[bucket|parsed]
```
Lists files either from the source bucket or processed markdown files.

### Get File
```
GET /files/{file_id}?source=[bucket|parsed]
```
Retrieves a specific file from either source or processed storage.

### Get File Status
```
GET /files/status
```
Returns processing status and version information for all files.

### Get Updates
```
GET /files/updates?since={timestamp/ulid}
```
Returns list of files updated since the specified timestamp/ULID.

## Integration with RAG Systems

This service is designed to be used as a pre-processing step in RAG pipelines:

1. Documents are stored in a source S3 bucket
2. Service automatically processes new/modified documents
3. Processed markdown files are stored with normalized names
4. RAG system can efficiently fetch only recent updates
5. Original filenames and metadata are preserved for reference

Example workflow:
```python
# Fetch recent updates
updates = requests.get(
    "http://localhost:8080/files/updates",
    params={"since": "last_processed_ulid"}
)

# Process updated files
for file in updates.json():
    # Fetch processed markdown
    content = requests.get(
        f"http://localhost:8080/files/{file['id']}",
        params={"source": "parsed"}
    )
    # Update RAG system with new content
    rag_system.update(content.text)
```

## File Tracking

The service maintains a SQLite database (configurable) to track:
- Original filenames
- Processed ULIDs
- File versions
- Processing timestamps
- Processing status

## Configuration

- **S3/MinIO**: Configure endpoint and credentials in `.env`
- **Conversion Service**: Set external conversion service URL
- **Storage**: Configure source and destination buckets
- **Processing**: Adjust worker intervals and batch sizes
- **Database**: SQLite by default, expandable to other databases

## Monitoring

Access API documentation and monitoring at:
- Swagger UI: `http://localhost:8080/docs`
- ReDoc: `http://localhost:8080/redoc`
- Health check: `http://localhost:8080/health`

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE) for details
