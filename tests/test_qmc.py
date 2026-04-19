from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from nonebot_plugin_kuwo.qmc import (
    decrypt_mflac_file,
    decrypt_qmc_bytes,
    derive_qmc_key,
    extract_qmc_raw_key_from_ekey,
)

SAMPLE_MFLAC_PATH = Path(
    "tests/AIM0000WoYYr0hishZ3b6ff42855ecade7711348a59f29bca0.mflac"
)
KUWO_SAMPLE_EKEY = (
    "+VlgJ5kSGg2sQmRUeoXBZA0xekKR/eEy8hZn9vRWHIjtJJwNoXzJ7Q7QJi04V3cNRt+FUSW1uD0k"
    "JGOPWc6ba0ljj1IbP9FTnfHRaOACTCYOYL/G2QfQRxKdldC/+igzTi+PWAN9CyUhSmV/sdRvkNf"
    "+N5idjhgOzgAY5SYw/TYECkoG2u2jpgz8NjHYicKshfUxhVjyvgPIIe12TVa6NEnjYMr6VVpTRz9"
    "JmEw8+LYFa/WP6iT2cVErciL/8fgo/LKXAVVUU7DvTFFd6jav903pl7+k42hcsCOvOs6v7aKG7vd"
    "e3PXAaPzp8CcnjKX5hp5hQivtVABKfhAcxPNvxfkwdviBFJt0j9UgmUcl0kHhLPC2So1XnYxaWqog"
    "CfJKRrqGPYZjfPH+sv9HW3gb4jM9tOLs4BuBuIaPgMbK8KNfgbKEcrImxPLLzJhYSv2KBS1/f5zW"
    "jFjHwiVFKoVRm7qhcQDN4lk6MShpXg5u3Ps7dpORYtB/AzMh4ws9V12ihYR8JhccUYh3C9jM1CGNP"
    "HCN2EQRYrHUAGkw0t8PGJz2/dFISqjN+gvAKRsX8/6SQRDvAOsO24C3YpXsYlxvLjcb8z7/b0CD8g"
    "Yf+nTlLIU01PKhMwMCoaFpnAiJX9Cn0H6OY7aUvpGH/XKjpRopnOM6GnCpZ+HotTdkp8qftQ1B9gQ"
    "W5V7YDE32kbSa8gZrtnBBci9QtRoD717BU3PFz/hEFuE+O2kxkKxuB7GXoQkAwl+5bkJShaXmdK4o"
    "rw0l1Iq/vwRMiDxfG7XfJdb1JoapyKiWY+2pGoO3Fwjxh9ajHyKOhpd1MGh9YLyAjIHR6y14NXkV0"
    "hbQ5UnGAPQKyC16jIpqVYhZ66Bwvu6eFycdFJcsRUMZZgxBckgImckNoaTAolUFHbPxrgrQGr2m9Z"
    "2S1ug/w8x2/+BM9i3n4FakYJlqGxdIYg0a15zgqMO9"
)


def make_workspace_tmp_path(name: str) -> Path:
    tmp_path = (Path("tests") / ".tmp" / f"{name}_{uuid4().hex}").resolve()
    tmp_path.mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_extract_qmc_raw_key_from_ekey_uses_trailing_704_chars() -> None:
    raw_key = extract_qmc_raw_key_from_ekey(KUWO_SAMPLE_EKEY)

    assert len(raw_key) == 704
    assert raw_key.startswith(b"ajE5Nk5UOUZgLQNW")
    assert raw_key.endswith(b"O2ZkzJabppBa89Y41WmW9yCZx+")


def test_derive_qmc_key_returns_decoded_stream_key() -> None:
    raw_key = extract_qmc_raw_key_from_ekey(KUWO_SAMPLE_EKEY)
    derived_key = derive_qmc_key(raw_key)

    assert isinstance(derived_key, bytes)
    assert len(derived_key) > 300


def test_decrypt_qmc_bytes_can_decrypt_real_sample_header() -> None:
    raw_key = extract_qmc_raw_key_from_ekey(KUWO_SAMPLE_EKEY)
    encrypted_head = SAMPLE_MFLAC_PATH.read_bytes()[:65536]

    decrypted_head = decrypt_qmc_bytes(encrypted_head, raw_key)

    assert decrypted_head.startswith(b"fLaC")


def test_decrypt_mflac_file_can_decrypt_real_sample_header() -> None:
    tmp_path = make_workspace_tmp_path("decrypt_real_sample_header")
    encrypted_head_path = tmp_path / "sample_head.mflac"
    decrypted_head_path = tmp_path / "sample_head.flac"

    with SAMPLE_MFLAC_PATH.open("rb") as source:
        encrypted_head_path.write_bytes(source.read(65536))

    output_path = decrypt_mflac_file(
        encrypted_head_path,
        decrypted_head_path,
        KUWO_SAMPLE_EKEY,
    )

    assert output_path == decrypted_head_path
    assert decrypted_head_path.read_bytes().startswith(b"fLaC")
