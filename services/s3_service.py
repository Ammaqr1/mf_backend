
import os
from dotenv import load_dotenv
from app.db.schema import generate_cuid
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
AWS_S3_BUCKET = os.environ["AWS_S3_BUCKET"]



MAX_PDF_SIZE = 50 * 1024 * 1024  # 50 MB

s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION,
    config=Config(signature_version="s3v4"),
)



def generate_upload_url(user_id: str):
    document_id = generate_cuid()

    object_key = (
        f"users/{user_id}/documents/{document_id}.pdf"
    )

    response = s3_client.generate_presigned_post(
        Bucket=AWS_S3_BUCKET,
        Key=object_key,
        Fields={
            "Content-Type": "application/pdf"
        },
        Conditions=[
            {"Content-Type": "application/pdf"},
            ["content-length-range", 1, MAX_PDF_SIZE],
        ],
        ExpiresIn=300,
    )

    return {
        "document_id": document_id,
        "key": object_key,
        "url": response["url"],
        "fields": response["fields"],
    }


def check_pdf_password(object_key: str, password: str | None) -> bool | None:
    """None = PDF is not encrypted, True = password opens it, False = missing/wrong."""
    import fitz  # pymupdf

    try:
        body = s3_client.get_object(Bucket=AWS_S3_BUCKET, Key=object_key)["Body"].read()
        doc = fitz.open(stream=body, filetype="pdf")
    except Exception:
        return None  # unreadable PDF: can't judge the password

    try:
        if not doc.needs_pass:
            return None
        if not password:
            return False
        return bool(doc.authenticate(password))
    finally:
        doc.close()


def verify_uploaded_pdf(user_id: str, object_key: str):
    expected_prefix = f"users/{user_id}/documents/"

    if not object_key.startswith(expected_prefix):
        raise ValueError("Invalid document ownership")

    try:
        metadata = s3_client.head_object(
            Bucket=AWS_S3_BUCKET,
            Key=object_key,
        )

        if metadata["ContentLength"] > MAX_PDF_SIZE:
            raise ValueError("PDF exceeds maximum size")

        if metadata["ContentType"] != "application/pdf":
            raise ValueError("Invalid content type")

        # Verify actual PDF signature
        result = s3_client.get_object(
            Bucket=AWS_S3_BUCKET,
            Key=object_key,
            Range="bytes=0-4",
        )

        signature = result["Body"].read()

        if signature != b"%PDF-":
            raise ValueError("Invalid PDF file")

        return {
            "size": metadata["ContentLength"],
            "key": object_key,
            "content_type": metadata["ContentType"],
        }

    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]

        if error_code in ("404", "NoSuchKey", "NotFound"):
            raise ValueError("Uploaded document not found")

        raise