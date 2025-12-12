# config/extract_ddl.py
import snowflake.connector
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import os
import pandas as pd

def get_next_version(scripts_dir):
    if not os.path.exists(scripts_dir):
        os.makedirs(scripts_dir)
    files = [f for f in os.listdir(scripts_dir) if f.startswith('V') and f.endswith('.sql')]
    versions = []
    for f in files:
        v_str = f.split('__')[0][1:]  # e.g., '1.1.7'
        try:
            major, minor, patch = map(int, v_str.split('.'))
            versions.append((major, minor, patch))
        except ValueError:
            pass  # Skip invalid
    if versions:
        max_v = max(versions)
        return f"{max_v[0]}.{max_v[1]}.{max_v[2] + 1}"
    else:
        return "1.0.0"

# Load private key for JWT
with open("private_key.pem", "rb") as key_file:
    p_key = serialization.load_pem_private_key(
        key_file.read(),
        password=None,  # Add passphrase if needed
        backend=default_backend()
    )
pkb = p_key.private_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)

# Connect to Snowflake
conn = snowflake.connector.connect(
    account=os.environ['SF_ACCOUNT'],
    user=os.environ['SF_USERNAME'],
    role=os.environ['SF_ROLE'],
    warehouse=os.environ['SF_WAREHOUSE'],
    authenticator='snowflake_jwt',
    private_key=pkb
)
cur = conn.cursor()

# Assume table in <SF_DATABASE>.BRONZE.CONFIG_SNOWFLAKE_CICD (adjust if needed)
db = os.environ['SF_DATABASE']
table = f"{db}.BRONZE.CONFIG_SNOWFLAKE_CICD"

cur.execute(f"USE DATABASE {db}")
cur.execute(f"SELECT * FROM {table} WHERE RELEASE_STATUS = 'N'")
columns = [desc[0] for desc in cur.description]
results = pd.DataFrame(cur.fetchall(), columns=columns)

processed = []
if not results.empty:
    groups = results.groupby('CICID_RELEASE_NO')
    for release_no, group in groups:
        release_dir = group['RELEASE_DIR'].iloc[0].lower()  # e.g., 'gold'
        if not all(group['RELEASE_DIR'].str.lower() == release_dir):
            raise ValueError(f"Inconsistent RELEASE_DIR for release {release_no}")
        
        scripts_dir = f"{release_dir}/migrations/scripts"
        next_v = get_next_version(scripts_dir)
        file_name = f"V{next_v}__RELEASE_{release_no}.sql"
        file_path = f"{scripts_dir}/{file_name}"
        
        with open(file_path, 'w') as f:
            for _, row in group.iterrows():
                full_object = f"{row['OBJECT_DATABASE']}.{row['OBJECT_SCHEMA']}.{row['OBJECT_NAME']}"
                ddl_query = f"SELECT GET_DDL('{row['OBJECT_TYPE']}', '{full_object}', TRUE)"
                cur.execute(ddl_query)
                ddl = cur.fetchone()[0]
                f.write(ddl + ';\n\n')
        
        print(f"Created migration file: {file_path}")
        processed.append(release_no)
else:
    print("No pending releases found.")

# Update status to 'Y'
if processed:
    for rel in processed:
        cur.execute(f"UPDATE {table} SET RELEASE_STATUS = 'Y' WHERE CICID_RELEASE_NO = {rel} AND RELEASE_STATUS = 'N'")
    conn.commit()

# Cleanup
cur.close()
conn.close()