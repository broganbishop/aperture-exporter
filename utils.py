import hashlib


def getSHA256(filepath):
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    hash_str = sha256_hash.hexdigest()
    return hash_str

class AlreadyExportedException(Exception):
    pass
