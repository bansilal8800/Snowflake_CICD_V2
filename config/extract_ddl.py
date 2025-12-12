# config/extract_ddl.py
import os
import sys
import pandas as pd
from snowflake.connector import connect
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

def fail(message):
    print(f"\nERROR: {message}")
    sys.exit(1)

print("Connecting to Snowflake...")

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

# Connect
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
table = f"{db}.BRONZE.CONFIG_SNOWFLAKE_CICD"

# Check if table exists first
try:
    cur.execute(f"""
        SELECT COUNT(*) 
        FROM {db}.INFORMATION_SCHEMA.TABLES 
        WHERE TABLE_SCHEMA = 'BRONZE' 
          AND TABLE_NAME = 'CONFIG_SNOWFLAKE_CICD'
    """)
    exists = cur.fetchone()[0] > 0
except Exception as e:
    fail(f"Cannot query INFORMATION_SCHEMA to check table existence: {e}")

if not exists:
    fail(f"Config table {table} does not exist. Please create it first or fix the location.")

print(f"Found config table: {table}")

# Now safely query
try:
    cur.execute(f"SELECT * FROM {table} WHERE RELEASE_STATUS = 'N' ORDER BY CICID_RELEASE_NO")
    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description]
    df = pd.DataFrame(rows, columns=columns)
except Exception as e:
    fail(f"Failed to query config table: {e}")

if df.empty:
    print("No pending releases found (RELEASE_STATUS = 'N'). Skipping DDL extraction.")
    sys.exit(0)  # Exit cleanly — not an error

print(f"Found {len(df)} pending release(s):")
print(df[['CICID_RELEASE_NO', 'OBJECT_DATABASE', 'OBJECT_SCHEMA', 'OBJECT_NAME', 'OBJECT_TYPE', 'RELEASE_DIR']]))

# Rest of your logic (unchanged)
def get_next_version(scripts_dir):
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
        next_v = (max_v[0], max_v[1], max_v[2] + 1)
    else:
        next_v = (1, 0, 0)
    return f"{next_v[0]}.{next_v[1]}.{next_v[2]}"

for release_no, group in df.groupby('CICID_RELEASE_NO'):
    release_dir = group['RELEASE_DIR'].iloc[0].strip().upper()
    scripts_dir = f"{release_dir.lower()}/migrations/scripts"
    next_version = get_next_version(scripts_dir)
    file_name = f"V{next_version}__RELEASE_{release_no}.sql"
    file_path = f"{scripts_dir}/{file_name}"
    
    print(f"\nCreating migration file: {file_path}")

    with open(file_path, 'w') as f:
        for _, row in group.iterrows():
            full_object = f"{row['OBJECT_DATABASE']}.{row['OBJECT_SCHEMA']}.{row['OBJECT_NAME']}"
            print(f"  → Extracting DDL: {full_object} ({row['OBJECT_TYPE']})")
            try:
                cur.execute(f"SELECT GET_DDL('{row['OBJECT_TYPE']}', '{full_object}', TRUE)")
                ddl = cur.fetchone()[0]
                f.write(ddl + ';\n\n')
                print(f"    Success: {full_object}")
            except Exception as e:
                fail(f"Failed to get DDL for {full_object}: {e}")

    print(f"Successfully created {file_path}")

    # Mark as done
    cur.execute(f"UPDATE {table} SET RELEASE_STATUS = 'Y' WHERE CICID_RELEASE_NO = {release_no}")
    print(f"Updated RELEASE_STATUS = 'Y' for release {release_no}")

conn.commit()
conn.close()
print("\nDDL extraction completed successfully!")