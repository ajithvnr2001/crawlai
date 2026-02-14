import boto3
from botocore.config import Config
import datetime

S3_CONFIG = {
    "endpoint_url": os.getenv("S3_ENDPOINT", "https://s3.us-west-1.wasabisys.com"),
    "access_key": os.getenv("S3_ACCESS_KEY"),
    "secret_key": os.getenv("S3_SECRET_KEY"),
    "bucket": os.getenv("S3_BUCKET", "crawlai")
}

def list_recent_s3_objects():
    s3 = boto3.client(
        's3',
        endpoint_url=S3_CONFIG["endpoint_url"],
        aws_access_key_id=S3_CONFIG["access_key"],
        aws_secret_access_key=S3_CONFIG["secret_key"],
        config=Config(signature_version='s3v4')
    )
    
    bucket_name = S3_CONFIG["bucket"]
    
    print(f"Fetching objects from bucket: {bucket_name}")
    
    try:
        # Get objects sorted by last modified
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name)
        
        all_objects = []
        for page in pages:
            if 'Contents' in page:
                all_objects.extend(page['Contents'])
        
        if not all_objects:
            print("No objects found in the bucket.")
            return

        # Sort by LastModified descending
        all_objects.sort(key=lambda x: x['LastModified'], reverse=True)
        
        print("\nLast 50 uploaded objects:")
        print("-" * 100)
        print(f"{'Key':<60} | {'Last Modified':<20} | {'Size'}")
        print("-" * 100)
        
        for obj in all_objects[:50]:
            last_mod = obj['LastModified'].strftime('%Y-%m-%d %H:%M:%S')
            size_kb = obj['Size'] / 1024
            print(f"{obj['Key']:<60} | {last_mod} | {size_kb:.2f} KB")

        print("\nChecking for potential state files:")
        state_files = [obj['Key'] for obj in all_objects if 'crawl_state' in obj['Key'].lower() or '.db' in obj['Key'].lower()]
        for sf in state_files[:5]:
            print(f"  Found: {sf}")
            
    except Exception as e:
        print(f"Error listing objects: {e}")

if __name__ == "__main__":
    list_recent_s3_objects()
