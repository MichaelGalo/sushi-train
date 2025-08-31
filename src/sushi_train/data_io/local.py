import polars as pl

def write_dataframe_to_local_csv(dataframe, file_path):
    try:
        result = dataframe.to_csv(file_path, index=False)
        return result
    except Exception as e:
        print(f"Error in writing dataframe locally: {e}")
        return None

def read_local_csv_to_dataframe(file_path):
    try:
        result = pl.read_csv(file_path)
        return result
    except Exception as e:
        print(f"Error in reading local file: {e}")
        return None
    
def write_dataframe_to_local_parquet(dataframe, file_path):
    try:
        result = dataframe.to_parquet(file_path, index=False)
        return result
    except Exception as e:
        print(f"Error in writing dataframe locally: {e}")
        return None
    
def read_local_parquet_to_dataframe(file_path):
    try:
        result = pl.read_parquet(file_path)
        return result
    except Exception as e:
        print(f"Error in reading local file: {e}")
        return None

def write_dataframe_to_local_json(dataframe, file_path):
    try:
        result = dataframe.to_json(file_path, index=False)
        return result
    except Exception as e:
        print(f"Error in writing dataframe locally: {e}")
        return None

def read_local_json_to_dataframe(file_path):
    try:
        result = pl.read_json(file_path)
        return result
    except Exception as e:
        print(f"Error in reading local file: {e}")
        return None