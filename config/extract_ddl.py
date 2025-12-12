# config/extract_ddl.py
import os
import pandas as pd
from snowflake.connector import connect
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

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

# Load private key
with open("private_key.pem", "rb") as key_file:
    p_key = serialization.load_pem_private_key(key_file.read(), password=None, backend=default_backend())
pkb = p_key.private_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)

# Connect
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

db = os.environ['SF_DATABASE']
table = f"{db}.public.config_snowflake_cicd"

cur.execute(f"SELECT * FROM {table} WHERE RELEASE_STATUS = 'N' ORDER BY CICID_RELEASE_NO")
rows = cur.fetchall()
columns = [desc[0] for desc in cur.description]
df = pd.DataFrame(rows, columns=columns)

if df.empty:
    print("No pending releases found (RELEASE_STATUS = 'N')")
else:
    print(f"Found {len(df)} pending release(s):")
    print(df[['CICID_RELEASE_NO', 'OBJECT_DATABASE', 'OBJECT_SCHEMA', 'OBJECT_NAME', 'OBJECT_TYPE', 'RELEASE_DIR']])

    for release_no, group in df.groupby('CICID_RELEASE_NO'):
        release_dir = group['RELEASE_DIR'].iloc[0].upper()
        scripts_dir = f"{release_dir.lower()}/migrations/scripts"
        next_version = get_next_version(scripts_dir)
        file_name = f"V{next_version}__RELEASE_{release_no}.sql"
        file_path = f"{scripts_dir}/{file_name}"
        
        print(f"\nCreating migration file: {file_path}")

        with open(file_path, 'w') as f:
            for _, row in group.iterrows():
                full_object = f"{row['OBJECT_DATABASE']}.{row['OBJECT_SCHEMA']}.{row['OBJECT_NAME']}"
                print(f"  → Extracting DDL for {full_object} ({row['OBJECT_TYPE']})")
                cur.execute(f"SELECT GET_DDL('{row['OBJECT_TYPE']}', '{full_object}', TRUE)")
                ddl = cur.fetchone()[0]
                f.write(ddl + ';\n\n')
                print(f"    Success: {full_object}")

        print(f"Successfully created {file_path}")

        # Update status
        cur.execute(f"UPDATE {table} SET RELEASE_STATUS = 'Y' WHERE CICID_RELEASE_NO = {release_no}")
        print(f"Updated RELEASE_STATUS to 'Y' for release {release_no}")

conn.commit()
conn.close()
print("\nDDL extraction completed successfully!")