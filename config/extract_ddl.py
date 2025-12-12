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
    cur.execute(f"SELECT * FROM {table} WHERE RELEASE_STATUS = 'N' ORDER BY CICD_RELEASE_NO")
    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description]
    df = pd.DataFrame(rows, columns=columns)
except Exception as e:
    fail(f"Failed to query pending rows: {e}")

if df.empty:
    print("No pending releases (RELEASE_STATUS = 'N'). Skipping extraction.")
    sys.exit(0)

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
            return f"{max_v[0]}.{max_v[1]}.{max_v[2] + 1}"
        else:
            return "1.0.0"
    except Exception as e:
        fail(f"Failed to get next version for {scripts_dir}: {e}")

# Process each group = one migration file
for release_no, group in df.groupby('CICD_RELEASE_NO'):
    target_schema = group['RELEASE_DIR'].iloc[0].strip().upper()  # e.g. GOLD
    print(f"\nProcessing release {release_no} → deploying to schema: {target_schema}")

    scripts_dir = f"{target_schema.lower()}/migrations/scripts"
    next_version = get_next_version(scripts_dir)
    file_name = f"V{next_version}__RELEASE_{release_no}.sql"
    file_path = f"{scripts_dir}/{file_name}"

    print(f"Creating migration file: {file_path}")

    with open(file_path, 'w') as f:
        for _, row in group.iterrows():
            source_db = row['OBJECT_DATABASE']
            source_schema = row['OBJECT_SCHEMA']
            object_name = row['OBJECT_NAME']
            object_type = row['OBJECT_TYPE']

            full_source_object = f"{source_db}.{source_schema}.{object_name}"
            print(f"  → Extracting DDL: {full_source_object} ({object_type})")

            try:
                cur.execute(f"SELECT GET_DDL('{object_type}', '{full_source_object}', TRUE)")
                original_ddl = cur.fetchone()[0]

                # REPLACE SOURCE SCHEMA WITH TARGET SCHEMA
                # This handles both quoted and unquoted identifiers safely
                modified_ddl = original_ddl \
                    .replace(f"{source_schema.upper()}.", f"{target_schema}.") \
                    .replace(f'"{source_schema}".', f'"{target_schema}".') \
                    .replace(f"{source_schema.lower()}.", f"{target_schema}.")

                # Also replace in the middle of fully qualified names
                modified_ddl = modified_ddl.replace(f"{source_db}.{source_schema}.", f"{source_db}.{target_schema}.")

                f.write(modified_ddl.strip() + ';\n\n')
                print(f"    Success: Rewrote schema {source_schema} → {target_schema}")

            except Exception as e:
                fail(f"Failed to get or rewrite DDL for {full_source_object}: {e}")

    print(f"Successfully created {file_path}")

    # Update status in Snowflake
    cur.execute(f"UPDATE {table} SET RELEASE_STATUS = 'Y' WHERE CICD_RELEASE_NO = {release_no}")
    print(f"Updated RELEASE_STATUS = 'Y' for release {release_no}")

conn.commit()
conn.close()
print("\nDDL extraction and schema rewrite completed successfully!")