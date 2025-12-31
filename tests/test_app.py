import gzip
from pathlib import Path
from typing import Any

import pytest

from app import LogFileHandler, read_file_content


class TestableLogFileHandler(LogFileHandler):
    """Expose a public wrapper for the protected `_src_path_to_str` to avoid
    accessing a protected member from tests while keeping implementation
    details encapsulated in the SUT.
    """

    def src_path_to_str(self, src_path: Any) -> str:
        return self._src_path_to_str(src_path)


def test_src_path_to_str_with_bytes() -> None:
    handler = TestableLogFileHandler()
    value = handler.src_path_to_str(b"/tmp/foo.log")
    assert value == "/tmp/foo.log"


def test_src_path_to_str_with_bytearray() -> None:
    handler = TestableLogFileHandler()
    value = handler.src_path_to_str(bytearray(b"/tmp/bar.log"))
    assert value == "/tmp/bar.log"


def test_src_path_to_str_with_memoryview() -> None:
    handler = TestableLogFileHandler()
    mv = memoryview(b"/tmp/baz.log")
    value = handler.src_path_to_str(mv)
    assert value == "/tmp/baz.log"


def test_read_file_content_plain(tmp_path: Path) -> None:
    p = tmp_path / "sample.log"
    p.write_text("hello world", encoding="utf-8")
    content = read_file_content(str(p))
    assert "hello world" in content


def test_read_file_content_gz(tmp_path: Path) -> None:
    p = tmp_path / "sample.log.gz"
    raw = b"gzip content\n"
    with gzip.open(p, "wb") as f:
        f.write(raw)
    content = read_file_content(str(p))
    assert "gzip content" in content


def test_get_log_files_filters_and_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Create a temporary logs dir with some files
    d = tmp_path / "logs"
    d.mkdir()
    (d / "a.log").write_text("a", encoding="utf-8")
    (d / "b.txt").write_text("b", encoding="utf-8")
    (d / "c.log.gz").write_bytes(gzip.compress(b"c"))

    monkeypatch.setenv("ANSIBLE_LOGS_DIR", str(d))
    # Call get_log_files after setting the module constant
    import app as appmod

    appmod.LOGS_DIRECTORY = str(d)
    files = appmod.get_log_files()
    names = {f["name"] for f in files}
    assert "a.log" in names
    assert "c.log.gz" in names
    assert "b.txt" not in names
