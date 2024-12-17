import boto3
import io
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
from typing import Dict
from src.models.documents import Document

class S3Service:
    def __init__(self):
        self.logger = get_logger(__name__)
        # Disable SSL warnings for local development
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Validate required environment variables
        self.endpoint_url = os.getenv('S3_ENDPOINT')
        self.source_bucket = os.getenv('SOURCE_BUCKET')
        self.access_key = os.getenv('S3_ACCESS_KEY')
        self.secret_key = os.getenv('S3_SECRET_KEY')
        
        if not self.endpoint_url:
            raise ValueError("S3_ENDPOINT environment variable is required")
        if not self.source_bucket:
            raise ValueError("SOURCE_BUCKET environment variable is required")
        if not self.access_key or not self.secret_key:
            raise ValueError("S3_ACCESS_KEY and S3_SECRET_KEY environment variables are required")
            
        # Ensure endpoint includes API port for MinIO (typically :9000)
        if ':' not in self.endpoint_url:
            self.endpoint_url = f"{self.endpoint_url}:9000"
            
        config = Config(
            s3={'addressing_style': 'path' if os.getenv('S3_USE_PATH_STYLE', 'true').lower() == 'true' else 'auto'},
            connect_timeout=5,
            retries={'max_attempts': 3}
        )
            
        self.s3_client = boto3.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=os.getenv('S3_ACCESS_KEY'),
            aws_secret_access_key=os.getenv('S3_SECRET_KEY'),
            config=config,
            verify=os.getenv('S3_VERIFY_SSL', 'true').lower() == 'true'
        )
        
        # Validate bucket access and create if needed
        try:
            # First try to list bucket contents to verify full access
            self.s3_client.list_objects_v2(
                Bucket=self.source_bucket,
                MaxKeys=1
            )
            self.logger.info(f"Successfully connected to bucket '{self.source_bucket}' with full access")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_msg = e.response['Error'].get('Message', '')
            if error_code == '403':
                self.logger.error(f"Access denied to bucket '{self.source_bucket}'. Error: {error_msg}")
                self.logger.error("Current credentials and configuration:")
                self.logger.error(f"Access Key: {self.access_key[:4]}...{self.access_key[-4:]}")
                self.logger.error(f"Endpoint: {self.endpoint_url}")
                self.logger.error(f"Bucket: {self.source_bucket}")
                self.logger.error(f"Source Prefix: {self.source_prefix}")
                self.logger.error(f"Path Style: {os.getenv('S3_USE_PATH_STYLE', 'true')}")
                self.logger.error(f"Verify SSL: {os.getenv('S3_VERIFY_SSL', 'true')}")
                
                # Try to get bucket policy to check permissions
                try:
                    policy = self.s3_client.get_bucket_policy(Bucket=self.source_bucket)
                    self.logger.error(f"Current bucket policy: {policy}")
                except:
                    self.logger.error("Unable to retrieve bucket policy")
                
                raise PermissionError(
                    f"Access denied to bucket '{self.source_bucket}'. "
                    f"Error: {error_msg}. "
                    "Please verify:\n"
                    "1. S3 credentials are correct\n"
                    "2. Bucket exists and is accessible\n"
                    "3. IAM/bucket policy allows s3:ListBucket and s3:GetObject\n"
                    "4. Endpoint URL and SSL settings are correct"
                )
            elif error_code == '404':
                self.logger.warning(f"Bucket '{self.source_bucket}' does not exist, attempting to create...")
                try:
                    self.s3_client.create_bucket(Bucket=self.source_bucket)
                    self.logger.info(f"Successfully created bucket '{self.source_bucket}'")
                except ClientError as create_error:
                    self.logger.error(f"Failed to create bucket: {str(create_error)}")
                    raise ValueError(f"Cannot create bucket '{self.source_bucket}'. Error: {str(create_error)}")
            else:
                self.logger.error(f"S3 error: {error_code} - {error_msg}")
                raise
                
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
                Bucket=self.source_bucket,
                Prefix=self.source_prefix
            )
            self.logger.debug(f"Listed {len(response.get('Contents', []))} objects in {self.source_bucket}/{self.source_prefix}")
            
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
                # Check if document exists in database
                doc = session.query(Document).filter_by(
                    original_filename=obj['Key']
                ).first() if session else None
                
                files.append({
                    "id": doc.id if doc else str(ulid.new()),
                    "filename": filename,
                    "status": status
                })
            return files
        except Exception as e:
            raise Exception(f"Error listing bucket files: {str(e)}")

    async def get_files_status(self, session: Session) -> Dict[str, str]:
        """Get processing status for all files in the system"""
        try:
            # Get all documents from database
            docs = session.query(Document).all()
            
            # Build status dictionary
            status = {}
            for doc in docs:
                status[doc.original_filename] = "processed"
                
            # Check source bucket for unprocessed files
            response = self.s3_client.list_objects_v2(
                Bucket=self.source_bucket,
                Prefix=self.source_prefix
            )
            
            for obj in response.get('Contents', []):
                if obj['Key'] not in status:
                    status[obj['Key']] = "unprocessed"
                    
            return status
        except Exception as e:
            self.logger.error(f"Error getting files status: {str(e)}")
            raise
            
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
            Bucket=self.source_bucket,
            Prefix=self.source_prefix
        )
        
        for obj in objects.get('Contents', []):
            await self.process_single_file(obj['Key'], session)

    async def process_single_file(self, file_id: str, session: Session):
        """Process a specific file by its ID"""
        try:
            log_s3_operation(self.logger, "get_object", {"file_id": file_id})
            
            try:
                # Try to get the object directly instead of head_object
                response = self.s3_client.get_object(
                    Bucket=self.source_bucket,
                    Key=file_id
                )
                
                # Read the content and metadata
                content = response['Body'].read()
                last_modified = response['LastModified']
                self.logger.info(f"Successfully downloaded file {file_id}, size: {len(content)} bytes")
                
                # Store metadata for later use
                file_metadata = {
                    "Key": file_id,
                    "LastModified": last_modified,
                    "Content": content  # Store the content to avoid re-downloading
                }
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                error_msg = e.response['Error']['Message']
                context = {
                    "file_id": file_id,
                    "bucket": self.source_bucket,
                    "operation": "get_object",
                    "error_code": error_code,
                    "error_message": error_msg
                }
                
                if error_code == '404':
                    log_api_error(self.logger, e, context)
                    raise FileNotFoundError(f"File '{file_id}' not found in bucket '{self.source_bucket}'")
                elif error_code == '403':
                    log_api_error(self.logger, e, context)
                    self.logger.error("Access denied. Current configuration:")
                    self.logger.error(f"Bucket: {self.source_bucket}")
                    self.logger.error(f"Key: {file_id}")
                    self.logger.error(f"Endpoint: {self.endpoint_url}")
                    raise PermissionError(
                        f"Access denied to file '{file_id}' in bucket '{self.source_bucket}'. "
                        "Please verify:\n"
                        "1. S3 credentials are correct\n"
                        "2. IAM/bucket policy allows s3:GetObject\n"
                        "3. File exists and is accessible\n"
                        "4. Bucket and path configuration is correct"
                    )
                else:
                    log_api_error(self.logger, e, context)
                    raise Exception(f"S3 error accessing file '{file_id}': {error_msg}")
            
            # Check if already processed
            doc = session.query(Document).filter_by(
                original_filename=file_id
            ).order_by(Document.created_at.desc()).first()
            
            if doc and doc.s3_last_modified >= file_metadata['LastModified']:
                return {"status": "skipped", "message": "File already processed"}
            
            # Process the file
            await self._process_file(file_metadata, session)
            return {"status": "success", "message": "File processed successfully"}
            
        except self.s3_client.exceptions.NoSuchKey:
            raise Exception(f"File {file_id} not found in bucket")
        except Exception as e:
            raise Exception(f"Error processing file {file_id}: {str(e)}")
    
    async def _process_file(self, obj, session: Session):
        try:
            # Use the content we already downloaded
            content = obj.get('Content')
            if not content:
                self.logger.error(f"No content provided for file {obj['Key']}")
                raise ValueError("File content not provided")
                
            try:
            with tempfile.NamedTemporaryFile() as tmp:
                # Write the content we already have to temp file
                tmp.write(content)
                tmp.flush()
                
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
                else:
                    raise ValueError(f"Conversion service returned status {response.status_code}")
