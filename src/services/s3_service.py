import boto3
import urllib3
from botocore.config import Config
from botocore.exceptions import ClientError
from ..utils.logging import get_logger, log_api_error, log_s3_operation
import os
import tempfile
import requests
import ulid
from datetime import datetime
from sqlalchemy.orm import Session
from src.models.documents import Document

class S3Service:
    def __init__(self):
        self.logger = get_logger(__name__)
        # Disable SSL warnings for local development
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
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
            verify=os.getenv('S3_VERIFY_SSL', 'true').lower() == 'true'
        )
        # Get prefixes from environment with validation
        self.source_prefix = self._validate_prefix(os.getenv('SOURCE_PREFIX', 'downloads/'))
        self.destination_prefix = self._validate_prefix(os.getenv('DESTINATION_PREFIX', 'processed/'))

    def _validate_prefix(self, prefix: str) -> str:
        """Validate and normalize S3 prefix format"""
        if not prefix:
            raise ValueError("Prefix cannot be empty")
        
        # Ensure prefix ends with forward slash
        if not prefix.endswith('/'):
            prefix += '/'
            
        # Remove leading slash if present
        if prefix.startswith('/'):
            prefix = prefix[1:]
            
        return prefix
        
    async def list_files(self, session: Session = None, since: str = None):
        """List files from source bucket with accurate processing status"""
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=os.getenv('SOURCE_BUCKET'),
                Prefix=self.source_prefix
            )
            
            files = []
            contents = response.get('Contents', [])
            
            # Filter by timestamp/ULID if provided
            if since:
                try:
                    # Try parsing as ULID first
                    since_ts = ulid.parse(since).timestamp()
                except ValueError:
                    # Parse as ISO timestamp
                    since_ts = datetime.fromisoformat(since.replace('Z', '+00:00')).timestamp()
                
                contents = [obj for obj in contents if obj['LastModified'].timestamp() >= since_ts]
                
            for obj in contents:
                # Check if file has been processed by looking up in database
                status = "unprocessed"
                if session:
                    doc = session.query(Document).filter_by(
                        original_filename=obj['Key']
                    ).first()
                    if doc:
                        status = "processed"
                
                # Remove source prefix from filename
                filename = obj['Key'].replace(self.source_prefix, '', 1)
                files.append({
                    "id": str(ulid.new()),
                    "filename": filename,
                    "status": status
                })
            return files
        except Exception as e:
            raise Exception(f"Error listing bucket files: {str(e)}")

    async def list_processed_files(self, session: Session, since: str = None):
        """List processed files with their status"""
        try:
            query = session.query(Document)
            
            if since:
                try:
                    # Try parsing as ULID first
                    since_ts = datetime.fromtimestamp(ulid.parse(since).timestamp())
                except ValueError:
                    # Parse as ISO timestamp
                    since_ts = datetime.fromisoformat(since.replace('Z', '+00:00'))
                
                query = query.filter(Document.created_at >= since_ts)
                
            docs = query.all()
            return [{
                "id": doc.id,
                "filename": doc.processed_filename,
                "status": "processed"
            } for doc in docs]
        except Exception as e:
            raise Exception(f"Error listing processed files: {str(e)}")

    async def process_new_files(self, session: Session):
        """Process all new files in the source bucket"""
        objects = self.s3_client.list_objects_v2(
            Bucket=os.getenv('SOURCE_BUCKET'),
            Prefix=self.source_prefix
        )
        
        for obj in objects.get('Contents', []):
            await self.process_single_file(obj['Key'], session)

    async def process_single_file(self, file_id: str, session: Session):
        """Process a specific file by its ID"""
        try:
            log_s3_operation(self.logger, "head_object", {"file_id": file_id})
            
            try:
                obj = self.s3_client.head_object(
                    Bucket=os.getenv('SOURCE_BUCKET'),
                    Key=file_id
                )
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    log_api_error(self.logger, e, {
                        "file_id": file_id,
                        "bucket": os.getenv('SOURCE_BUCKET'),
                        "operation": "head_object"
                    })
                    raise FileNotFoundError(f"File {file_id} not found in bucket {os.getenv('SOURCE_BUCKET')}")
                log_api_error(self.logger, e, {
                    "file_id": file_id,
                    "bucket": os.getenv('SOURCE_BUCKET'),
                    "operation": "head_object",
                    "error_code": e.response['Error']['Code']
                })
                raise
            
            # Check if already processed
            doc = session.query(Document).filter_by(
                original_filename=file_id
            ).order_by(Document.created_at.desc()).first()
            
            if doc and doc.s3_last_modified >= obj['LastModified']:
                return {"status": "skipped", "message": "File already processed"}
            
            # Process the file
            await self._process_file({"Key": file_id, "LastModified": obj['LastModified']}, session)
            return {"status": "success", "message": "File processed successfully"}
            
        except self.s3_client.exceptions.NoSuchKey:
            raise Exception(f"File {file_id} not found in bucket")
        except Exception as e:
            raise Exception(f"Error processing file {file_id}: {str(e)}")
    
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
