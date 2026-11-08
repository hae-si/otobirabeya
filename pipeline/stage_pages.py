import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import tempfile
from zipfile import ZipFile

from pipeline.audit_package import FONT_FILES, SHARD_NAME, SITE_FILES, audit_package


MAX_SITE_BYTES = 1_000_000_000


def stage(archive, expected_sha256, output):
    if not re.fullmatch(r'[0-9a-fA-F]{64}', expected_sha256):
        raise ValueError('Expected a 64-character SHA256')
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)

    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != expected_sha256.lower():
            raise ValueError('Candidate ZIP SHA256 mismatch')
        stream.seek(0)
        with ZipFile(stream) as bundle:
            members = bundle.infolist()
            names = {member.filename for member in members}
            if len(names) != len(members) or not SITE_FILES <= names:
                raise ValueError('ZIP has duplicate or missing site files')
            if any(not SHARD_NAME.fullmatch(name) for name in names - SITE_FILES - FONT_FILES):
                raise ValueError('ZIP has unexpected file names')
            if any(stat.S_IFMT(member.external_attr >> 16) not in (0, stat.S_IFREG)
                   for member in members):
                raise ValueError('ZIP may contain only regular files')
            if sum(member.file_size for member in members) > MAX_SITE_BYTES:
                raise ValueError('ZIP exceeds the Pages site size limit')

            with tempfile.TemporaryDirectory(dir=output.parent) as temp:
                candidate = Path(temp) / 'site'
                candidate.mkdir()
                for member in members:
                    with bundle.open(member) as source, (candidate / member.filename).open('xb') as target:
                        shutil.copyfileobj(source, target)
                result = audit_package(candidate)
                candidate.rename(output)
    return {'sha256': digest, 'files': len(result['files'])}


def main():
    parser = argparse.ArgumentParser(description='Verify and stage a GitHub Pages candidate ZIP')
    parser.add_argument('archive', type=Path)
    parser.add_argument('sha256')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(stage(args.archive, args.sha256, args.output)))


if __name__ == '__main__':
    main()
