import os
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient

load_dotenv(".env", override=True)

connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
container_name = os.getenv("AZURE_CONTAINER_NAME", "uploads")

if not connection_string:
    print("ERROR: Azure connection string not found in .env")
    raise SystemExit(1)

try:
    blob_service = BlobServiceClient.from_connection_string(
        connection_string
    )

    container = blob_service.get_container_client(container_name)

    if container.exists():
        print("Azure connection successful!")
        print("Container:", container_name)

        print("Existing blobs:")
        for blob in container.list_blobs():
            print("-", blob.name)
    else:
        print("Azure connected, but container does not exist.")

except Exception as e:
    print("Azure connection failed:", type(e).__name__)
    print("Check your connection string and container settings.")