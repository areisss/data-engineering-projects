import os
import urllib.parse
import uuid
from datetime import datetime, timezone
from io import BytesIO

import boto3
from PIL import Image

# In Lambda, AWS_REGION is always set. The fallback lets the module import
# cleanly in local/test environments where no region is configured.
_REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))

s3 = boto3.client("s3", region_name=_REGION)
dynamodb = boto3.resource("dynamodb", region_name=_REGION)

BUCKET_NAME = os.environ.get("BUCKET_NAME", "")
TABLE_NAME = os.environ.get("TABLE_NAME", "")
THUMBNAIL_MAX_PX = 300

_PIL_FORMAT = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}


def get_dimensions(image_data: bytes) -> tuple:
    """Return (width, height) of the original image."""
    img = Image.open(BytesIO(image_data))
    return img.size


def make_thumbnail(image_data: bytes, pil_format: str) -> bytes:
    """Resize image to fit within THUMBNAIL_MAX_PX on its longest side.

    Converts RGBA/palette images to RGB before saving as JPEG to avoid
    format errors. Returns the thumbnail as bytes.
    """
    img = Image.open(BytesIO(image_data))
    if pil_format == "JPEG" and img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGB")
    img.thumbnail((THUMBNAIL_MAX_PX, THUMBNAIL_MAX_PX), Image.Resampling.LANCZOS)
    buf = BytesIO()
    img.save(buf, format=pil_format)
    return buf.getvalue()


def handler(event, context):
    table = dynamodb.Table(TABLE_NAME)

    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        filename = key.split("/")[-1]
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
        pil_format = _PIL_FORMAT.get(ext, "JPEG")

        print(f"Processing s3://{bucket}/{key}")

        response = s3.get_object(Bucket=bucket, Key=key)
        image_data = response["Body"].read()
        content_type = response.get("ContentType", f"image/{ext}")

        # Preserve original in photos/originals/
        original_key = f"photos/originals/{filename}"
        s3.copy_object(
            Bucket=bucket,
            CopySource={"Bucket": bucket, "Key": key},
            Key=original_key,
        )

        # Generate thumbnail and write to photos/thumbnails/
        thumbnail_data = make_thumbnail(image_data, pil_format)
        thumbnail_key = f"photos/thumbnails/{filename}"
        s3.put_object(
            Bucket=bucket,
            Key=thumbnail_key,
            Body=thumbnail_data,
            ContentType=content_type,
        )

        width, height = get_dimensions(image_data)

        table.put_item(
            Item={
                "photo_id": str(uuid.uuid4()),
                "original_key": original_key,
                "thumbnail_key": thumbnail_key,
                "filename": filename,
                "width": width,
                "height": height,
                "size_bytes": len(image_data),
                "content_type": content_type,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "source_key": key,
            }
        )

        print(f"Done: {original_key} + {thumbnail_key}")

    return {"statusCode": 200}
