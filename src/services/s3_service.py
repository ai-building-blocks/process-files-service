import boto3
from botocore.config import Config
import os
import tempfile
import requests
import ulid
from datetime import datetime
from sqlalchemy.orm import Session
from src.models.documents import Document

class S3Service:
    def __init__(self):
        endpoint_url = os.getenv('S3_ENDPOINT')
        if not endpoint_url:
            raise ValueError("S3_ENDPOINT environment variable is required")
            
        # Ensure endpoint includes API port for MinIO (typically :9000)
        if ':' not in endpoint_url:
            endpoint_url = f"{endpoint_url}:9000"
            
        config = Config(
            s3={'addressing_style': 'path' if os.getenv('S3_USE_PATH_STYLE', 'true').lower() == 'true' else 'auto'},
            connect_timeout=5,
            retries={'max_attempts': 3}
        )
            
        self.s3_client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=os.getenv('S3_ACCESS_KEY'),
            aws_secret_access_key=os.getenv('S3_SECRET_KEY'),
            config=config,
            verify=False  # For local MinIO instances
        )
        self.source_prefix = os.getenv('SOURCE_PREFIX', 'downloads/')
        self.destination_prefix = os.getenv('DESTINATION_PREFIX', 'processed/')
        
    async def list_files(self, session: Session = None):
        """List files from source bucket with accurate processing status"""
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=os.getenv('SOURCE_BUCKET'),
                Prefix=self.source_prefix
            )
            
            files = []
            for obj in response.get('Contents', []):
                # Check if file has been processed by looking up in database
                status = "unprocessed"
                if session:
                    doc = session.query(Document).filter_by(
                        original_filename=obj['Key']
                    ).first()
                    if doc:
                        status = "processed"
                
                files.append({
                    "id": str(ulid.new()),
                    "filename": obj['Key'],
                    "status": status
                })
            return files
        except Exception as e:
            raise Exception(f"Error listing bucket files: {str(e)}")

    async def list_processed_files(self, session: Session):
        """List processed files with their status"""
        try:
            docs = session.query(Document).all()
            return [{
                "id": doc.id,
                "filename": doc.processed_filename,
                "status": "processed"
            } for doc in docs]
        except Exception as e:
            raise Exception(f"Error listing processed files: {str(e)}")

    async def process_new_files(self, session: Session):
        objects = self.s3_client.list_objects_v2(
            Bucket=os.getenv('SOURCE_BUCKET'),
            Prefix=self.source_prefix
        )
        
        for obj in objects.get('Contents', []):
            doc = session.query(Document).filter_by(
                original_filename=obj['Key']
            ).order_by(Document.created_at.desc()).first()
            
            if not doc or doc.s3_last_modified < obj['LastModified']:
                await self._process_file(obj, session)
    
    async def _process_file(self, obj, session: Session):
        with tempfile.NamedTemporaryFile() as tmp:
            self.s3_client.download_file(
                os.getenv('SOURCE_BUCKET'),
                obj['Key'],
                tmp.name
            )
            
            files = {'file': open(tmp.name, 'rb')}
            response = requests.post(
                os.getenv('CONVERTER_SERVICE_URL'),
                files=files
            )
            
            if response.status_code == 200:
                content = response.json()['markdown_content']
                file_id = str(ulid.new())
                
                # Save locally
                os.makedirs('data/processed', exist_ok=True)
                with open(f'data/processed/{file_id}.md', 'w') as f:
                    f.write(content)
                
                # Save to destination folder
                destination_key = f"{self.destination_prefix}{file_id}.md"
                self.s3_client.put_object(
                    Bucket=os.getenv('SOURCE_BUCKET'),
                    Key=destination_key,
                    Body=content
                )
                
                # Update database
                doc = Document(
                    id=file_id,
                    original_filename=obj['Key'],
                    processed_filename=f'{file_id}.md',
                    version='1.0',
                    s3_last_modified=obj['LastModified']
                )
                session.add(doc)
                session.commit()
