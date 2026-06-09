# SPDX-License-Identifier: Apache-2.0
# src/fine_tuning_os/crypto.py
"""AES-256-GCM encryption for deliverables.

Output layout: nonce (12 bytes) || ciphertext+tag. The key is generated
fresh per deliverable and surfaced to the operator exactly once; it is never
persisted to disk by this module.
"""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_BYTES = 12
_KEY_BYTES = 32
_TAG_BYTES = 16  # AES-GCM authentication tag appended to the ciphertext


def generate_key() -> bytes:
    return AESGCM.generate_key(bit_length=256)


def encrypt_file(src: Path, dst: Path, key: bytes) -> Path:
    if len(key) != _KEY_BYTES:
        raise ValueError("key must be 32 bytes for AES-256-GCM")
    plaintext = Path(src).read_bytes()
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(nonce + ciphertext)
    return dst


def decrypt_file(src: Path, dst: Path, key: bytes) -> Path:
    if len(key) != _KEY_BYTES:
        raise ValueError("key must be 32 bytes for AES-256-GCM")
    blob = Path(src).read_bytes()
    if len(blob) < _NONCE_BYTES + _TAG_BYTES:
        raise ValueError("ciphertext too short to contain nonce + GCM tag")
    nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(plaintext)
    return dst
