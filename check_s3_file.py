import boto3
from botocore.config import Config

S3_CONFIG = {
    "endpoint_url": os.getenv("S3_ENDPOINT", "https://s3.us-west-1.wasabisys.com"),
    "access_key": os.getenv("S3_ACCESS_KEY"),
    "secret_key": os.getenv("S3_SECRET_KEY"),
    "bucket": os.getenv("S3_BUCKET", "crawlai")
}

def check_specific_file():
    s3 = boto3.client(
        's3',
        endpoint_url=S3_CONFIG["endpoint_url"],
        aws_access_key_id=S3_CONFIG["access_key"],
        aws_secret_access_key=S3_CONFIG["secret_key"],
        config=Config(signature_version='s3v4')
    )
    
    bucket_name = S3_CONFIG["bucket"]
    # Transforming the URL to the expected S3 filename format
    # URL: https://forum.rclone.org/t/mounting-rclone-to-use-like-a-local-drive/25604/19
    # Format used in script: url.replace("https://", "").replace("/", "_").replace(".", "_")
    target_prefix = "extracted_data/forum_rclone_org_t_mounting-rclone-to-use-like-a-local-drive_25604_19"
    
    print(f"Searching for files starting with: {target_prefix}")
    
    try:
        response = s3.list_objects_v2(Bucket=bucket_name, Prefix=target_prefix)
        if 'Contents' in response:
            print("\nFound Files on S3:")
            for obj in response['Contents']:
                print(f"  {obj['Key']} ({obj['Size'] / 1024:.2f} KB) - {obj['LastModified']}")
        else:
            print("\nNo files found for this specific URL yet.")
            
    except Exception as e:
        print(f"Error checking S3: {e}")

if __name__ == "__main__":
    check_specific_file()
