import asyncio
import sys
import uuid
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi import HTTPException, UploadFile
import api.server as server


async def main():
    thread_id = uuid.uuid4()
    with TemporaryDirectory() as directory:
        with patch.object(server, "upload_root", Path(directory)):
            with patch.object(server, "MAX_UPLOAD_BYTES", 4):
                old = UploadFile(file=BytesIO(b"old"), filename="contract.txt")
                await server.upload_file(thread_id, old)
                target = server.session_folder(Path(directory), thread_id) / "contract.txt"
                assert target.read_bytes() == b"old"

                too_large = UploadFile(file=BytesIO(b"12345"), filename="contract.txt")
                try:
                    await server.upload_file(thread_id, too_large)
                except HTTPException as exc:
                    assert exc.status_code == 413
                else:
                    raise AssertionError("超限上传应被拒绝")

                assert target.read_bytes() == b"old"
                assert not list(target.parent.glob(".upload-*"))

                replacement = UploadFile(file=BytesIO(b"new"), filename="contract.txt")
                result = await server.upload_file(thread_id, replacement)
                assert result == {"status": "uploaded", "filename": "contract.txt"}
                assert target.read_bytes() == b"new"
                assert not list(target.parent.glob(".upload-*"))

                cancelled = UploadFile(file=BytesIO(b"unused"), filename="contract.txt")
                with patch.object(
                    cancelled, "read", side_effect=[b"x", asyncio.CancelledError()]
                ):
                    try:
                        await server.upload_file(thread_id, cancelled)
                    except asyncio.CancelledError:
                        pass
                    else:
                        raise AssertionError("取消应向上抛出")
                assert target.read_bytes() == b"new"
                assert not list(target.parent.glob(".upload-*"))
                print("超限和取消后旧文件保留、临时文件已清理；成功后新文件接班")


asyncio.run(main())
