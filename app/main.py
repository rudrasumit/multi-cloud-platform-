from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
import boto3
import os
from pathlib import Path
from dotenv import load_dotenv


# ==========================================
# LOAD ENVIRONMENT VARIABLES
# ==========================================

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")


# ==========================================
# FASTAPI APPLICATION
# ==========================================

app = FastAPI(
    title="Multi-Cloud Data Management Platform",
    description="Cloud-based file management and replication platform",
    version="1.0.0"
)


# ==========================================
# AWS S3 CLIENT
# ==========================================

s3 = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)


# ==========================================
# HOME
# ==========================================

@app.get("/")
def home():
    return {
        "message": "Multi-Cloud Data Management Platform is running",
        "status": "success"
    }


# ==========================================
# HEALTH CHECK
# ==========================================

@app.get("/health")
def health():
    return {
        "status": "healthy"
    }


# ==========================================
# UPLOAD FILE TO S3
# ==========================================

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):

    try:

        s3.upload_fileobj(
            file.file,
            S3_BUCKET_NAME,
            file.filename
        )

        return {
            "status": "success",
            "filename": file.filename,
            "bucket": S3_BUCKET_NAME,
            "message": "File uploaded successfully"
        }

    except Exception as e:

        return {
            "status": "error",
            "message": str(e)
        }


# ==========================================
# LIST ALL FILES FROM S3
# ==========================================

@app.get("/files")
def list_files():

    try:

        response = s3.list_objects_v2(
            Bucket=S3_BUCKET_NAME
        )

        files = []

        for obj in response.get("Contents", []):

            files.append({
                "filename": obj["Key"],
                "size": obj["Size"],
                "last_modified": obj["LastModified"]
            })

        return {
            "status": "success",
            "bucket": S3_BUCKET_NAME,
            "total_files": len(files),
            "files": files
        }

    except Exception as e:

        return {
            "status": "error",
            "message": str(e)
        }


# ==========================================
# DOWNLOAD FILE FROM S3
# ==========================================

@app.get("/download/{filename}")
def download_file(filename: str):

    try:

        response = s3.get_object(
            Bucket=S3_BUCKET_NAME,
            Key=filename
        )

        file_stream = response["Body"]

        return StreamingResponse(
            file_stream,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition":
                f'attachment; filename="{filename}"'
            }
        )

    except Exception as e:

        return {
            "status": "error",
            "message": str(e)
        }


# ==========================================
# DELETE FILE FROM S3
# ==========================================

@app.delete("/delete/{filename}")
def delete_file(filename: str):

    try:

        # Check if file exists
        s3.head_object(
            Bucket=S3_BUCKET_NAME,
            Key=filename
        )

        # Delete file
        s3.delete_object(
            Bucket=S3_BUCKET_NAME,
            Key=filename
        )

        return {
            "status": "success",
            "filename": filename,
            "message": "File deleted successfully"
        }

    except s3.exceptions.ClientError as e:

        error_code = e.response["Error"]["Code"]

        if error_code in ["404", "NoSuchKey", "NotFound"]:

            return {
                "status": "error",
                "message": "File not found"
            }

        return {
            "status": "error",
            "message": str(e)
        }

    except Exception as e:

        return {
            "status": "error",
            "message": str(e)
        }