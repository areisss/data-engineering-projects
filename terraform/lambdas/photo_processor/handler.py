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

# EXIF tag IDs used for metadata extraction
_TAG_MAKE              = 271
_TAG_MODEL             = 272
_TAG_DATETIME          = 306
_TAG_DATETIME_ORIGINAL = 36867
_TAG_FLASH             = 37385
_TAG_GPS_INFO          = 34853

_EXIF_DT_FORMAT = "%Y:%m:%d %H:%M:%S"


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


def extract_exif(image_data: bytes) -> dict:
    """Extract EXIF metadata from image bytes.

    Returns a dict with keys:
      taken_at     - ISO-8601 string from DateTimeOriginal/DateTime, or None
      camera_make  - Camera manufacturer string, or None
      camera_model - Camera model string, or None
      tags         - Auto-derived list: orientation (landscape/portrait/square),
                     plus 'flash' and 'gps' when those EXIF fields are present

    All fields default to None / [] if EXIF is absent or unreadable.
    """
    result = {"taken_at": None, "camera_make": None, "camera_model": None, "tags": []}
    try:
        img = Image.open(BytesIO(image_data))
        exif = img.getexif()

        # taken_at: prefer DateTimeOriginal, fall back to DateTime
        raw_dt = exif.get(_TAG_DATETIME_ORIGINAL) or exif.get(_TAG_DATETIME)
        if raw_dt:
            try:
                dt = datetime.strptime(raw_dt.strip(), _EXIF_DT_FORMAT)
                result["taken_at"] = dt.replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass

        make = exif.get(_TAG_MAKE)
        model = exif.get(_TAG_MODEL)
        if make:
            result["camera_make"] = make.strip().rstrip("\x00")
        if model:
            result["camera_model"] = model.strip().rstrip("\x00")

        # Auto-derive orientation tag from image dimensions
        w, h = img.size
        if w > h:
            result["tags"].append("landscape")
        elif h > w:
            result["tags"].append("portrait")
        else:
            result["tags"].append("square")

        # Flash: bit 0 of tag 37385 = flash fired
        flash = exif.get(_TAG_FLASH)
        if isinstance(flash, int) and flash & 0x1:
            result["tags"].append("flash")

        # GPS presence
        if exif.get(_TAG_GPS_INFO):
            result["tags"].append("gps")

    except Exception as e:
        print(f"EXIF extraction failed: {e}")

    return result


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
        exif_meta = extract_exif(image_data)

        item = {
            "photo_id":     str(uuid.uuid4()),
            "original_key": original_key,
            "thumbnail_key": thumbnail_key,
            "filename":     filename,
            "width":        width,
            "height":       height,
            "size_bytes":   len(image_data),
            "content_type": content_type,
            "uploaded_at":  datetime.now(timezone.utc).isoformat(),
            "source_key":   key,
            # EXIF fields — None values omitted to keep DynamoDB items lean
            "taken_at":     exif_meta["taken_at"],
            "camera_make":  exif_meta["camera_make"],
            "camera_model": exif_meta["camera_model"],
            "tags":         exif_meta["tags"],
        }
        # Strip None values — DynamoDB rejects explicit nulls on non-key attributes
        item = {k: v for k, v in item.items() if v is not None}

        table.put_item(Item=item)

        print(f"Done: {original_key} + {thumbnail_key} | "
              f"taken_at={exif_meta['taken_at']} make={exif_meta['camera_make']} "
              f"tags={exif_meta['tags']}")

    return {"statusCode": 200}
