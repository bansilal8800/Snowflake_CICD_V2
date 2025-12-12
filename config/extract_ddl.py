# config/extract_ddl.py
import os
import sys
import pandas as pd
from snowflake.connector import connect
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

def fail(message):
    print(f"\nERROR: {message}", file=sys.stderr)
    sys.exit(1)

print("Starting DDL extraction...")

# Load private key
try:
    with open("private_key.pem", "rb") as key_file:
        p_key = serialization.load_pem_private_key(key_file.read(), password=None, backend=default_backend())
    pkb = p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
except Exception as e:
    fail(f"Failed to load private key: {e}")

# Connect to Snowflake
try:
    conn = connect(
        account=os.environ['SF_ACCOUNT'],
        user=os.environ['SF_USERNAME'],
        role=os.environ['SF_ROLE'],
        warehouse=os.environ['SF_WAREHOUSE'],
        database=os.environ['SF_DATABASE'],
        authenticator='snowflake_jwt',
        private_key=pkb
    )
    cur = conn.cursor()
    print("Connected to Snowflake successfully!")
except Exception as e:
    fail(f"Failed to connect to Snowflake: {e}")

db = os.environ['SF_DATABASE']
table = f"{db}.PUBLIC.CONFIG_SNOWFLAKE_CICD"

# Check if table exists
try:
    cur.execute(f"""
        SELECT COUNT(*) 
        FROM {db}.INFORMATION_SCHEMA.TABLES 
        WHERE TABLE_SCHEMA = 'PUBLIC' 
          AND TABLE_NAME = 'CONFIG_SNOWFLAKE_CICD'
    """)
    exists = cur.fetchone()[0] > 0
except Exception as e:
    fail(f"Cannot check if table exists: {e}")

if not exists:
    fail(f"Config table {table} does not exist.")

print(f"Found config table: {table}")

# Query pending rows
try:
    cur.execute(f"SELECT * FROM {table} WHERE RELEASE_STATUS = 'N' ORDER BY CICID_RELEASE_NO")
    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description]
    df = pd.DataFrame(rows, columns=columns)
except Exception as e:
    fail(f"Failed to query pending rows: {e}")

if df.empty:
    print("No pending releases (RELEASE_STATUS = 'N'). Skipping extraction.")
    sys.exit(0)  # Clean exit - not failure

print(f"Found {len(df)} pending rows:")
print(df.to_string(index=False))

def get_next_version(scripts_dir):
    try:
        if not os.path.exists(scripts_dir):
            os.makedirs(scripts_dir)
            print(f"Created directory: {scripts_dir}")
        files = [f for f in os.listdir(scripts_dir) if f.startswith('V') and f.endswith('.sql')]
        versions = []
        for f in files:
            try:
                v = f.split('__')[0][1:]
                major, minor, patch = map(int, v.split('.'))
                versions.append((major, minor, patch))
            except:
                pass
        if versions:
            max_v = max(versions)
            next_v = f"{max_v[0]}.{max_v[1]}.{max_v[2] + 1}"
        else:
            next_v = "1.0.0"
        return next_v
    except Exception as e:
        fail(f"Failed to get next version for {scripts_dir}: {e}")

# Process groups
try:
    for release_no, group in df.groupby('CICID_RELEASE_NO'):
        release_dir = group['RELEASE_DIR'].iloc[0].strip().upper()
        print(f"\nProcessing group CICID_RELEASE_NO = {release_no} (RELEASE_DIR = {release_dir})")
        
        scripts_dir = f"{release_dir.lower()}/migrations/scripts"
        next_version = get_next_version(scripts_dir)
        file_name = f"V{next_version}__RELEASE_{release_no}.sql"
        file_path = f"{scripts_dir}/{file_name}"
        
        print(f"Creating file: {file_path}")
        
        with open(file_path, 'w') as f:
            for _, row in group.iterrows():
                full_object = f"{row['OBJECT_DATABASE']}.{row['OBJECT_SCHEMA']}.{row['OBJECT_NAME']}"
                print(f"  → Fetching DDL for {full_object} ({row['OBJECT_TYPE']})")
                try:
                    cur.execute(f"SELECT GET_DDL('{row['OBJECT_TYPE']}', '{full_object}', TRUE)")
                    ddl = cur.fetchone()[0]
                    f.write(ddl + ';\n\n')
                    print(f"    DDL preview: {ddl[:200]}...")  # Short preview
                except Exception as e:
                    fail(f"Failed to get DDL for {full_object}: {e}")
        
        print(f"Created {file_path} successfully")

        # Update status
        cur.execute(f"UPDATE {table} SET RELEASE_STATUS = 'Y' WHERE CICID_RELEASE_NO = {release_no}")
        print(f"Updated RELEASE_STATUS to 'Y' for {release_no}")
except Exception as e:
    fail(f"Failed during processing: {e}")

conn.commit()
conn.close()
print("\nExtraction completed successfully!")