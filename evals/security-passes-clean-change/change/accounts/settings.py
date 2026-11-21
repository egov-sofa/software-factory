"""S3 settings for the avatar links, from the environment (.env.example lists them)."""
import os

AVATAR_BUCKET = os.environ.get("AVATAR_BUCKET", "shop-avatars")
AWS_REGION = os.environ.get("AWS_REGION", "eu-west-1")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
