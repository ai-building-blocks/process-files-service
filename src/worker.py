from datetime import datetime
from dotenv import load_dotenv
from src.models.documents import SessionLocal, Document
from src.services.s3_service import S3Service

async def process_files():
    """Process new files once when requested"""
    load_dotenv()
    session = SessionLocal()
    s3_service = S3Service()
    
    try:
        # Validate environment
        required_vars = ['DATA_DIR', 'TEMP_DIR', 'PROCESSED_DIR', 'DATABASE_URL']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
            
        # Ensure directories exist
        for dir_var in ['DATA_DIR', 'TEMP_DIR', 'PROCESSED_DIR']:
            dir_path = os.getenv(dir_var)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
                
        result = await s3_service.process_new_files(session)
        return {"status": "success", "message": "Files processed", "details": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    # Worker now waits for API requests instead of running continuously
    import os
    import uvicorn
    from fastapi import FastAPI

    app = FastAPI()
    
    @app.post("/process")
    async def trigger_processing():
        """Process files endpoint with proper error handling"""
        try:
            result = await process_files()
            return result
        except Exception as e:
            return {"status": "error", "message": str(e)}, 500
            
    @app.post("/files/process")
    async def process_single_file(request: dict):
        """Process a single file by ID"""
        session = SessionLocal()
        s3_service = S3Service()
        
        try:
            process_id = request["process_id"]
            identifier = request["identifier"]
            identifier_type = request["identifier_type"]
            
            # Get document record by ID
            doc = session.query(Document).filter_by(id=process_id).first()
            if not doc:
                return {"status": "error", "message": "Invalid process ID"}
            
            # Verify document is in queued state
            if doc.status != "queued":
                return {"status": "error", "message": f"Invalid document state: {doc.status}. Expected: queued"}
                
            # Update status to processing
            doc.status = "processing"
            doc.processing_started_at = datetime.utcnow()
            session.commit()
            
            try:
                if identifier_type == "filename":
                    # Strip prefix if present, then add it for S3 operations
                    clean_filename = identifier.replace(s3_service.source_prefix, '', 1)
                    file_path = f"{s3_service.source_prefix}{clean_filename}"
                else:
                    # Look up original filename from database using ID
                    orig_doc = session.query(Document).filter_by(id=identifier).first()
                    if not orig_doc:
                        raise FileNotFoundError(f"No file found with ID {identifier}")
                    # Add prefix for S3 operations
                    file_path = f"{s3_service.source_prefix}{orig_doc.original_filename}"
                
                # Check if document already exists with full path
                existing_doc = session.query(Document).filter_by(original_filename=file_path).first()
                if existing_doc and existing_doc.id != process_id:
                    # Update existing document instead of creating a new one
                    doc.status = "duplicate"
                    doc.error_message = f"Document already exists with ID: {existing_doc.id}"
                    session.commit()
                    return {"status": "error", "message": f"Document already exists with ID: {existing_doc.id}"}
                    
                await s3_service.process_single_file(file_path, session)
                
                # Update status to completed
                doc.status = "completed"
                doc.processing_completed_at = datetime.utcnow()
                session.commit()
                
                return {"status": "success", "message": "File processed successfully"}
                
            except Exception as e:
                doc.status = "failed"
                doc.error_message = str(e)
                session.commit()
                raise
                
        except Exception as e:
            return {"status": "error", "message": str(e)}, 500
        finally:
            session.close()
            
    @app.get("/health")
    async def health_check():
        """Health check endpoint with debug info"""
        return {
            "status": "healthy",
            "worker_url": os.getenv("WORKER_URL", "http://worker:8071"),
            "host": "0.0.0.0"
        }
    
    # Get port from WORKER_URL or use default
    worker_url = os.getenv("WORKER_URL", "http://worker:8071")
    try:
        port = int(worker_url.split(":")[-1])
    except (ValueError, IndexError):
        port = 8071
        
    print(f"Starting worker service on port {port}")  # Debug log
    
    uvicorn.run(
        app, 
        host="0.0.0.0",  # Always bind to all interfaces in container
        port=port,
        log_level="info"
    )
