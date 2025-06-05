import os
from minio import Minio
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Setup MinIO client
minio_client = Minio(
    os.getenv("MINIO_ENDPOINT"),
    access_key=os.getenv("MINIO_ACCESS_KEY"),
    secret_key=os.getenv("MINIO_SECRET_KEY"),
    secure=os.getenv("MINIO_SECURE") == "True"
)

bucket_name = os.getenv("BUCKET_NAME")  # passed dynamically by orchestrator
download_dir = "./"

# Create local download directory if it doesn't exist
os.makedirs(download_dir, exist_ok=True)

# List and download all objects
objects = minio_client.list_objects(bucket_name, recursive=True)

print(f"Downloading objects from bucket '{bucket_name}'...\n")

for obj in objects:
    object_path = obj.object_name
    local_file_path = os.path.join(download_dir, object_path)

    # Create local subdirectories if needed
    os.makedirs(os.path.dirname(local_file_path), exist_ok=True)

    # Download the object
    minio_client.fget_object(bucket_name, object_path, local_file_path)
    print(f"Downloaded: {object_path} -> {local_file_path}")

print("\n✅ All files downloaded successfully.")
