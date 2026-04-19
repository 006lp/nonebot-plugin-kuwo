use std::fs::File;
use std::io::{BufReader, BufWriter, Read, Write};
use std::path::Path;

use base64::{engine::general_purpose::STANDARD, Engine as _};
use pyo3::exceptions::{PyOSError, PyValueError};
use pyo3::PyErr;

const KUWO_SECRET_KEY: &[u8; 8] = b"ylzsxkwm";
const QMC_RAW_KEY_LENGTHS: [usize; 2] = [704, 364];
const QMC_V2_KEY_PREFIX: &[u8] = b"QQMusic EncV2,Key:";
const RC4_FIRST_SEGMENT_SIZE: usize = 128;
const RC4_SEGMENT_SIZE: usize = 5120;

const ARRAY_E: [i8; 64] = [
    31, 0, 1, 2, 3, 4, -1, -1, 3, 4, 5, 6, 7, 8, -1, -1, 7, 8, 9, 10, 11, 12, -1, -1, 11, 12, 13,
    14, 15, 16, -1, -1, 15, 16, 17, 18, 19, 20, -1, -1, 19, 20, 21, 22, 23, 24, -1, -1, 23, 24, 25,
    26, 27, 28, -1, -1, 27, 28, 29, 30, 31, 30, -1, -1,
];
const ARRAY_IP: [i8; 64] = [
    57, 49, 41, 33, 25, 17, 9, 1, 59, 51, 43, 35, 27, 19, 11, 3, 61, 53, 45, 37, 29, 21, 13, 5, 63,
    55, 47, 39, 31, 23, 15, 7, 56, 48, 40, 32, 24, 16, 8, 0, 58, 50, 42, 34, 26, 18, 10, 2, 60, 52,
    44, 36, 28, 20, 12, 4, 62, 54, 46, 38, 30, 22, 14, 6,
];
const ARRAY_IP_1: [i8; 64] = [
    39, 7, 47, 15, 55, 23, 63, 31, 38, 6, 46, 14, 54, 22, 62, 30, 37, 5, 45, 13, 53, 21, 61, 29,
    36, 4, 44, 12, 52, 20, 60, 28, 35, 3, 43, 11, 51, 19, 59, 27, 34, 2, 42, 10, 50, 18, 58, 26,
    33, 1, 41, 9, 49, 17, 57, 25, 32, 0, 40, 8, 48, 16, 56, 24,
];
const ARRAY_LS: [usize; 16] = [1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1];
const ARRAY_LS_MASK: [u64; 3] = [0, 0x100001, 0x300003];
const ARRAY_P: [i8; 32] = [
    15, 6, 19, 20, 28, 11, 27, 16, 0, 14, 22, 25, 4, 17, 30, 9, 1, 7, 23, 13, 31, 26, 2, 8, 18, 12,
    29, 5, 21, 10, 3, 24,
];
const ARRAY_PC_1: [i8; 56] = [
    56, 48, 40, 32, 24, 16, 8, 0, 57, 49, 41, 33, 25, 17, 9, 1, 58, 50, 42, 34, 26, 18, 10, 2, 59,
    51, 43, 35, 62, 54, 46, 38, 30, 22, 14, 6, 61, 53, 45, 37, 29, 21, 13, 5, 60, 52, 44, 36, 28,
    20, 12, 4, 27, 19, 11, 3,
];
const ARRAY_PC_2: [i8; 64] = [
    13, 16, 10, 23, 0, 4, -1, -1, 2, 27, 14, 5, 20, 9, -1, -1, 22, 18, 11, 3, 25, 7, -1, -1, 15, 6,
    26, 19, 12, 1, -1, -1, 40, 51, 30, 36, 46, 54, -1, -1, 29, 39, 50, 44, 32, 47, -1, -1, 43, 48,
    38, 55, 33, 52, -1, -1, 45, 41, 49, 35, 28, 31, -1, -1,
];
const MATRIX_NS_BOX: [[u8; 64]; 8] = [
    [
        14, 4, 3, 15, 2, 13, 5, 3, 13, 14, 6, 9, 11, 2, 0, 5, 4, 1, 10, 12, 15, 6, 9, 10, 1, 8, 12,
        7, 8, 11, 7, 0, 0, 15, 10, 5, 14, 4, 9, 10, 7, 8, 12, 3, 13, 1, 3, 6, 15, 12, 6, 11, 2, 9,
        5, 0, 4, 2, 11, 14, 1, 7, 8, 13,
    ],
    [
        15, 0, 9, 5, 6, 10, 12, 9, 8, 7, 2, 12, 3, 13, 5, 2, 1, 14, 7, 8, 11, 4, 0, 3, 14, 11, 13,
        6, 4, 1, 10, 15, 3, 13, 12, 11, 15, 3, 6, 0, 4, 10, 1, 7, 8, 4, 11, 14, 13, 8, 0, 6, 2, 15,
        9, 5, 7, 1, 10, 12, 14, 2, 5, 9,
    ],
    [
        10, 13, 1, 11, 6, 8, 11, 5, 9, 4, 12, 2, 15, 3, 2, 14, 0, 6, 13, 1, 3, 15, 4, 10, 14, 9, 7,
        12, 5, 0, 8, 7, 13, 1, 2, 4, 3, 6, 12, 11, 0, 13, 5, 14, 6, 8, 15, 2, 7, 10, 8, 15, 4, 9,
        11, 5, 9, 0, 14, 3, 10, 7, 1, 12,
    ],
    [
        7, 10, 1, 15, 0, 12, 11, 5, 14, 9, 8, 3, 9, 7, 4, 8, 13, 6, 2, 1, 6, 11, 12, 2, 3, 0, 5,
        14, 10, 13, 15, 4, 13, 3, 4, 9, 6, 10, 1, 12, 11, 0, 2, 5, 0, 13, 14, 2, 8, 15, 7, 4, 15,
        1, 10, 7, 5, 6, 12, 11, 3, 8, 9, 14,
    ],
    [
        2, 4, 8, 15, 7, 10, 13, 6, 4, 1, 3, 12, 11, 7, 14, 0, 12, 2, 5, 9, 10, 13, 0, 3, 1, 11, 15,
        5, 6, 8, 9, 14, 14, 11, 5, 6, 4, 1, 3, 10, 2, 12, 15, 0, 13, 2, 8, 5, 11, 8, 0, 15, 7, 14,
        9, 4, 12, 7, 10, 9, 1, 13, 6, 3,
    ],
    [
        12, 9, 0, 7, 9, 2, 14, 1, 10, 15, 3, 4, 6, 12, 5, 11, 1, 14, 13, 0, 2, 8, 7, 13, 15, 5, 4,
        10, 8, 3, 11, 6, 10, 4, 6, 11, 7, 9, 0, 6, 4, 2, 13, 1, 9, 15, 3, 8, 15, 3, 1, 14, 12, 5,
        11, 0, 2, 12, 14, 7, 5, 10, 8, 13,
    ],
    [
        4, 1, 3, 10, 15, 12, 5, 0, 2, 11, 9, 6, 8, 7, 6, 9, 11, 4, 12, 15, 0, 3, 10, 5, 14, 13, 7,
        8, 13, 14, 1, 2, 13, 6, 14, 9, 4, 1, 2, 14, 11, 13, 5, 0, 1, 10, 8, 3, 0, 11, 3, 5, 9, 4,
        15, 2, 7, 8, 12, 15, 10, 7, 6, 12,
    ],
    [
        13, 7, 10, 0, 6, 9, 5, 15, 8, 4, 3, 10, 11, 14, 12, 5, 2, 11, 9, 6, 15, 12, 0, 3, 4, 1, 14,
        13, 1, 2, 7, 8, 1, 2, 12, 15, 10, 4, 0, 3, 13, 14, 6, 9, 7, 8, 9, 6, 15, 1, 5, 12, 3, 10,
        14, 5, 8, 7, 11, 0, 4, 13, 2, 11,
    ],
];
const QMC_V2_DERIVE_KEY_1: [u8; 16] = [
    0x33, 0x38, 0x36, 0x5A, 0x4A, 0x59, 0x21, 0x40, 0x23, 0x2A, 0x24, 0x25, 0x5E, 0x26, 0x29, 0x28,
];
const QMC_V2_DERIVE_KEY_2: [u8; 16] = [
    0x2A, 0x2A, 0x23, 0x21, 0x28, 0x23, 0x24, 0x25, 0x26, 0x5E, 0x61, 0x31, 0x63, 0x5A, 0x2C, 0x54,
];

#[derive(Debug)]
pub enum QmcError {
    Value(String),
    Io(std::io::Error),
}

impl std::fmt::Display for QmcError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Value(message) => f.write_str(message),
            Self::Io(error) => write!(f, "{error}"),
        }
    }
}

impl std::error::Error for QmcError {}

impl From<std::io::Error> for QmcError {
    fn from(value: std::io::Error) -> Self {
        Self::Io(value)
    }
}

impl From<base64::DecodeError> for QmcError {
    fn from(value: base64::DecodeError) -> Self {
        Self::Value(value.to_string())
    }
}

impl From<std::string::FromUtf8Error> for QmcError {
    fn from(value: std::string::FromUtf8Error) -> Self {
        Self::Value(value.to_string())
    }
}

impl From<QmcError> for PyErr {
    fn from(value: QmcError) -> Self {
        match value {
            QmcError::Value(message) => PyValueError::new_err(message),
            QmcError::Io(error) => PyOSError::new_err(error.to_string()),
        }
    }
}

fn bit_transform(arr: &[i8], n: usize, value: u64) -> u64 {
    let mut transformed = 0u64;
    for (index, bit_index) in arr.iter().take(n).enumerate() {
        if *bit_index >= 0 && value & (1u64 << (*bit_index as u32)) != 0 {
            transformed |= 1u64 << index;
        }
    }
    transformed
}

fn des64(longs: &[u64; 16], value: u64) -> u64 {
    let output = bit_transform(&ARRAY_IP, 64, value);
    let mut source = [output & 0xFFFF_FFFF, output >> 32];
    let mut partial = [0u8; 8];

    for round_key in longs {
        let mut right = bit_transform(&ARRAY_E, 64, source[1]) ^ *round_key;
        for (index, item) in partial.iter_mut().enumerate() {
            *item = ((right >> (index * 8)) & 0xFF) as u8;
        }

        let mut s_out = 0u64;
        for box_index in (0..8).rev() {
            s_out <<= 4;
            s_out |= MATRIX_NS_BOX[box_index][partial[box_index] as usize] as u64;
        }
        right = bit_transform(&ARRAY_P, 32, s_out);
        let left = source[0];
        source[0] = source[1];
        source[1] = left ^ right;
    }

    source.swap(0, 1);
    let merged = ((source[1] << 32) & 0xFFFF_FFFF_0000_0000) | (source[0] & 0xFFFF_FFFF);
    bit_transform(&ARRAY_IP_1, 64, merged)
}

fn sub_keys(value: u64, mode: u8) -> [u64; 16] {
    let mut key_schedule = [0u64; 16];
    let mut transformed = bit_transform(&ARRAY_PC_1, 56, value);

    for (index, item) in key_schedule.iter_mut().enumerate() {
        let shift = ARRAY_LS[index];
        let mask = ARRAY_LS_MASK[shift];
        transformed = ((transformed & mask) << (28 - shift)) | ((transformed & !mask) >> shift);
        *item = bit_transform(&ARRAY_PC_2, 64, transformed);
    }

    if mode == 1 {
        key_schedule.reverse();
    }
    key_schedule
}

fn kuwo_crypto(message: &[u8], mode: u8, key: &[u8; 8]) -> Result<Vec<u8>, QmcError> {
    let mut input = message.to_vec();
    match mode {
        0 => {
            let padding = (8 - input.len() % 8) % 8;
            if padding > 0 {
                input.resize(input.len() + padding, 0);
            }
        }
        1 => {
            if input.len() % 8 != 0 {
                return Err(QmcError::Value(
                    "Invalid message length: msg must be a multiple of 8 in decrypt mode."
                        .to_string(),
                ));
            }
        }
        _ => {
            return Err(QmcError::Value(format!(
                "Invalid mode: {mode}. Mode must be 0 (encrypt) or 1 (decrypt)."
            )));
        }
    }

    let mut key_block = 0u64;
    for (index, item) in key.iter().enumerate() {
        key_block |= (*item as u64) << (index * 8);
    }
    let schedule = sub_keys(key_block, mode);

    let mut result = Vec::with_capacity(input.len());
    for chunk in input.chunks_exact(8) {
        let mut block = 0u64;
        for (index, item) in chunk.iter().enumerate() {
            block |= (*item as u64) << (index * 8);
        }
        let encrypted = des64(&schedule, block);
        for index in 0..8 {
            result.push(((encrypted >> (index * 8)) & 0xFF) as u8);
        }
    }
    Ok(result)
}

pub fn kuwo_base64_decrypt(value: &str) -> Result<String, QmcError> {
    let decoded = STANDARD.decode(value)?;
    let result = kuwo_crypto(&decoded, 1, KUWO_SECRET_KEY)?;
    let trimmed_len = result
        .iter()
        .rposition(|item| *item != 0)
        .map(|index| index + 1)
        .unwrap_or(0);
    String::from_utf8(result[..trimmed_len].to_vec()).map_err(Into::into)
}

pub fn extract_qmc_raw_key_from_ekey(ekey: &str) -> Result<Vec<u8>, QmcError> {
    let decrypted = kuwo_base64_decrypt(ekey)?;
    for key_length in QMC_RAW_KEY_LENGTHS {
        if decrypted.len() < key_length {
            continue;
        }
        let candidate = &decrypted[decrypted.len() - key_length..];
        if STANDARD.decode(candidate).is_ok() {
            return Ok(candidate.as_bytes().to_vec());
        }
    }
    Err(QmcError::Value(
        "Cannot extract QMC raw key from kuwo ekey.".to_string(),
    ))
}

fn simple_make_key(salt: usize, length: usize) -> Vec<u8> {
    let mut key = vec![0u8; length];
    for (index, item) in key.iter_mut().enumerate() {
        *item = ((f64::tan(salt as f64 + index as f64 * 0.1).abs() * 100.0) as u64 & 0xFF) as u8;
    }
    key
}

fn tea_decrypt_block(block: &[u8], key: &[u8]) -> Result<[u8; 8], QmcError> {
    let mut v0 = u32::from_be_bytes(
        block[0..4]
            .try_into()
            .map_err(|_| QmcError::Value("invalid tea block".to_string()))?,
    );
    let mut v1 = u32::from_be_bytes(
        block[4..8]
            .try_into()
            .map_err(|_| QmcError::Value("invalid tea block".to_string()))?,
    );
    let k0 = u32::from_be_bytes(
        key[0..4]
            .try_into()
            .map_err(|_| QmcError::Value("invalid tea key".to_string()))?,
    );
    let k1 = u32::from_be_bytes(
        key[4..8]
            .try_into()
            .map_err(|_| QmcError::Value("invalid tea key".to_string()))?,
    );
    let k2 = u32::from_be_bytes(
        key[8..12]
            .try_into()
            .map_err(|_| QmcError::Value("invalid tea key".to_string()))?,
    );
    let k3 = u32::from_be_bytes(
        key[12..16]
            .try_into()
            .map_err(|_| QmcError::Value("invalid tea key".to_string()))?,
    );

    let delta = 0x9E37_79B9u32;
    let mut sum_value = delta.wrapping_mul(16);
    for _ in 0..16 {
        v1 = v1.wrapping_sub(
            ((v0 << 4).wrapping_add(k2))
                ^ (v0.wrapping_add(sum_value))
                ^ ((v0 >> 5).wrapping_add(k3)),
        );
        v0 = v0.wrapping_sub(
            ((v1 << 4).wrapping_add(k0))
                ^ (v1.wrapping_add(sum_value))
                ^ ((v1 >> 5).wrapping_add(k1)),
        );
        sum_value = sum_value.wrapping_sub(delta);
    }

    let mut output = [0u8; 8];
    output[0..4].copy_from_slice(&v0.to_be_bytes());
    output[4..8].copy_from_slice(&v1.to_be_bytes());
    Ok(output)
}

fn xor_8_bytes(left: &[u8; 8], right: &[u8; 8]) -> [u8; 8] {
    let mut output = [0u8; 8];
    for index in 0..8 {
        output[index] = left[index] ^ right[index];
    }
    output
}

fn decrypt_tencent_tea(input_buffer: &[u8], key: &[u8]) -> Result<Vec<u8>, QmcError> {
    const SALT_LEN: usize = 2;
    const ZERO_LEN: usize = 7;

    if input_buffer.len() % 8 != 0 {
        return Err(QmcError::Value(
            "inBuf size not a multiple of the block size".to_string(),
        ));
    }
    if input_buffer.len() < 16 {
        return Err(QmcError::Value("inBuf size too small".to_string()));
    }

    let mut decrypted_block = tea_decrypt_block(&input_buffer[..8], key)?;
    let pad_len = (decrypted_block[0] & 0x7) as usize;
    let output_len = input_buffer.len() - 1 - pad_len - SALT_LEN - ZERO_LEN;
    let mut output = vec![0u8; output_len];

    let mut iv_prev = [0u8; 8];
    let mut iv_cur: [u8; 8] = input_buffer[..8]
        .try_into()
        .map_err(|_| QmcError::Value("invalid tea input".to_string()))?;
    let mut input_pos = 8usize;
    let mut dest_idx = 1 + pad_len;

    let decrypt_next_block = |decrypted_block: &mut [u8; 8],
                              iv_prev: &mut [u8; 8],
                              iv_cur: &mut [u8; 8],
                              input_pos: &mut usize,
                              dest_idx: &mut usize|
     -> Result<(), QmcError> {
        *iv_prev = *iv_cur;
        let next_block: [u8; 8] = input_buffer
            .get(*input_pos..*input_pos + 8)
            .ok_or_else(|| QmcError::Value("unexpected end of tea buffer".to_string()))?
            .try_into()
            .map_err(|_| QmcError::Value("invalid tea buffer block".to_string()))?;
        *iv_cur = next_block;
        let xored = xor_8_bytes(decrypted_block, iv_cur);
        *decrypted_block = tea_decrypt_block(&xored, key)?;
        *input_pos += 8;
        *dest_idx = 0;
        Ok(())
    };

    let mut salt_index = 1usize;
    while salt_index <= SALT_LEN {
        if dest_idx < 8 {
            dest_idx += 1;
            salt_index += 1;
        } else {
            decrypt_next_block(
                &mut decrypted_block,
                &mut iv_prev,
                &mut iv_cur,
                &mut input_pos,
                &mut dest_idx,
            )?;
        }
    }

    let mut output_pos = 0usize;
    while output_pos < output_len {
        if dest_idx < 8 {
            output[output_pos] = decrypted_block[dest_idx] ^ iv_prev[dest_idx];
            dest_idx += 1;
            output_pos += 1;
        } else {
            decrypt_next_block(
                &mut decrypted_block,
                &mut iv_prev,
                &mut iv_cur,
                &mut input_pos,
                &mut dest_idx,
            )?;
        }
    }

    let mut zero_index = 1usize;
    while zero_index <= ZERO_LEN {
        if dest_idx < 8 {
            if decrypted_block[dest_idx] != iv_prev[dest_idx] {
                return Err(QmcError::Value("zero check failed".to_string()));
            }
            dest_idx += 1;
            zero_index += 1;
        } else {
            decrypt_next_block(
                &mut decrypted_block,
                &mut iv_prev,
                &mut iv_cur,
                &mut input_pos,
                &mut dest_idx,
            )?;
        }
    }

    Ok(output)
}

fn derive_key_v1(raw_key_decoded: &[u8]) -> Result<Vec<u8>, QmcError> {
    if raw_key_decoded.len() < 16 {
        return Err(QmcError::Value("key length is too short".to_string()));
    }

    let simple_key = simple_make_key(106, 8);
    let mut tea_key = vec![0u8; 16];
    for index in 0..8 {
        tea_key[index << 1] = simple_key[index];
        tea_key[(index << 1) + 1] = raw_key_decoded[index];
    }

    let decrypted = decrypt_tencent_tea(&raw_key_decoded[8..], &tea_key)?;
    let mut output = raw_key_decoded[..8].to_vec();
    output.extend_from_slice(&decrypted);
    Ok(output)
}

fn derive_key_v2(raw_key: &[u8]) -> Result<Vec<u8>, QmcError> {
    let buffer = decrypt_tencent_tea(raw_key, &QMC_V2_DERIVE_KEY_1)?;
    let buffer = decrypt_tencent_tea(&buffer, &QMC_V2_DERIVE_KEY_2)?;
    STANDARD.decode(buffer).map_err(Into::into)
}

pub fn derive_qmc_key(raw_key: &[u8]) -> Result<Vec<u8>, QmcError> {
    let mut decoded = STANDARD.decode(raw_key)?;
    if decoded.starts_with(QMC_V2_KEY_PREFIX) {
        decoded = derive_key_v2(&decoded[QMC_V2_KEY_PREFIX.len()..])?;
    }
    derive_key_v1(&decoded)
}

struct MapCipher {
    key: Vec<u8>,
    size: usize,
}

impl MapCipher {
    fn new(key: Vec<u8>) -> Result<Self, QmcError> {
        if key.is_empty() {
            return Err(QmcError::Value(
                "qmc map cipher key cannot be empty".to_string(),
            ));
        }
        let size = key.len();
        Ok(Self { key, size })
    }

    fn rotate(value: u8, bits: u8) -> u8 {
        let rotate = (bits + 4) % 8;
        value.wrapping_shl(rotate as u32) | value.wrapping_shr(rotate as u32)
    }

    fn get_mask(&self, offset: usize) -> u8 {
        let normalized_offset = if offset > 0x7FFF {
            offset % 0x7FFF
        } else {
            offset
        };
        let index = (((normalized_offset as u128 * normalized_offset as u128) + 71_214)
            % self.size as u128) as usize;
        Self::rotate(self.key[index], (index & 0x7) as u8)
    }

    fn decrypt(&self, buffer: &mut [u8], offset: usize) {
        for (index, item) in buffer.iter_mut().enumerate() {
            *item ^= self.get_mask(offset + index);
        }
    }
}

struct Rc4Cipher {
    key: Vec<u8>,
    size: usize,
    box_state: Vec<u8>,
    hash: u32,
}

impl Rc4Cipher {
    fn new(key: Vec<u8>) -> Result<Self, QmcError> {
        if key.is_empty() {
            return Err(QmcError::Value(
                "qmc rc4 cipher key cannot be empty".to_string(),
            ));
        }

        let size = key.len();
        let mut box_state = (0..size)
            .map(|index| (index & 0xFF) as u8)
            .collect::<Vec<_>>();
        let mut j = 0usize;
        for index in 0..size {
            j = (j + box_state[index] as usize + key[index % size] as usize) % size;
            box_state.swap(index, j);
        }

        let hash = Self::get_hash_base(&key);
        Ok(Self {
            key,
            size,
            box_state,
            hash,
        })
    }

    fn get_hash_base(key: &[u8]) -> u32 {
        let mut result = 1u32;
        for value in key {
            if *value == 0 {
                continue;
            }
            let next_hash = result.wrapping_mul(*value as u32);
            if next_hash == 0 || next_hash <= result {
                break;
            }
            result = next_hash;
        }
        result
    }

    fn get_segment_skip(&self, segment_id: usize) -> usize {
        let seed = self.key[segment_id % self.size] as usize;
        if seed == 0 {
            return 0;
        }
        let index = ((self.hash as f64 / ((segment_id + 1) * seed) as f64) * 100.0) as usize;
        index % self.size
    }

    fn decrypt_first_segment(&self, buffer: &mut [u8], offset: usize) {
        for (index, item) in buffer.iter_mut().enumerate() {
            *item ^= self.key[self.get_segment_skip(offset + index)];
        }
    }

    fn decrypt_segment(&self, buffer: &mut [u8], offset: usize) {
        let mut box_state = self.box_state.clone();
        let mut j = 0usize;
        let mut k = 0usize;
        let skip_length =
            (offset % RC4_SEGMENT_SIZE) + self.get_segment_skip(offset / RC4_SEGMENT_SIZE);

        for index in 0..(skip_length + buffer.len()) {
            j = (j + 1) % self.size;
            k = (box_state[j] as usize + k) % self.size;
            box_state.swap(j, k);
            if index >= skip_length {
                let output_index = index - skip_length;
                let xor_index = (box_state[j] as usize + box_state[k] as usize) % self.size;
                buffer[output_index] ^= box_state[xor_index];
            }
        }
    }

    fn decrypt(&self, buffer: &mut [u8], mut offset: usize) {
        let mut to_process = buffer.len();
        let mut processed = 0usize;

        if offset < RC4_FIRST_SEGMENT_SIZE {
            let block_size = to_process.min(RC4_FIRST_SEGMENT_SIZE - offset);
            self.decrypt_first_segment(&mut buffer[..block_size], offset);
            offset += block_size;
            to_process -= block_size;
            processed += block_size;
            if to_process == 0 {
                return;
            }
        }

        if offset % RC4_SEGMENT_SIZE != 0 {
            let block_size = to_process.min(RC4_SEGMENT_SIZE - offset % RC4_SEGMENT_SIZE);
            self.decrypt_segment(&mut buffer[processed..processed + block_size], offset);
            offset += block_size;
            to_process -= block_size;
            processed += block_size;
            if to_process == 0 {
                return;
            }
        }

        while to_process > RC4_SEGMENT_SIZE {
            self.decrypt_segment(&mut buffer[processed..processed + RC4_SEGMENT_SIZE], offset);
            offset += RC4_SEGMENT_SIZE;
            to_process -= RC4_SEGMENT_SIZE;
            processed += RC4_SEGMENT_SIZE;
        }

        if to_process > 0 {
            self.decrypt_segment(&mut buffer[processed..], offset);
        }
    }
}

enum QmcCipher {
    Map(MapCipher),
    Rc4(Rc4Cipher),
}

impl QmcCipher {
    fn decrypt(&self, buffer: &mut [u8], offset: usize) {
        match self {
            Self::Map(cipher) => cipher.decrypt(buffer, offset),
            Self::Rc4(cipher) => cipher.decrypt(buffer, offset),
        }
    }
}

fn new_qmc_cipher(key: Vec<u8>) -> Result<QmcCipher, QmcError> {
    if key.len() > 300 {
        return Ok(QmcCipher::Rc4(Rc4Cipher::new(key)?));
    }
    if !key.is_empty() {
        return Ok(QmcCipher::Map(MapCipher::new(key)?));
    }
    Err(QmcError::Value("QMC key cannot be empty".to_string()))
}

pub fn decrypt_qmc_bytes(data: &[u8], raw_key: &[u8], offset: usize) -> Result<Vec<u8>, QmcError> {
    let cipher = new_qmc_cipher(derive_qmc_key(raw_key)?)?;
    let mut buffer = data.to_vec();
    cipher.decrypt(&mut buffer, offset);
    Ok(buffer)
}

pub fn decrypt_mflac_file(
    source_path: &str,
    target_path: &str,
    ekey: &str,
    chunk_size: usize,
) -> Result<(), QmcError> {
    let raw_key = extract_qmc_raw_key_from_ekey(ekey)?;
    let cipher = new_qmc_cipher(derive_qmc_key(&raw_key)?)?;

    let mut reader = BufReader::new(File::open(Path::new(source_path))?);
    let mut writer = BufWriter::new(File::create(Path::new(target_path))?);
    let mut offset = 0usize;
    let mut buffer = vec![0u8; chunk_size];

    loop {
        let read_size = reader.read(&mut buffer)?;
        if read_size == 0 {
            break;
        }
        let chunk = &mut buffer[..read_size];
        cipher.decrypt(chunk, offset);
        writer.write_all(chunk)?;
        offset += read_size;
    }

    writer.flush()?;
    Ok(())
}
