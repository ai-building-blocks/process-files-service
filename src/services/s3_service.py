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
from typing import Dict, List, Optional
from src.models.documents import Document

class S3Service:
    def __init__(self):
        self.logger = get_logger(__name__)
        # Disable SSL warnings for local development
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Set up data directories
        self.temp_dir = os.getenv('TEMP_DIR', './data/temp')
        self.processed_dir = os.getenv('PROCESSED_DIR', './data/processed')
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.processed_dir, exist_ok=True)
        
        # Validate required environment variables
        self.endpoint_url = os.getenv('S3_ENDPOINT')
        self.source_bucket = os.getenv('SOURCE_BUCKET')
        self.access_key = os.getenv('S3_ACCESS_KEY')
        self.secret_key = os.getenv('S3_SECRET_KEY')
        
        if not all([self.endpoint_url, self.source_bucket, self.access_key, self.secret_key]):
            raise ValueError("Missing required environment variables: S3_ENDPOINT, SOURCE_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY")
            
        # Ensure endpoint includes API port for MinIO (typically :9000)
        if ':' not in self.endpoint_url:
            self.endpoint_url = f"{self.endpoint_url}:9000"
            
        # Get prefixes from environment with validation
        self.source_prefix = self._validate_prefix(os.getenv('SOURCE_PREFIX', 'downloads/'))
        self.destination_prefix = self._validate_prefix(os.getenv('DESTINATION_PREFIX', 'processed/'))
            
        config = Config(
            s3={'addressing_style': 'path' if os.getenv('S3_USE_PATH_STYLE', 'true').lower() == 'true' else 'auto'},
            connect_timeout=5,
            retries={'max_attempts': 3}
        )
            
        self.s3_client = boto3.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name='us-east-1',  # Required for MinIO
            config=config,
            verify=os.getenv('S3_VERIFY_SSL', 'true').lower() == 'true'
        )
        
        # Validate bucket access and create if needed
        self._validate_bucket_access()

    def _validate_bucket_access(self) -> None:
        """Validate access to the S3 bucket and create if needed"""
        try:
            self.s3_client.head_bucket(Bucket=self.source_bucket)
            self.logger.info(f"Successfully connected to bucket '{self.source_bucket}' with full access")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_msg = e.response['Error'].get('Message', '')
            
            if error_code == '403':
                self._handle_access_denied_error(error_msg)
            elif error_code == '404':
                self._handle_missing_bucket()
            else:
                self.logger.error(f"S3 error: {error_code} - {error_msg}")
                raise

    def _handle_access_denied_error(self, error_msg: str) -> None:
        """Handle 403 Access Denied error with detailed logging"""
        self.logger.error(f"Access denied to bucket '{self.source_bucket}'. Error: {error_msg}")
        self.logger.error("Current credentials and configuration:")
        self.logger.error(f"Access Key: {self.access_key[:4]}...{self.access_key[-4:]}")
        self.logger.error(f"Endpoint: {self.endpoint_url}")
        self.logger.error(f"Bucket: {self.source_bucket}")
        self.logger.error(f"Source Prefix: {self.source_prefix}")
        
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

    def _handle_missing_bucket(self) -> None:
        """Handle 404 Not Found error by creating the bucket"""
        self.logger.warning(f"Bucket '{self.source_bucket}' does not exist, attempting to create...")
        try:
            self.s3_client.create_bucket(Bucket=self.source_bucket)
            self.logger.info(f"Successfully created bucket '{self.source_bucket}'")
        except ClientError as create_error:
            self.logger.error(f"Failed to create bucket: {str(create_error)}")
            raise ValueError(f"Cannot create bucket '{self.source_bucket}'. Error: {str(create_error)}")

    def _validate_prefix(self, prefix: str) -> str:
        """Validate and normalize S3 prefix format"""
        if not prefix:
            raise ValueError("Prefix cannot be empty")
        
        # Ensure prefix ends with forward slash
        prefix = prefix.strip('/')
        return f"{prefix}/"
        
    async def list_files(self, session: Optional[Session] = None, since: Optional[str] = None) -> List[Dict]:
        """List files from source bucket with accurate processing status"""
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.source_bucket,
                Prefix=self.source_prefix
            )
            
            contents = response.get('Contents', [])
            self.logger.debug(f"Listed {len(contents)} objects in {self.source_bucket}/{self.source_prefix}")
            
            if since:
                since_ts = self._parse_timestamp(since)
                contents = [obj for obj in contents if obj['LastModified'].timestamp() >= since_ts]
                
            return [self._create_file_info(obj, session) for obj in contents]
            
        except Exception as e:
            self.logger.error(f"Error listing bucket files: {str(e)}")
            raise

    def _parse_timestamp(self, timestamp: str) -> float:
        """Parse timestamp from ULID or ISO format"""
        try:
            return ulid.parse(timestamp).timestamp()
        except ValueError:
            return datetime.fromisoformat(timestamp.replace('Z', '+00:00')).timestamp()

    def _create_file_info(self, obj: Dict, session: Optional[Session]) -> Dict:
        """Create file info dictionary from S3 object"""
        filename = obj['Key'].replace(self.source_prefix, '', 1)
        doc = None
        if session:
            doc = session.query(Document).filter_by(
                original_filename=obj['Key']
            ).first()
            
        status = "unprocessed"
        if doc:
            status = doc.status
        elif os.path.exists(os.path.join(self.temp_dir, filename)):
            status = "downloaded"
            
        return {
            "id": doc.id if doc else str(ulid.new()),
            "filename": filename,
            "status": status,
            "last_modified": obj['LastModified'].isoformat()
        }

    async def get_files_status(self, session: Session) -> Dict[str, str]:
        """Get processing status for all files in the system"""
        try:
            # Get all documents from database
            docs = {doc.original_filename: "processed" 
                   for doc in session.query(Document).all()}
                
            # Check source bucket for unprocessed files
            response = self.s3_client.list_objects_v2(
                Bucket=self.source_bucket,
                Prefix=self.source_prefix
            )
            
            for obj in response.get('Contents', []):
                if obj['Key'] not in docs:
                    docs[obj['Key']] = "unprocessed"
                    
            return docs
            
        except Exception as e:
            self.logger.error(f"Error getting files status: {str(e)}")
            raise

    async def process_new_files(self, session: Session) -> List[Dict]:
        """Process all new files in the source bucket"""
        results = []
        objects = self.s3_client.list_objects_v2(
            Bucket=self.source_bucket,
            Prefix=self.source_prefix
        )
        
        for obj in objects.get('Contents', []):
            try:
                result = await self.process_single_file(obj['Key'], session)
                results.append({
                    'file': obj['Key'],
                    'status': result['status'],
                    'message': result['message']
                })
            except Exception as e:
                results.append({
                    'file': obj['Key'],
                    'status': 'error',
                    'message': str(e)
                })
                
        return results

    def process_single_file(self, file_id: str, session: Session) -> None:
        """Process a specific file by its ID in background"""
        try:
            # Get file metadata first
            head_response = self.s3_client.head_object(
                Bucket=self.source_bucket,
                Key=file_id
            )
            last_modified = head_response['LastModified']
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code in ['403', '404']:
                self._handle_s3_client_error(e, file_id)
            raise

        # Create initial document record with s3_last_modified
        doc = Document(
            id=str(ulid.new()),
            original_filename=file_id,
            processed_filename='',
            version='1.0',
            status='pending',
            created_at=datetime.utcnow(),
            s3_last_modified=last_modified.replace(tzinfo=None)  # Remove timezone for SQLite
        )
        session.add(doc)
        session.commit()
        
        try:
            # Update status to downloading
            doc.status = 'downloading'
            session.commit()
            
            log_s3_operation(self.logger, "get_object", {"file_id": file_id})
            
            try:
                response = self.s3_client.get_object(
                    Bucket=self.source_bucket,
                    Key=file_id
                )
                
                content = response['Body'].read()
                last_modified = response['LastModified']
                self.logger.info(f"Successfully downloaded file {file_id}, size: {len(content)} bytes")
                
                # Update status after successful download
                doc.status = 'downloaded'
                doc.downloaded_at = datetime.utcnow()
                doc.s3_last_modified = last_modified.replace(tzinfo=None)
                session.commit()
                
                file_metadata = {
                    "Key": file_id,
                    "LastModified": last_modified,
                    "Content": content
                }
                
            except ClientError as e:
                doc.status = 'failed'
                doc.error_message = str(e)
                session.commit()
                self._handle_s3_client_error(e, file_id)
            
            # Update status to processing
            doc.status = 'processing'
            doc.processing_started_at = datetime.utcnow()
            session.commit()
            
            # Process the file synchronously since S3 operations are blocking
            self._process_file(file_metadata, session, doc)
            
        except Exception as e:
            self.logger.error(f"Error processing file {file_id}: {str(e)}")
            raise

    def _handle_s3_client_error(self, error: ClientError, file_id: str) -> None:
        """Handle S3 client errors with appropriate logging and exceptions"""
        error_code = error.response['Error']['Code']
        error_msg = error.response['Error']['Message']
        context = {
            "file_id": file_id,
            "bucket": self.source_bucket,
            "operation": "get_object",
            "error_code": error_code,
            "error_message": error_msg
        }
        
        log_api_error(self.logger, error, context)
        
        if error_code == '404':
            raise FileNotFoundError(f"File '{file_id}' not found in bucket '{self.source_bucket}'")
        elif error_code == '403':
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
            raise Exception(f"S3 error accessing file '{file_id}': {error_msg}")
    
    def process_single_file_background(self, obj: Dict, session: Session) -> None:
        """Process a single file through the converter service"""
        content = obj.get('Content')
        if not content:
            self.logger.error(f"No content provided for file {obj['Key']}")
            raise ValueError("File content not provided")

        # Create or get document record
        doc = session.query(Document).filter_by(original_filename=obj['Key']).first()
        if not doc:
            doc = Document(
                id=str(ulid.new()),
                original_filename=obj['Key'],  # Store full path including prefix
                processed_filename='',
                version='1.0',
                status='pending',
                created_at=datetime.utcnow(),
                downloaded_at=datetime.utcnow(),  # Set downloaded_at timestamp
                processing_started_at=datetime.utcnow(),  # Set processing_started_at timestamp
                s3_last_modified=obj['LastModified'].replace(tzinfo=None)
            )
            session.add(doc)
            session.commit()
        else:
            # Update timestamps if document already exists
            doc.downloaded_at = datetime.utcnow()
            doc.processing_started_at = datetime.utcnow()
            session.commit()
            
        # Create a unique filename for the temporary file
        temp_filename = os.path.basename(obj['Key'])
        temp_filepath = os.path.join(self.temp_dir, temp_filename)
        
        try:
            # Log pre-save state
            self.logger.debug(f"Attempting to save file to {temp_filepath}")
            self.logger.debug(f"Temp directory exists: {os.path.exists(self.temp_dir)}")
            self.logger.debug(f"Temp directory permissions: {oct(os.stat(self.temp_dir).st_mode)[-3:]}")
            self.logger.debug(f"Content size to write: {len(content)} bytes")
            
            # Use absolute paths
            abs_temp_filepath = os.path.abspath(temp_filepath)
            self.logger.debug(f"Using absolute path: {abs_temp_filepath}")
            
            # Ensure parent directory exists
            os.makedirs(os.path.dirname(abs_temp_filepath), exist_ok=True)
            
            # Save the downloaded file
            with open(abs_temp_filepath, 'wb') as f:
                bytes_written = f.write(content)
                self.logger.debug(f"Bytes written to file: {bytes_written}")
                f.flush()
                os.fsync(f.fileno())  # Force write to disk
                
            # Verify file was saved correctly
            if not os.path.exists(abs_temp_filepath):
                raise IOError(f"Failed to save file to {abs_temp_filepath}")
            
            actual_size = os.path.getsize(abs_temp_filepath)
            self.logger.debug(f"Saved file size: {actual_size} bytes")
            if actual_size != len(content):
                raise IOError(f"File size mismatch. Expected: {len(content)}, Got: {actual_size}")
            
            # Double check file persistence
            with open(abs_temp_filepath, 'rb') as f:
                check_content = f.read()
                if len(check_content) != len(content):
                    raise IOError(f"File content verification failed. Expected size: {len(content)}, Got: {len(check_content)}")
                
            self.logger.info(f"Successfully saved file to {abs_temp_filepath}")
            self.logger.debug(f"File exists after save: {os.path.exists(abs_temp_filepath)}")
            
            self.logger.info(f"Processing file {obj['Key']}")
            
            # Get document record by original filename
            doc = session.query(Document).filter_by(original_filename=obj.get('Key')).first()
            if not doc:
                raise ValueError(f"No document record found for file {obj.get('Key')}")

            converter_url = os.getenv('CONVERTER_SERVICE_URL')
            if not converter_url:
                raise ValueError("CONVERTER_SERVICE_URL environment variable is required")
                
            with open(temp_filepath, 'rb') as f:
                response = requests.post(
                    converter_url,
                    files={'file': f}
                )
            
            if response.status_code != 200:
                doc.status = 'failed'
                doc.error_message = f"Conversion service returned status {response.status_code}"
                session.commit()
                raise ValueError(doc.error_message)
                
            content = response.json()['markdown_content']
            
            # Save locally in processed directory - use just the filename without prefix
            processed_filename = f'{doc.id}.md'
            processed_filepath = os.path.join(self.processed_dir, os.path.basename(processed_filename))
            with open(processed_filepath, 'w') as f:
                f.write(content)
            
            # Try to save to destination folder
            try:
                destination_key = f"{self.destination_prefix}{processed_filename}"
                self.s3_client.put_object(
                    Bucket=self.source_bucket,
                    Key=destination_key,
                    Body=content
                )
                
                # Update document status on successful upload
                doc.processed_filename = processed_filename
                doc.status = 'completed'
                doc.processing_completed_at = datetime.utcnow()
                session.commit()
                
            except Exception as upload_error:
                self.logger.error(f"Failed to upload processed file to S3: {str(upload_error)}")
                doc.status = 'upload_failed'
                doc.error_message = f"Failed to upload to S3: {str(upload_error)}"
                doc.processing_completed_at = datetime.utcnow()
                session.commit()
                raise  # Re-raise to trigger outer exception handling
            
        except Exception as e:
            if doc:
                doc.status = 'failed'
                doc.error_message = str(e)
                session.commit()
            raise
        finally:
            # Clean up temp file in all cases
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
                self.logger.debug(f"Cleaned up temporary file: {temp_filepath}")
