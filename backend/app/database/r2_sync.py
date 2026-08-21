import os
import sys
import logging
from typing import Optional

logger = logging.getLogger("r2_sync")

def get_s3_client():
    """
    Initializes S3/R2 client using Cloudflare S3-compatible credentials.
    """
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
    endpoint = os.getenv("R2_S3_API_ENDPOINT") or (
        f"https://{account_id}.r2.cloudflarestorage.com" if account_id else None
    )

    if not (access_key and secret_key and endpoint):
        logger.info("[R2] Missing R2 credentials (R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY). Cloud sync skipped.")
        return None

    try:
        import boto3
        from botocore.config import Config
        return boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto",
            config=Config(signature_version="s3v4")
        )
    except ImportError:
        logger.warning("[R2] boto3 not installed. Please install boto3 to enable R2 cloud persistence.")
        return None
    except Exception as e:
        logger.warning(f"[R2] Failed to initialize S3 client: {e}")
        return None

def restore_database_from_r2(local_path: str = "backend/deals.db", bucket_name: str = "ajioradar-storage", key: str = "deals.db") -> bool:
    """
    Downloads latest deals.db snapshot from Cloudflare R2 before starting sync.
    """
    client = get_s3_client()
    if not client:
        return False

    resolved_path = os.path.abspath(local_path)
    os.makedirs(os.path.dirname(resolved_path), exist_ok=True)

    try:
        logger.info(f"[R2] Checking existing cloud backup in r2://{bucket_name}/{key}...")
        client.download_file(bucket_name, key, resolved_path)
        size = os.path.getsize(resolved_path)
        logger.info(f"[R2] Restored database snapshot from Cloudflare R2 ({size:,} bytes) -> {resolved_path}")
        return True
    except Exception as e:
        logger.info(f"[R2] No existing cloud snapshot or bucket not ready yet ({e}). Using fresh/local seed.")
        return False

def backup_database_to_r2(local_path: str = "backend/deals.db", bucket_name: str = "ajioradar-storage", key: str = "deals.db") -> bool:
    """
    Uploads updated deals.db SQLite database directly to Cloudflare R2 bucket for permanent persistence.
    """
    client = get_s3_client()
    if not client:
        return False

    resolved_path = os.path.abspath(local_path)
    if not os.path.exists(resolved_path) or os.path.getsize(resolved_path) < 1000:
        logger.warning(f"[R2] Skipping upload: {resolved_path} does not exist or is empty.")
        return False

    try:
        # 1. Ensure bucket exists or create it
        try:
            client.head_bucket(Bucket=bucket_name)
        except Exception:
            try:
                client.create_bucket(Bucket=bucket_name)
                logger.info(f"[R2] Created new R2 bucket '{bucket_name}'.")
            except Exception as be:
                logger.info(f"[R2] Bucket initialization note: {be}")

        # 2. Upload SQLite database file
        size = os.path.getsize(resolved_path)
        logger.info(f"[R2] Uploading database snapshot ({size:,} bytes) -> r2://{bucket_name}/{key}...")
        client.upload_file(resolved_path, bucket_name, key)
        logger.info(f"[R2] SQLite database backup saved to Cloudflare R2!")
        return True
    except Exception as e:
        logger.warning(f"[R2] Upload to R2 encountered error: {e}")
        return False

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    action = sys.argv[1] if len(sys.argv) > 1 else "backup"
    try:
        if action == "restore":
            restore_database_from_r2()
        else:
            backup_database_to_r2()
    except Exception as e:
        logger.info(f"[R2] Cloud backup step skipped safely: {e}")
    sys.exit(0)
