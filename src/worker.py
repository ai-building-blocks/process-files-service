import asyncio
from dotenv import load_dotenv
from models.documents import SessionLocal
from services.s3_service import S3Service

async def process_files():
    load_dotenv()
    session = SessionLocal()
    s3_service = S3Service()
    
    while True:
        try:
            await s3_service.process_new_files(session)
        except Exception as e:
            print(f"Error processing files: {e}")
        
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(process_files())
