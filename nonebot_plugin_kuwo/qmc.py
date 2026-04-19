from __future__ import annotations

import base64
import binascii
import math
import struct
from pathlib import Path

_KUWO_SECRET_KEY = b"ylzsxkwm"
_QMC_RAW_KEY_LENGTHS = (704, 364)
_QMC_V2_KEY_PREFIX = b"QQMusic EncV2,Key:"
_RC4_FIRST_SEGMENT_SIZE = 128
_RC4_SEGMENT_SIZE = 5120

_ARRAY_E = [
    31, 0, 1, 2, 3, 4, -1, -1,
    3, 4, 5, 6, 7, 8, -1, -1,
    7, 8, 9, 10, 11, 12, -1, -1,
    11, 12, 13, 14, 15, 16, -1, -1,
    15, 16, 17, 18, 19, 20, -1, -1,
    19, 20, 21, 22, 23, 24, -1, -1,
    23, 24, 25, 26, 27, 28, -1, -1,
    27, 28, 29, 30, 31, 30, -1, -1,
]

_ARRAY_IP = [
    57, 49, 41, 33, 25, 17, 9, 1,
    59, 51, 43, 35, 27, 19, 11, 3,
    61, 53, 45, 37, 29, 21, 13, 5,
    63, 55, 47, 39, 31, 23, 15, 7,
    56, 48, 40, 32, 24, 16, 8, 0,
    58, 50, 42, 34, 26, 18, 10, 2,
    60, 52, 44, 36, 28, 20, 12, 4,
    62, 54, 46, 38, 30, 22, 14, 6,
]

_ARRAY_IP_1 = [
    39, 7, 47, 15, 55, 23, 63, 31,
    38, 6, 46, 14, 54, 22, 62, 30,
    37, 5, 45, 13, 53, 21, 61, 29,
    36, 4, 44, 12, 52, 20, 60, 28,
    35, 3, 43, 11, 51, 19, 59, 27,
    34, 2, 42, 10, 50, 18, 58, 26,
    33, 1, 41, 9, 49, 17, 57, 25,
    32, 0, 40, 8, 48, 16, 56, 24,
]

_ARRAY_LS = [1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1]
_ARRAY_LS_MASK = [0, 0x100001, 0x300003]
_ARRAY_MASK = [2**i for i in range(64)]
_ARRAY_MASK[-1] *= -1

_ARRAY_P = [
    15, 6, 19, 20, 28, 11, 27, 16,
    0, 14, 22, 25, 4, 17, 30, 9,
    1, 7, 23, 13, 31, 26, 2, 8,
    18, 12, 29, 5, 21, 10, 3, 24,
]

_ARRAY_PC_1 = [
    56, 48, 40, 32, 24, 16, 8, 0,
    57, 49, 41, 33, 25, 17, 9, 1,
    58, 50, 42, 34, 26, 18, 10, 2,
    59, 51, 43, 35, 62, 54, 46, 38,
    30, 22, 14, 6, 61, 53, 45, 37,
    29, 21, 13, 5, 60, 52, 44, 36,
    28, 20, 12, 4, 27, 19, 11, 3,
]

_ARRAY_PC_2 = [
    13, 16, 10, 23, 0, 4, -1, -1,
    2, 27, 14, 5, 20, 9, -1, -1,
    22, 18, 11, 3, 25, 7, -1, -1,
    15, 6, 26, 19, 12, 1, -1, -1,
    40, 51, 30, 36, 46, 54, -1, -1,
    29, 39, 50, 44, 32, 47, -1, -1,
    43, 48, 38, 55, 33, 52, -1, -1,
    45, 41, 49, 35, 28, 31, -1, -1,
]

_MATRIX_NS_BOX = [
    [
        14, 4, 3, 15, 2, 13, 5, 3,
        13, 14, 6, 9, 11, 2, 0, 5,
        4, 1, 10, 12, 15, 6, 9, 10,
        1, 8, 12, 7, 8, 11, 7, 0,
        0, 15, 10, 5, 14, 4, 9, 10,
        7, 8, 12, 3, 13, 1, 3, 6,
        15, 12, 6, 11, 2, 9, 5, 0,
        4, 2, 11, 14, 1, 7, 8, 13,
    ],
    [
        15, 0, 9, 5, 6, 10, 12, 9,
        8, 7, 2, 12, 3, 13, 5, 2,
        1, 14, 7, 8, 11, 4, 0, 3,
        14, 11, 13, 6, 4, 1, 10, 15,
        3, 13, 12, 11, 15, 3, 6, 0,
        4, 10, 1, 7, 8, 4, 11, 14,
        13, 8, 0, 6, 2, 15, 9, 5,
        7, 1, 10, 12, 14, 2, 5, 9,
    ],
    [
        10, 13, 1, 11, 6, 8, 11, 5,
        9, 4, 12, 2, 15, 3, 2, 14,
        0, 6, 13, 1, 3, 15, 4, 10,
        14, 9, 7, 12, 5, 0, 8, 7,
        13, 1, 2, 4, 3, 6, 12, 11,
        0, 13, 5, 14, 6, 8, 15, 2,
        7, 10, 8, 15, 4, 9, 11, 5,
        9, 0, 14, 3, 10, 7, 1, 12,
    ],
    [
        7, 10, 1, 15, 0, 12, 11, 5,
        14, 9, 8, 3, 9, 7, 4, 8,
        13, 6, 2, 1, 6, 11, 12, 2,
        3, 0, 5, 14, 10, 13, 15, 4,
        13, 3, 4, 9, 6, 10, 1, 12,
        11, 0, 2, 5, 0, 13, 14, 2,
        8, 15, 7, 4, 15, 1, 10, 7,
        5, 6, 12, 11, 3, 8, 9, 14,
    ],
    [
        2, 4, 8, 15, 7, 10, 13, 6,
        4, 1, 3, 12, 11, 7, 14, 0,
        12, 2, 5, 9, 10, 13, 0, 3,
        1, 11, 15, 5, 6, 8, 9, 14,
        14, 11, 5, 6, 4, 1, 3, 10,
        2, 12, 15, 0, 13, 2, 8, 5,
        11, 8, 0, 15, 7, 14, 9, 4,
        12, 7, 10, 9, 1, 13, 6, 3,
    ],
    [
        12, 9, 0, 7, 9, 2, 14, 1,
        10, 15, 3, 4, 6, 12, 5, 11,
        1, 14, 13, 0, 2, 8, 7, 13,
        15, 5, 4, 10, 8, 3, 11, 6,
        10, 4, 6, 11, 7, 9, 0, 6,
        4, 2, 13, 1, 9, 15, 3, 8,
        15, 3, 1, 14, 12, 5, 11, 0,
        2, 12, 14, 7, 5, 10, 8, 13,
    ],
    [
        4, 1, 3, 10, 15, 12, 5, 0,
        2, 11, 9, 6, 8, 7, 6, 9,
        11, 4, 12, 15, 0, 3, 10, 5,
        14, 13, 7, 8, 13, 14, 1, 2,
        13, 6, 14, 9, 4, 1, 2, 14,
        11, 13, 5, 0, 1, 10, 8, 3,
        0, 11, 3, 5, 9, 4, 15, 2,
        7, 8, 12, 15, 10, 7, 6, 12,
    ],
    [
        13, 7, 10, 0, 6, 9, 5, 15,
        8, 4, 3, 10, 11, 14, 12, 5,
        2, 11, 9, 6, 15, 12, 0, 3,
        4, 1, 14, 13, 1, 2, 7, 8,
        1, 2, 12, 15, 10, 4, 0, 3,
        13, 14, 6, 9, 7, 8, 9, 6,
        15, 1, 5, 12, 3, 10, 14, 5,
        8, 7, 11, 0, 4, 13, 2, 11,
    ],
]

_QMC_V2_DERIVE_KEY_1 = bytes(
    [0x33, 0x38, 0x36, 0x5A, 0x4A, 0x59, 0x21, 0x40, 0x23, 0x2A, 0x24, 0x25, 0x5E, 0x26, 0x29, 0x28]
)
_QMC_V2_DERIVE_KEY_2 = bytes(
    [0x2A, 0x2A, 0x23, 0x21, 0x28, 0x23, 0x24, 0x25, 0x26, 0x5E, 0x61, 0x31, 0x63, 0x5A, 0x2C, 0x54]
)


def _bit_transform(arr_int: list[int], n: int, value: int) -> int:
    transformed = 0
    for i in range(n):
        if arr_int[i] < 0 or value & _ARRAY_MASK[arr_int[i]] == 0:
            continue
        transformed |= _ARRAY_MASK[i]
    return transformed


def _des64(longs: list[int], value: int) -> int:
    output = _bit_transform(_ARRAY_IP, 64, value)
    source = [output & 0xFFFFFFFF, ((output & -4294967296) >> 32)]
    partial = [0] * 8
    for i in range(16):
        right = source[1]
        right = _bit_transform(_ARRAY_E, 64, right)
        right ^= longs[i]
        for j in range(8):
            partial[j] = 255 & (right >> (j * 8))
        s_out = 0
        for box_index in range(7, -1, -1):
            s_out <<= 4
            s_out |= _MATRIX_NS_BOX[box_index][partial[box_index]]
        right = _bit_transform(_ARRAY_P, 32, s_out)
        left = source[0]
        source[0] = source[1]
        source[1] = left ^ right
    source.reverse()
    output = ((source[1] << 32) & -4294967296) | (source[0] & 0xFFFFFFFF)
    return _bit_transform(_ARRAY_IP_1, 64, output)


def _sub_keys(value: int, mode: int) -> list[int]:
    key_schedule = [0] * 16
    transformed = _bit_transform(_ARRAY_PC_1, 56, value)
    for i in range(16):
        transformed = (
            ((transformed & _ARRAY_LS_MASK[_ARRAY_LS[i]]) << (28 - _ARRAY_LS[i]))
            | ((transformed & ~_ARRAY_LS_MASK[_ARRAY_LS[i]]) >> _ARRAY_LS[i])
        )
        key_schedule[i] = _bit_transform(_ARRAY_PC_2, 64, transformed)
    if mode == 1:
        for i in range(8):
            key_schedule[i], key_schedule[15 - i] = key_schedule[15 - i], key_schedule[i]
    return key_schedule


def _kuwo_crypto(msg: bytes, mode: int, key: bytes = _KUWO_SECRET_KEY) -> list[int]:
    if mode == 1 and len(msg) % 8 != 0:
        raise ValueError("Invalid message length: msg must be a multiple of 8 in decrypt mode.")
    if mode == 0:
        padding_length = 8 - len(msg) % 8
        msg += b"\x00" * padding_length
    elif mode != 1:
        raise ValueError(f"Invalid mode: {mode}. Mode must be 0 (encrypt) or 1 (decrypt).")

    key_block = 0
    for i in range(8):
        key_block |= key[i] << (i * 8)
    schedule = _sub_keys(key_block, mode)

    input_blocks = [0] * (len(msg) // 8)
    for block_index in range(len(input_blocks)):
        for byte_index in range(8):
            input_blocks[block_index] |= msg[byte_index + block_index * 8] << (byte_index * 8)

    encrypted_blocks = [_des64(schedule, block) for block in input_blocks]
    result = [0] * (8 * len(encrypted_blocks))
    offset = 0
    for block in encrypted_blocks:
        for byte_index in range(8):
            result[offset] = (255 & (block >> (byte_index * 8)))
            offset += 1
    return result


def kuwo_base64_decrypt(value: str) -> str:
    decoded = base64.b64decode(value)
    result = bytes(_kuwo_crypto(decoded, 1))
    return result.rstrip(b"\x00").decode("utf-8")


def extract_qmc_raw_key_from_ekey(ekey: str) -> bytes:
    decrypted = kuwo_base64_decrypt(ekey)
    for key_length in _QMC_RAW_KEY_LENGTHS:
        if len(decrypted) < key_length:
            continue
        candidate = decrypted[-key_length:]
        try:
            base64.b64decode(candidate, validate=True)
        except (binascii.Error, ValueError):
            continue
        return candidate.encode()
    raise ValueError("Cannot extract QMC raw key from kuwo ekey.")


def _simple_make_key(salt: int, length: int) -> bytes:
    key = bytearray(length)
    for i in range(length):
        key[i] = int(abs(math.tan(float(salt) + float(i) * 0.1)) * 100.0) & 0xFF
    return bytes(key)


def _tea_decrypt_block(block: bytes, key: bytes) -> bytes:
    v0, v1 = struct.unpack(">2I", block)
    k0, k1, k2, k3 = struct.unpack(">4I", key)
    delta = 0x9E3779B9
    rounds = 32
    sum_value = (delta * (rounds // 2)) & 0xFFFFFFFF
    for _ in range(rounds // 2):
        v1 = (v1 - (((v0 << 4) + k2) ^ (v0 + sum_value) ^ ((v0 >> 5) + k3))) & 0xFFFFFFFF
        v0 = (v0 - (((v1 << 4) + k0) ^ (v1 + sum_value) ^ ((v1 >> 5) + k1))) & 0xFFFFFFFF
        sum_value = (sum_value - delta) & 0xFFFFFFFF
    return struct.pack(">2I", v0, v1)


def _xor_8_bytes(left: bytes | bytearray, right: bytes | bytearray) -> bytearray:
    return bytearray((left[i] ^ right[i]) for i in range(8))


def _decrypt_tencent_tea(input_buffer: bytes, key: bytes) -> bytes:
    salt_len = 2
    zero_len = 7
    if len(input_buffer) % 8 != 0:
        raise ValueError("inBuf size not a multiple of the block size")
    if len(input_buffer) < 16:
        raise ValueError("inBuf size too small")

    decrypted_block = bytearray(_tea_decrypt_block(input_buffer[:8], key))
    pad_len = decrypted_block[0] & 0x7
    output_len = len(input_buffer) - 1 - pad_len - salt_len - zero_len
    output = bytearray(output_len)

    iv_prev = bytearray(8)
    iv_cur = input_buffer[:8]
    input_pos = 8
    dest_idx = 1 + pad_len

    def decrypt_next_block() -> tuple[bytearray, bytearray, bytes, int, int]:
        nonlocal decrypted_block, iv_prev, iv_cur, input_pos, dest_idx
        iv_prev = bytearray(iv_cur)
        iv_cur = input_buffer[input_pos : input_pos + 8]
        decrypted_block = _xor_8_bytes(decrypted_block, iv_cur)
        decrypted_block = bytearray(_tea_decrypt_block(bytes(decrypted_block), key))
        input_pos += 8
        dest_idx = 0
        return decrypted_block, iv_prev, iv_cur, input_pos, dest_idx

    i = 1
    while i <= salt_len:
        if dest_idx < 8:
            dest_idx += 1
            i += 1
        else:
            decrypt_next_block()

    output_pos = 0
    while output_pos < output_len:
        if dest_idx < 8:
            output[output_pos] = decrypted_block[dest_idx] ^ iv_prev[dest_idx]
            dest_idx += 1
            output_pos += 1
        else:
            decrypt_next_block()

    i = 1
    while i <= zero_len:
        if dest_idx < 8:
            if decrypted_block[dest_idx] != iv_prev[dest_idx]:
                raise ValueError("zero check failed")
            dest_idx += 1
            i += 1
        else:
            decrypt_next_block()

    return bytes(output)


def _derive_key_v1(raw_key_decoded: bytes) -> bytes:
    if len(raw_key_decoded) < 16:
        raise ValueError("key length is too short")

    simple_key = _simple_make_key(106, 8)
    tea_key = bytearray(16)
    for i in range(8):
        tea_key[i << 1] = simple_key[i]
        tea_key[(i << 1) + 1] = raw_key_decoded[i]

    decrypted = _decrypt_tencent_tea(raw_key_decoded[8:], bytes(tea_key))
    return raw_key_decoded[:8] + decrypted


def _derive_key_v2(raw_key: bytes) -> bytes:
    buffer = _decrypt_tencent_tea(raw_key, _QMC_V2_DERIVE_KEY_1)
    buffer = _decrypt_tencent_tea(buffer, _QMC_V2_DERIVE_KEY_2)
    return base64.b64decode(buffer)


def derive_qmc_key(raw_key: bytes | str) -> bytes:
    if isinstance(raw_key, str):
        raw_key = raw_key.encode()
    decoded = base64.b64decode(raw_key)
    if decoded.startswith(_QMC_V2_KEY_PREFIX):
        decoded = _derive_key_v2(decoded[len(_QMC_V2_KEY_PREFIX) :])
    return _derive_key_v1(decoded)


class _MapCipher:
    def __init__(self, key: bytes) -> None:
        if not key:
            raise ValueError("qmc map cipher key cannot be empty")
        self.key = key
        self.size = len(key)

    def _get_mask(self, offset: int) -> int:
        if offset > 0x7FFF:
            offset %= 0x7FFF
        index = (offset * offset + 71214) % self.size
        return self._rotate(self.key[index], index & 0x7)

    @staticmethod
    def _rotate(value: int, bits: int) -> int:
        rotate = (bits + 4) % 8
        left = (value << rotate) & 0xFF
        right = value >> rotate
        return left | right

    def decrypt(self, buffer: bytearray, offset: int) -> None:
        for i in range(len(buffer)):
            buffer[i] ^= self._get_mask(offset + i)


class _Rc4Cipher:
    def __init__(self, key: bytes) -> None:
        if not key:
            raise ValueError("qmc rc4 cipher key cannot be empty")
        self.key = key
        self.size = len(key)
        self.box = bytearray((i & 0xFF) for i in range(self.size))
        j = 0
        for i in range(self.size):
            j = (j + self.box[i] + key[i % self.size]) % self.size
            self.box[i], self.box[j] = self.box[j], self.box[i]
        self.hash = self._get_hash_base()

    def _get_hash_base(self) -> int:
        result = 1
        for value in self.key:
            if value == 0:
                continue
            next_hash = (result * value) & 0xFFFFFFFF
            if next_hash == 0 or next_hash <= result:
                break
            result = next_hash
        return result

    def _get_segment_skip(self, segment_id: int) -> int:
        seed = self.key[segment_id % self.size]
        index = int((self.hash / ((segment_id + 1) * seed)) * 100.0)
        return index % self.size

    def _decrypt_first_segment(self, buffer: bytearray, offset: int) -> None:
        for i in range(len(buffer)):
            buffer[i] ^= self.key[self._get_segment_skip(offset + i)]

    def _decrypt_segment(self, buffer: bytearray, offset: int) -> None:
        box = bytearray(self.box)
        j = 0
        k = 0
        skip_length = (offset % _RC4_SEGMENT_SIZE) + self._get_segment_skip(offset // _RC4_SEGMENT_SIZE)
        for i in range(-skip_length, len(buffer)):
            j = (j + 1) % self.size
            k = (box[j] + k) % self.size
            box[j], box[k] = box[k], box[j]
            if i >= 0:
                buffer[i] ^= box[(box[j] + box[k]) % self.size]

    def decrypt(self, buffer: bytearray, offset: int) -> None:
        to_process = len(buffer)
        processed = 0

        def mark_processed(size: int) -> bool:
            nonlocal offset, to_process, processed
            offset += size
            to_process -= size
            processed += size
            return to_process == 0

        if offset < _RC4_FIRST_SEGMENT_SIZE:
            block_size = min(to_process, _RC4_FIRST_SEGMENT_SIZE - offset)
            self._decrypt_first_segment(memoryview(buffer)[:block_size], offset)
            if mark_processed(block_size):
                return

        if offset % _RC4_SEGMENT_SIZE != 0:
            block_size = min(to_process, _RC4_SEGMENT_SIZE - offset % _RC4_SEGMENT_SIZE)
            self._decrypt_segment(
                memoryview(buffer)[processed : processed + block_size],
                offset,
            )
            if mark_processed(block_size):
                return

        while to_process > _RC4_SEGMENT_SIZE:
            self._decrypt_segment(
                memoryview(buffer)[processed : processed + _RC4_SEGMENT_SIZE],
                offset,
            )
            mark_processed(_RC4_SEGMENT_SIZE)

        if to_process > 0:
            self._decrypt_segment(memoryview(buffer)[processed:], offset)


def new_qmc_cipher(key: bytes) -> _MapCipher | _Rc4Cipher:
    if len(key) > 300:
        return _Rc4Cipher(key)
    if key:
        return _MapCipher(key)
    raise ValueError("QMC key cannot be empty")


def decrypt_qmc_bytes(data: bytes, raw_key: bytes | str, offset: int = 0) -> bytes:
    cipher = new_qmc_cipher(derive_qmc_key(raw_key))
    buffer = bytearray(data)
    cipher.decrypt(buffer, offset)
    return bytes(buffer)


def decrypt_mflac_file(source_path: Path, target_path: Path, ekey: str, chunk_size: int = 65536) -> Path:
    raw_key = extract_qmc_raw_key_from_ekey(ekey)
    cipher = new_qmc_cipher(derive_qmc_key(raw_key))
    offset = 0

    with source_path.open("rb") as source, target_path.open("wb") as target:
        while chunk := source.read(chunk_size):
            buffer = bytearray(chunk)
            cipher.decrypt(buffer, offset)
            target.write(buffer)
            offset += len(buffer)
    return target_path
