
import os
import secrets
from io import BytesIO
from pathlib import Path

import boto3
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from azure.storage.blob import BlobServiceClient
from botocore.exceptions import ClientError
from azure.core.exceptions import AzureError

load_dotenv()

app = FastAPI(title="Multi-Cloud Data Management Platform")

secret_key = os.getenv("SESSION_SECRET_KEY")
if not secret_key:
    raise RuntimeError("SESSION_SECRET_KEY is missing from .env")

app.add_middleware(
    SessionMiddleware,
    secret_key=secret_key,
    same_site="lax",
    https_only=os.getenv("COOKIE_HTTPS_ONLY", "false").lower() == "true"
)

base_dir = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(base_dir / "templates"))

aws_region = os.getenv("AWS_REGION", "ap-northeast-1")
bucket_name = os.getenv("S3_BUCKET_NAME")
container_name = os.getenv("AZURE_CONTAINER_NAME", "uploads")

s3 = boto3.client(
    "s3",
    region_name=aws_region,
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID") or None,
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY") or None
)

connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
blob_service = None

if connection_string:
    blob_service = BlobServiceClient.from_connection_string(
        connection_string
    )

admin_username = os.getenv("ADMIN_USERNAME", "")
admin_password = os.getenv("ADMIN_PASSWORD", "")


def check_login(request):
    if not request.session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Please login first")


def check_provider(provider):
    if provider not in ("aws", "azure"):
        raise HTTPException(status_code=400, detail="Invalid provider")


def get_container():
    if not blob_service:
        raise HTTPException(status_code=500, detail="Azure is not configured")

    return blob_service.get_container_client(container_name)


def clean_filename(filename):
    filename = filename.replace("\\", "/").split("/")[-1].strip()

    if not filename or filename in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid filename")

    return filename


def format_size(size):
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.2f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.2f} MB"

    return f"{size / (1024 * 1024 * 1024):.2f} GB"


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"request": request}
    )


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    if not admin_username or not admin_password:
        raise HTTPException(status_code=500, detail="Login is not configured")

    username_ok = secrets.compare_digest(username, admin_username)
    password_ok = secrets.compare_digest(password, admin_password)

    if username_ok and password_ok:
        request.session.clear()
        request.session["logged_in"] = True
        return {"message": "Login successful"}

    raise HTTPException(
        status_code=401,
        detail="Invalid username or password"
    )


@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"message": "Logged out successfully"}


@app.get("/auth/me")
async def auth_status(request: Request):
    return {"logged_in": bool(request.session.get("logged_in"))}


@app.get("/health")
async def health():
    return {"status": "running"}


@app.post("/upload/{provider}")
async def upload_file(
    provider: str,
    request: Request,
    file: UploadFile = File(...)
):
    check_login(request)
    check_provider(provider)

    filename = clean_filename(file.filename or "")
    data = await file.read()

    try:
        if provider == "aws":
            if not bucket_name:
                raise HTTPException(
                    status_code=500,
                    detail="S3 bucket is not configured"
                )

            s3.upload_fileobj(
                BytesIO(data),
                bucket_name,
                filename,
                ExtraArgs={
                    "ContentType": file.content_type
                    or "application/octet-stream"
                }
            )
        else:
            container = get_container()
            blob = container.get_blob_client(filename)
            blob.upload_blob(data, overwrite=True)

        return {
            "message": "File uploaded successfully",
            "filename": filename,
            "provider": provider,
            "size": format_size(len(data))
        }

    except (ClientError, AzureError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    finally:
        await file.close()


@app.get("/files/{provider}")
async def list_files(provider: str, request: Request):
    check_login(request)
    check_provider(provider)

    files = []

    try:
        if provider == "aws":
            if not bucket_name:
                raise HTTPException(
                    status_code=500,
                    detail="S3 bucket is not configured"
                )

            paginator = s3.get_paginator("list_objects_v2")

            for page in paginator.paginate(Bucket=bucket_name):
                for item in page.get("Contents", []):
                    files.append({
                        "name": item["Key"],
                        "size": item["Size"],
                        "size_readable": format_size(item["Size"]),
                        "last_modified": item["LastModified"].isoformat()
                    })
        else:
            container = get_container()

            for item in container.list_blobs():
                size = item.size or 0
                files.append({
                    "name": item.name,
                    "size": size,
                    "size_readable": format_size(size),
                    "last_modified": (
                        item.last_modified.isoformat()
                        if item.last_modified else None
                    )
                })

        return {
            "provider": provider,
            "count": len(files),
            "files": files
        }

    except (ClientError, AzureError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.get("/download/{provider}/{filename:path}")
async def download_file(
    provider: str,
    filename: str,
    request: Request
):
    check_login(request)
    check_provider(provider)
    filename = clean_filename(filename)

    try:
        if provider == "aws":
            if not bucket_name:
                raise HTTPException(
                    status_code=500,
                    detail="S3 bucket is not configured"
                )

            result = s3.get_object(
                Bucket=bucket_name,
                Key=filename
            )
            data = result["Body"].read()
        else:
            container = get_container()
            blob = container.get_blob_client(filename)
            data = blob.download_blob().readall()

        return StreamingResponse(
            BytesIO(data),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "")

        if code in ("NoSuchKey", "404", "NotFound"):
            raise HTTPException(
                status_code=404,
                detail="File not found"
            ) from error

        raise HTTPException(status_code=502, detail=str(error)) from error

    except AzureError as error:
        if getattr(error, "status_code", None) == 404:
            raise HTTPException(
                status_code=404,
                detail="File not found"
            ) from error

        raise HTTPException(status_code=502, detail=str(error)) from error


@app.delete("/files/{provider}/{filename:path}")
async def delete_file(
    provider: str,
    filename: str,
    request: Request
):
    check_login(request)
    check_provider(provider)
    filename = clean_filename(filename)

    try:
        if provider == "aws":
            if not bucket_name:
                raise HTTPException(
                    status_code=500,
                    detail="S3 bucket is not configured"
                )

            s3.delete_object(
                Bucket=bucket_name,
                Key=filename
            )
        else:
            container = get_container()
            container.delete_blob(filename)

        return {
            "message": "File deleted successfully",
            "filename": filename,
            "provider": provider
        }

    except (ClientError, AzureError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.get("/analytics")
async def analytics(request: Request):
    check_login(request)

    aws_count = 0
    aws_size = 0
    azure_count = 0
    azure_size = 0
    errors = []

    try:
        if bucket_name:
            paginator = s3.get_paginator("list_objects_v2")

            for page in paginator.paginate(Bucket=bucket_name):
                for item in page.get("Contents", []):
                    aws_count += 1
                    aws_size += item["Size"]
        else:
            errors.append("S3 bucket is not configured")

    except ClientError as error:
        errors.append(f"AWS: {error}")

    try:
        if blob_service:
            container = get_container()

            for item in container.list_blobs():
                azure_count += 1
                azure_size += item.size or 0
        else:
            errors.append("Azure is not configured")

    except AzureError as error:
        errors.append(f"Azure: {error}")

    total_size = aws_size + azure_size

    return {
        "aws": {
            "files": aws_count,
            "bytes": aws_size,
            "size": format_size(aws_size)
        },
        "azure": {
            "files": azure_count,
            "bytes": azure_size,
            "size": format_size(azure_size)
        },
        "total": {
            "files": aws_count + azure_count,
            "bytes": total_size,
            "size": format_size(total_size)
        },
        "errors": errors
    }