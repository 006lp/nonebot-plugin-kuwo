from __future__ import annotations

from pathlib import Path
from typing import Protocol, cast

from ._native import load_extension


class _QmcExtension(Protocol):
    def kuwo_base64_decrypt(self, value: str) -> str: ...
    def extract_qmc_raw_key_from_ekey(self, ekey: str) -> bytes: ...
    def derive_qmc_key(self, raw_key: bytes) -> bytes: ...
    def decrypt_qmc_bytes(
        self, data: bytes, raw_key: bytes, offset: int = 0
    ) -> bytes: ...
    def decrypt_mflac_file(
        self,
        source_path: str,
        target_path: str,
        ekey: str,
        chunk_size: int = 65536,
    ) -> None: ...


def _load_extension() -> _QmcExtension:
    return cast(_QmcExtension, load_extension())


def kuwo_base64_decrypt(value: str) -> str:
    return _load_extension().kuwo_base64_decrypt(value)


def extract_qmc_raw_key_from_ekey(ekey: str) -> bytes:
    return _load_extension().extract_qmc_raw_key_from_ekey(ekey)


def derive_qmc_key(raw_key: bytes | str) -> bytes:
    normalized_raw_key = raw_key.encode() if isinstance(raw_key, str) else raw_key
    return _load_extension().derive_qmc_key(normalized_raw_key)


def decrypt_qmc_bytes(data: bytes, raw_key: bytes | str, offset: int = 0) -> bytes:
    normalized_raw_key = raw_key.encode() if isinstance(raw_key, str) else raw_key
    return _load_extension().decrypt_qmc_bytes(data, normalized_raw_key, offset)


def decrypt_mflac_file(
    source_path: Path,
    target_path: Path,
    ekey: str,
    chunk_size: int = 65536,
) -> Path:
    _load_extension().decrypt_mflac_file(
        str(source_path),
        str(target_path),
        ekey,
        chunk_size,
    )
    return target_path


__all__ = [
    "decrypt_mflac_file",
    "decrypt_qmc_bytes",
    "derive_qmc_key",
    "extract_qmc_raw_key_from_ekey",
    "kuwo_base64_decrypt",
]
