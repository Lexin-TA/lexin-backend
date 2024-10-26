import io
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import IO

from dotenv import load_dotenv
from fastapi import HTTPException
from google.cloud import storage
from google.api_core.exceptions import GoogleAPIError

# Load Environment Variables.
load_dotenv()

if os.path.isfile("GOOGLE_APPLICATION_CREDENTIALS.json"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "GOOGLE_APPLICATION_CREDENTIALS.json"
else:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "../GOOGLE_APPLICATION_CREDENTIALS.json"

GOOGLE_CLOUD_STORAGE_URI = os.getenv('GOOGLE_CLOUD_STORAGE_URI')
GOOGLE_BUCKET_NAME = os.getenv('GOOGLE_BUCKET_NAME')

# Initialize Google Cloud Storage client.
storage_client = storage.Client()


def create_bucket(bucket_name):
    """Creates a new bucket."""
    try:
        bucket = storage_client.create_bucket(bucket_name)
    except GoogleAPIError as e:
        raise HTTPException(status_code=422, detail=str(e))

    result = {
        "detail": f"Bucket {bucket.name} created",
        "ok": True
    }

    return result


def delete_bucket(bucket_name):
    """Deletes a bucket even if it's not empty."""
    try:
        bucket = storage_client.get_bucket(bucket_name)
        bucket.delete(force=True)
    except GoogleAPIError as e:
        raise HTTPException(status_code=422, detail=str(e))

    result = {
        "detail": f"Bucket {bucket.name} deleted",
        "ok": True
    }

    return result


def clear_bucket(bucket_name: str) -> dict:
    def delete_single_blob(blob):
        """Helper function to delete a single blob."""
        blob.delete()

    bucket = storage_client.get_bucket(bucket_name)
    blobs = list(bucket.list_blobs())  # Pre-fetch blob list

    # Delete files in parallel using ThreadPoolExecutor
    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(delete_single_blob, blob) for blob in blobs]

        for future in as_completed(futures):
            if future.exception():
                # Log or handle exception if needed
                print(f"Error deleting blob: {future.exception()}")

    result = {
        "detail": f"Bucket {bucket.name} cleared",
        "ok": True
    }

    return result


def delete_file(bucket_name: str, blob_name: str) -> str:
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    blob.delete()

    return f"Blob {blob_name} deleted."


def upload_file(bucket_name: str, file: IO[bytes], blob_name: str) -> str:
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(blob_name)

    # # Check if file is already in google cloud storage.
    # if blob.exists():
    #     raise HTTPException(status_code=400, detail="A file with this name already exists in storage.")

    # Upload file to google cloud storage
    blob.upload_from_file(file)
    file_url = f"{GOOGLE_CLOUD_STORAGE_URI}/{GOOGLE_BUCKET_NAME}/{blob_name}"

    return file_url


def download_file(bucket_name: str, blob_name: str) -> io.BytesIO:
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(blob_name)

    file_content = blob.download_as_bytes()
    file = io.BytesIO(file_content)

    return file
