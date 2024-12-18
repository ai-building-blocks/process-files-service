from datetime import datetime
from dotenv import load_dotenv
from src.models.documents import SessionLocal, Document
from src.services.s3_service import S3Service

import os
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI
import uvicorn
from src.models.documents import SessionLocal, Document
from src.services.s3_service import S3Service

app = FastAPI()

async def process_files(session: SessionLocal = None):
    """Process new files once when requested"""
    if session is None:
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
    finally:
        if session:
            session.close()

@app.post("/process")
async def trigger_processing():
    """Process files endpoint with proper error handling"""
    try:
        result = await process_files()
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/files/process")
async def process_single_file(request: dict):
    """Process a single file by ID"""
    session = SessionLocal()
    s3_service = S3Service()
    
    try:
        process_id = request["process_id"]
        identifier = request["identifier"]
        identifier_type = request["identifier_type"]
            
        # Get document record by ID and verify state
        doc = session.query(Document).filter_by(id=process_id).first()
        if not doc:
            return {"status": "error", "message": "Invalid process ID"}
        
        if doc.status != "queued":
            return {"status": "error", "message": f"Invalid document state: {doc.status}. Expected: queued"}
            
        # Update status to downloading first
        doc.status = "downloading"
        session.commit()
        
        # After successful download, update to processing
        doc.status = "processing"
        doc.processing_started_at = datetime.utcnow()
        session.commit()
        
        # Create a new session for this operation
        process_session = SessionLocal()
        try:
            # Re-fetch document with new session
            doc = process_session.query(Document).filter_by(id=process_id).first()
            if not doc:
                raise ValueError(f"Document not found with ID: {process_id}")

            if identifier_type == "filename":
                # Strip prefix if present, then add it for S3 operations
                clean_filename = identifier.replace(s3_service.source_prefix, '', 1)
                file_path = f"{s3_service.source_prefix}{clean_filename}"
            else:
                # Look up original filename from database using ID
                orig_doc = process_session.query(Document).filter_by(id=identifier).first()
                if not orig_doc:
                    raise FileNotFoundError(f"No file found with ID {identifier}")
                # Add prefix for S3 operations
                file_path = f"{s3_service.source_prefix}{orig_doc.original_filename}"
            
            # Check if document already exists with full path
            existing_doc = process_session.query(Document).filter_by(original_filename=file_path).first()
            if existing_doc and existing_doc.id != process_id:
                # Update existing document instead of creating a new one
                doc.status = "duplicate"
                doc.error_message = f"Document already exists with ID: {existing_doc.id}"
                process_session.commit()
                return {"status": "error", "message": f"Document already exists with ID: {existing_doc.id}"}
            
            await s3_service.process_single_file(file_path, process_session)
            
            # Update status to uploading
            doc.status = "uploading"
            process_session.commit()
            
            # After successful upload, mark as completed
            doc.status = "completed"
            doc.processing_completed_at = datetime.utcnow()
            process_session.commit()
            
            return {"status": "success", "message": "File processed successfully"}
            
        except Exception as e:
            if doc:
                doc.status = "failed"
                doc.error_message = str(e)
                process_session.commit()
            return {"status": "error", "message": str(e)}
        finally:
            process_session.close()
    except Exception as e:
        return {"status": "error", "message": str(e)}
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
