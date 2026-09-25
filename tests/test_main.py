from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
import boto3
from botocore.exceptions import ClientError, BotoCoreError
import os
from pathlib import Path
from dotenv import load_dotenv


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

# Load .env from the same folder as this Python file
load_dotenv(BASE_DIR / ".env")

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")


# ============================================================
# VALIDATE ENVIRONMENT VARIABLES
# ============================================================

missing_variables = []

if not AWS_ACCESS_KEY_ID:
    missing_variables.append("AWS_ACCESS_KEY_ID")

if not AWS_SECRET_ACCESS_KEY:
    missing_variables.append("AWS_SECRET_ACCESS_KEY")

if not S3_BUCKET_NAME:
    missing_variables.append("S3_BUCKET_NAME")


if missing_variables:
    raise RuntimeError(
        "Missing environment variables: "
        + ", ".join(missing_variables)
    )


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Multi-Cloud Data Management Platform",
    description="Cloud-based file management and replication platform",
    version="1.0.0"
)


# ============================================================
# AWS S3 CLIENT
# ============================================================

try:

    s3 = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )

except Exception as e:

    raise RuntimeError(
        f"Failed to create AWS S3 client: {str(e)}"
    )


# ============================================================
# HOME
# ============================================================

@app.get("/", response_class=HTMLResponse)
def home():

    return """
    <!DOCTYPE html>

    <html lang="en">

    <head>

        <meta charset="UTF-8">

        <meta
            name="viewport"
            content="width=device-width, initial-scale=1.0"
        >

        <title>Multi-Cloud Data Management Platform</title>

        <style>

            body {

                font-family: Arial, sans-serif;

                background: #0f172a;

                color: #e2e8f0;

                margin: 0;

                padding: 40px;

            }

            .container {

                max-width: 900px;

                margin: 0 auto;

                background: #111827;

                border-radius: 16px;

                padding: 32px;

                box-shadow:
                    0 10px 30px rgba(0,0,0,0.25);

            }

            h1 {

                color: #7dd3fc;

                margin-top: 0;

            }

            h2 {

                color: #cbd5e1;

            }

            .badge {

                display: inline-block;

                background: #16a34a;

                color: white;

                padding: 6px 12px;

                border-radius: 999px;

                font-size: 12px;

                margin-bottom: 20px;

            }

            code {

                background: #1f2937;

                padding: 4px 8px;

                border-radius: 6px;

                color: #7dd3fc;

            }

            ul {

                line-height: 2;

            }

        </style>

    </head>

    <body>

        <div class="container">

            <div class="badge">
                API is running
            </div>

            <h1>
                Multi-Cloud Data Management Platform
            </h1>

            <p>
                Backend is active and connected to AWS S3.
            </p>

            <h2>
                Available Endpoints
            </h2>

            <ul>

                <li>
                    <code>GET /health</code>
                    - Health check
                </li>

                <li>
                    <code>POST /upload</code>
                    - Upload file to S3
                </li>

                <li>
                    <code>GET /files</code>
                    - List S3 files
                </li>

                <li>
                    <code>GET /download/{filename}</code>
                    - Download file
                </li>

                <li>
                    <code>DELETE /delete/{filename}</code>
                    - Delete file
                </li>

                <li>
                    <code>GET /docs</code>
                    - Swagger API documentation
                </li>

            </ul>

        </div>

    </body>

    </html>
    """


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health():

    try:

        # Check whether bucket is accessible
        s3.head_bucket(
            Bucket=S3_BUCKET_NAME
        )

        return {
            "status": "healthy",
            "service": "FastAPI",
            "s3": "connected",
            "bucket": S3_BUCKET_NAME,
            "region": AWS_REGION
        }

    except ClientError as e:

        return {
            "status": "unhealthy",
            "service": "FastAPI",
            "s3": "connection failed",
            "error": str(e)
        }


# ============================================================
# UPLOAD FILE TO S3
# ============================================================

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...)
):

    if not file.filename:

        raise HTTPException(
            status_code=400,
            detail="No filename provided"
        )

    filename = Path(file.filename).name

    try:

        # Upload file to S3
        s3.upload_fileobj(
            file.file,
            S3_BUCKET_NAME,
            filename,
            ExtraArgs={
                "ContentType": file.content_type
                or "application/octet-stream"
            }
        )

        return {

            "status": "success",

            "filename": filename,

            "bucket": S3_BUCKET_NAME,

            "message": "File uploaded successfully"

        }

    except ClientError as e:

        raise HTTPException(
            status_code=500,
            detail=f"S3 upload failed: {str(e)}"
        )

    except BotoCoreError as e:

        raise HTTPException(
            status_code=500,
            detail=f"AWS error: {str(e)}"
        )

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {str(e)}"
        )


# ============================================================
# LIST ALL FILES FROM S3
# ============================================================

@app.get("/files")
def list_files():

    try:

        files = []

        # First request
        response = s3.list_objects_v2(
            Bucket=S3_BUCKET_NAME
        )

        # Add first page
        for obj in response.get("Contents", []):

            files.append({

                "filename": obj["Key"],

                "size": obj["Size"],

                "last_modified":
                    obj["LastModified"].isoformat()

            })

        # Handle pagination
        while response.get("IsTruncated"):

            response = s3.list_objects_v2(

                Bucket=S3_BUCKET_NAME,

                ContinuationToken=
                    response["NextContinuationToken"]

            )

            for obj in response.get("Contents", []):

                files.append({

                    "filename": obj["Key"],

                    "size": obj["Size"],

                    "last_modified":
                        obj["LastModified"].isoformat()

                })

        return {

            "status": "success",

            "bucket": S3_BUCKET_NAME,

            "total_files": len(files),

            "files": files

        }

    except ClientError as e:

        raise HTTPException(

            status_code=500,

            detail=f"Unable to list S3 files: {str(e)}"

        )

    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=f"Error listing files: {str(e)}"

        )


# ============================================================
# DOWNLOAD FILE FROM S3
# ============================================================

@app.get("/download/{filename:path}")
def download_file(filename: str):

    filename = Path(filename).name

    try:

        response = s3.get_object(

            Bucket=S3_BUCKET_NAME,

            Key=filename

        )

        file_stream = response["Body"]

        content_type = response.get(
            "ContentType",
            "application/octet-stream"
        )

        return StreamingResponse(

            file_stream,

            media_type=content_type,

            headers={

                "Content-Disposition":
                    f'attachment; filename="{filename}"'

            }

        )

    except ClientError as e:

        error_code = e.response.get(
            "Error", {}
        ).get(
            "Code"
        )

        if error_code in [
            "NoSuchKey",
            "404",
            "NotFound"
        ]:

            raise HTTPException(

                status_code=404,

                detail="File not found"

            )

        raise HTTPException(

            status_code=500,

            detail=f"S3 download failed: {str(e)}"

        )

    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=f"Download failed: {str(e)}"

        )


# ============================================================
# DELETE FILE FROM S3
# ============================================================

@app.delete("/delete/{filename:path}")
def delete_file(filename: str):

    filename = Path(filename).name

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

    except ClientError as e:

        error_code = e.response.get(
            "Error", {}
        ).get(
            "Code"
        )

        if error_code in [
            "404",
            "NoSuchKey",
            "NotFound"
        ]:

            raise HTTPException(

                status_code=404,

                detail="File not found"

            )

        raise HTTPException(

            status_code=500,

            detail=f"S3 delete failed: {str(e)}"

        )

    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=f"Delete failed: {str(e)}"

        )


# ============================================================
# APPLICATION START
# ============================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(

        app,

        host="127.0.0.1",

        port=8000

    )