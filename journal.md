# Project Journal: S3 Document Processor Service

## Project Overview
**Last Updated**: 2024-12-17  
**Project Status**: In Development  
**Current Phase**: Initial Implementation

## Timeline

### Phase 1: Initial Setup (2024-12-17) - COMPLETED
- ✅ Created initial FastAPI application structure
- ✅ Implemented basic file monitoring and processing
- ✅ Added SQLite persistence layer
- ✅ Created project structure with UV package manager

### Phase 2: S3 Configuration (2024-12-17) - COMPLETED
- ✅ Added configurable SSL verification for S3/MinIO
- ✅ Implemented configurable prefix paths
- ✅ Added prefix validation
- ✅ Improved S3 client configuration
- ✅ Added proper error handling for S3 operations

### Phase 3: API Enhancement (2024-12-17 - In Progress)
- ✅ Enhanced file processing endpoint with ID/filename support
- ✅ Added ProcessFileRequest validation model
- ✅ Improved error handling and logging
- ✅ Updated API documentation

**Key Decisions**:
- Selected FastAPI for its async capabilities and automatic OpenAPI documentation
- Chose SQLite for initial persistence layer due to simplicity
- Implemented background processing for file monitoring
- Using UV as package manager with pyproject.toml for better dependency resolution and performance
- Implemented ULID-based file naming for uniqueness and sorting capabilities
- Chose pyproject.toml over requirements.txt for modern Python packaging

**Technical Debt**:
- Need to add proper error handling for S3 operations
- File processing could be more robust
- Progress tracking needs implementation
- Need to implement proper cleanup routines

### Phase 2: Infrastructure (2024-12-17 - In Progress)
- ✅ Docker containerization with multi-stage builds
- ✅ Docker Compose setup for API and worker services
- ✅ Basic S3/MinIO integration with boto3
- ⏳ Implementing proper error handling
- ⏳ Adding monitoring and logging
- ⏳ Setting up proper health checks

**Planned Decisions**:
- Evaluating MinIO vs S3 configuration options
- Considering migration to PostgreSQL for better scalability
- Exploring structured logging implementation

## Design Decisions

### Architecture

#### API Design
**Decision**: REST API with async processing  
**Rationale**: 
- Long-running file processing jobs require async processing
- REST provides familiar interface for clients
- AsyncIO in FastAPI enables efficient handling of multiple requests
- ULID-based file naming enables natural temporal ordering

#### Storage Strategy
**Current**: S3/MinIO + SQLite  
**Planned**: S3/MinIO + PostgreSQL  
**Rationale**:
- Started with SQLite for simplicity
- S3/MinIO provides scalable object storage
- PostgreSQL will enable better querying and concurrent access
- Keeping processed files in both S3 and local storage for redundancy

#### Security
**Implemented**:
- Basic input validation
- Environment-based configuration
- File tracking with metadata

**Planned**:
- API key authentication
- Rate limiting
- Enhanced input sanitization
- Proper credential rotation

## Technical Specifications

### Current Implementation
```yaml
Language: Python 3.8+
Framework: FastAPI
Storage: S3/MinIO + SQLite
Processing: Background tasks
State: SQLite database
Package Manager: UV
```

### Planned Enhancements
```yaml
Storage: S3/MinIO + PostgreSQL
Authentication: API Keys
Monitoring: Structured Logging
Docker: Multi-stage build with UV package manager
Container: API and worker services with health checks
```

## Challenges & Solutions

### Challenge 1: File Tracking
**Problem**: Maintaining consistency between S3 and local storage  
**Current Solution**: SQLite database with versioning  
**Planned Improvement**: More sophisticated tracking with proper cleanup

### Challenge 2: Error Handling
**Problem**: Robust error handling for external services  
**Current Solution**: Basic error catching  
**Planned Solution**: Proper retry mechanisms and dead letter queues

## Performance Metrics

### Current Baseline
- File Processing: Not yet measured
- Memory Usage: Not yet measured
- Database Performance: Not yet measured

### Targets
- API Response Time: <100ms
- Processing Queue: <5min wait
- Success Rate: >99%

## Dependencies

### Core Dependencies
- fastapi
- uvicorn
- python-multipart
- boto3
- sqlalchemy
- python-dotenv
- ulid-py

### Future Dependencies
- psycopg2 (for PostgreSQL)
- structlog (for logging)
- prometheus-client (for metrics)

## Integration Points

### Current
- S3/MinIO for storage
- External conversion service
- SQLite database
- Background task system

### Planned
- PostgreSQL
- Monitoring systems
- Authentication service
- Webhook notifications

## Maintenance Notes

### Regular Tasks
- Clean up old files
- Update dependencies
- Check error logs
- Verify S3 bucket consistency

### Monitoring Points
- S3 storage usage
- Database size
- Processing queue length
- Error rates

## Next Steps

### Immediate (Next 2 Weeks)
1. ✅ Implement proper error handling for S3 operations
2. ✅ Add structured logging
3. Add log rotation and aggregation
4. Implement proper cleanup routines for temp files
5. Add performance metrics logging
6. Implement audit logging for sensitive operations

### Short Term (Next Month)
1. Add authentication
2. Implement rate limiting
3. Create Docker setup

### Long Term
1. Migrate to PostgreSQL
2. Add webhook support
3. Create management UI

## Open Questions

1. Best approach for handling very large files?
2. Strategy for handling service outages during long processing jobs?
3. Best practices for managing multiple file versions?
4. Optimal cleanup strategy for temporary files?

---
*Note: This document should be updated regularly as new decisions are made and implementations are completed.*
