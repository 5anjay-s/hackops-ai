"""Create deployment zip for Lambda."""
import zipfile
import os

zip_path = "d:/hackops-ai/deploy/hackops-lambda.zip"
root = "d:/hackops-ai/deploy/package"

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for dp, dn, filenames in os.walk(root):
        if "__pycache__" in dp:
            continue
        for f in filenames:
            full_path = os.path.join(dp, f)
            arcname = os.path.relpath(full_path, root)
            z.write(full_path, arcname)

size_mb = os.path.getsize(zip_path) / 1024 / 1024
print(f"Zip created: {size_mb:.2f} MB")
