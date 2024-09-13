import os
from datetime import timedelta
import subprocess

from minio import Minio
from minio.error import S3Error

from dotenv import load_dotenv

load_dotenv()


def create_minio_client():
    access_key = os.getenv("MINIO_ACCESS_KEY")
    secret_key = os.getenv("MINIO_SECRET_KEY")

    minio_client = Minio(
        os.getenv('MINIO_SERVER_ADDRESS'),
        access_key=access_key,
        secret_key=secret_key,
        secure=False  # Change to True if using HTTPS
    )
    return minio_client


def create_minio_bucket(minio_client, server_id):
    minio_client.make_bucket(get_minio_bucket_name(server_id))
    print(f"Successfully created bucket {get_minio_bucket_name(server_id)}")


def get_minio_bucket_name(server_id):
    return f"discord-server-{server_id}"


def delete_minio_bucket(minio_client, bucket_name):
    try:
        # List and delete all objects in the bucket
        objects = minio_client.list_objects(bucket_name, recursive=True)
        for obj in objects:
            minio_client.remove_object(bucket_name, obj.object_name)

        minio_client.remove_bucket(bucket_name)
        print(f"Bucket {bucket_name} has been deleted.")

    except S3Error as e:
        print(f"An error occurred: {e}")


def upload_to_minio(minio_client, server_id, song):
    try:
        ydl_optss = [
            'yt-dlp',
            '-f', 'bestaudio',
            '--no-warnings',
            '--quiet',
            '--output', '-'  # Send output to stdout
        ]

        # Run yt-dlp to download and pipe the audio directly
        process = subprocess.Popen(
            ydl_optss + [song.url],
            stdout=subprocess.PIPE
        )
        bucket_name = f"discord-server-{server_id}"

        # Upload directly to MinIO from the process output
        minio_client.put_object(bucket_name, song.suitable_name, process.stdout,
                                length=song.filesize, content_type="audio/mpeg")
        print(f"Song has been uploaded to {bucket_name}/{song.suitable_name}.")
    except Exception as e:
        print(f"An error occurred: {e}")


def get_presigned_url(minio_client, bucket_name, object_name):
    url = minio_client.presigned_get_object(bucket_name, object_name, expires=timedelta(hours=2))
    return url