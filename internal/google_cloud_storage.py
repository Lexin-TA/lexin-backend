import io
import json
import os

from dotenv import load_dotenv
from fastapi import UploadFile
from google.cloud import storage

# Load Environment Variables.
load_dotenv()

if os.path.isfile("GOOGLE_APPLICATION_CREDENTIALS.json"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "GOOGLE_APPLICATION_CREDENTIALS.json"
else:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "../GOOGLE_APPLICATION_CREDENTIALS.json"

GOOGLE_CLOUD_STORAGE_URI = os.getenv('GOOGLE_CLOUD_STORAGE_URI')
GOOGLE_BUCKET_NAME = os.getenv('GOOGLE_BUCKET_NAME')

# Initialize Google Cloud Storage client.
client = storage.Client()
bucket = client.get_bucket(GOOGLE_BUCKET_NAME)


def upload_gcs_file(file: UploadFile, blob_name: str) -> str:
    blob = bucket.blob(blob_name)
    blob.upload_from_file(file.file)

    file_url = f"{GOOGLE_CLOUD_STORAGE_URI}/{GOOGLE_BUCKET_NAME}/{blob_name}"

    return file_url


def download_gcs_file(blob_name: str) -> io.BytesIO:
    blob = bucket.blob(blob_name)

    file_content = blob.download_as_bytes()
    file = io.BytesIO(file_content)

    return file
