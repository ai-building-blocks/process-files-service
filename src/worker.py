from dotenv import load_dotenv
from src.models.documents import SessionLocal
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
            
    @app.get("/health")
    async def health_check():
        """Health check endpoint with debug info"""
        return {
            "status": "healthy",
            "worker_port": os.getenv("WORKER_PORT", 8081),
            "host": "0.0.0.0"
        }
    
    uvicorn.run(
        app, 
        host="0.0.0.0",  # Always bind to all interfaces in container
        port=int(os.getenv("WORKER_PORT", 8081)),
        log_level="info"
    )
