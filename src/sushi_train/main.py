import sys
import os
import io
import duckdb
import polars as pl
from urllib.parse import urlencode
current_path = os.path.dirname(os.path.abspath(__file__))
parent_path = os.path.abspath(os.path.join(current_path, ".."))
sys.path.append(parent_path)

def execute_SQL_file_list(con, list_of_file_paths):
    """
    Execute a list of SQL files against the provided DuckDB connection.

    Parameters
    - con: duckdb connection object to execute SQL on.
    - list_of_file_paths: iterable of file paths (relative to project parent) containing SQL statements.

    Raises
    - FileNotFoundError: if any SQL file is missing.
    - Exception: re-raises underlying execution errors.
    """
    for file_path in list_of_file_paths:
        full_path = os.path.join(parent_path, file_path)
        if not os.path.exists(full_path):
            raise FileNotFoundError(full_path)

        with open(full_path, 'r') as file:
            sql = file.read()
        try:
            con.execute(sql)
        except Exception as e:
            raise

def duckdb_memory_con_init():
    """
    Initialize a DuckDB in-memory connection and load required extensions.

    This function installs and loads the `ducklake` and `httpfs` extensions
    then returns a fresh in-memory DuckDB connection.

    Returns
    - con: a duckdb.Connection instance connected to ':memory:'.
    """
    duckdb.install_extension("ducklake")
    duckdb.install_extension("httpfs")
    duckdb.load_extension("ducklake")
    duckdb.load_extension("httpfs")
    con = duckdb.connect(':memory:')
    return con

def ducklake_init(con, data_path, catalog_path):
    """
    Attach and switch to a DuckLake catalog on the given DuckDB connection.

    Parameters
    - con: duckdb connection
    - data_path: path where ducklake will store data
    - catalog_path: path to the ducklake catalog to attach
    """
    con.execute(f"ATTACH 'ducklake:{catalog_path}' AS my_ducklake (DATA_PATH '{data_path}')")
    con.execute("USE my_ducklake")

def ducklake_attach_minio(con, minio_access_key, minio_secret_key, minio_endpoint):
    """
    Configure S3/MinIO credentials and endpoint for DuckDB/DuckLake session.

    Parameters
    - con: duckdb connection
    - minio_access_key: access key id for MinIO
    - minio_secret_key: secret key for MinIO
    - minio_endpoint: endpoint URL or host for MinIO
    """
    con.execute(f"SET s3_access_key_id = '{minio_access_key}'")
    con.execute(f"SET s3_secret_access_key = '{minio_secret_key}'")
    con.execute(f"SET s3_endpoint = '{minio_endpoint}'")
    con.execute("SET s3_use_ssl = false")
    con.execute("SET s3_url_style = 'path'")

def ducklake_medallion_schema_creation(con):
    """
    Create medallion-style schemas (RAW, STAGED, CLEANED) if they do not exist.

    Parameters
    - con: duckdb connection
    """
    con.execute("CREATE SCHEMA IF NOT EXISTS RAW")
    con.execute("CREATE SCHEMA IF NOT EXISTS STAGED")
    con.execute("CREATE SCHEMA IF NOT EXISTS CLEANED")

def ducklake_refresh(con):
    """
    Refresh DuckLake state by expiring snapshots and cleaning up old files.

    Parameters
    - con: duckdb connection
    """
    con.execute("CALL ducklake_expire_snapshots('my_ducklake', older_than => now())")
    con.execute("CALL ducklake_cleanup_old_files('my_ducklake', cleanup_all => true)")

def update_ducklake_from_minio_parquets(con, bucket_name, source_folder_path, target_folder_path):
    """
    Read Parquet files from a MinIO (S3) bucket and create/replace tables in DuckLake.

    Parameters
    - con: duckdb connection
    - bucket_name: name of the S3/MinIO bucket
    - source_folder_path: folder inside the bucket with parquet files
    - target_folder_path: target schema or path in DuckLake where tables are created

    Behavior
    - Uses `glob` to list parquet files in the source path
    - For each parquet file, creates or replaces a table named after the file
      (uppercased, hyphens/spaces replaced with underscores)
    - Adds metadata columns: _source_file, _ingestion_timestamp, _record_id

    Raises
    - Re-raises any exception encountered while listing or creating tables.
    """
    file_list_query = f"SELECT * FROM glob('s3://{bucket_name}/{source_folder_path}/*.parquet')"

    try:
        files_result = con.execute(file_list_query).fetchall()
        file_paths = []
        for row in files_result:
            file_paths.append(row[0])
        
        for file_path in file_paths:
            file_name = os.path.basename(file_path).replace('.parquet', '')
            table_name = file_name.upper().replace('-', '_').replace(' ', '_')

            query = f"""
            CREATE OR REPLACE TABLE {target_folder_path}.{table_name} AS
            SELECT 
                *,
                '{file_name}' AS _source_file,
                CURRENT_TIMESTAMP AS _ingestion_timestamp,
                ROW_NUMBER() OVER () AS _record_id
            FROM read_parquet('{file_path}');
            """
            
            con.execute(query)

    except Exception as e:
        raise


def write_data_to_minio_from_parquet_buffer(parquet_buffer, minio_client, bucket_name, object_name, folder_name=None):    
    """
    Upload a parquet binary buffer to MinIO as an object.

    Parameters
    - parquet_buffer: io.BytesIO containing parquet bytes (will be seeked to 0)
    - minio_client: an instantiated MinIO client with put_object method
    - bucket_name: target bucket name
    - object_name: desired object name (filename)
    - folder_name: optional folder inside bucket to place the object

    Raises
    - Re-raises any exception from the MinIO client.
    """
    parquet_buffer.seek(0)
    data_bytes = parquet_buffer.read()

    if folder_name:
        folder_name = folder_name.strip("/")
        full_object_name = f"{folder_name}/{object_name}"
    else:
        full_object_name = object_name

    try:
        minio_client.put_object(
            bucket_name,
            full_object_name,
            io.BytesIO(data_bytes),
            length=len(data_bytes),
            content_type="application/x-parquet",
        )
    except Exception as e:
        raise

def add_query_params_to_url(base_url, params):
    """
    Append query parameters to a base URL without parsing the URL first.

    - Skips parameters with value None.
    - Values are converted to strings and URL-encoded.
    - Preserves existing query separators on the base_url.

    Parameters
    - base_url: the URL string to append params to
    - params: mapping of keys to values (values of None are skipped)

    Returns
    - A new URL string with encoded query parameters appended.
    """
    if not params:
        return base_url

    cleaned_params = {}
    for name, value in params.items():
        if value is None:
            continue
        cleaned_params[str(name)] = str(value)

    if not cleaned_params:
        return base_url

    encoded_query = urlencode(cleaned_params, doseq=True)

    if base_url.endswith('?') or base_url.endswith('&'):
        separator = ''
    elif '?' in base_url:
        separator = '&'
    else:
        separator = '?'

    result = f"{base_url}{separator}{encoded_query}"
    return result


def convert_df_to_parquet_buffer(dataframe):
    """
    Convert a Polars DataFrame to an in-memory parquet buffer (io.BytesIO).

    Parameters
    - dataframe: a polars.DataFrame instance

    Returns
    - io.BytesIO containing parquet data on success, or None on failure.
    """
    buffer = io.BytesIO()
    try:
        dataframe.write_parquet(buffer)
        buffer.seek(0)
        result = buffer
        return result
    except Exception as e:
        return None