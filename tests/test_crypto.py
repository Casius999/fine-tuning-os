# tests/test_crypto.py
import pytest
from cryptography.exceptions import InvalidTag

from fine_tuning_os.crypto import decrypt_file, encrypt_file, generate_key


def test_generate_key_is_32_bytes():
    assert len(generate_key()) == 32


def test_encrypt_decrypt_roundtrip(tmp_path):
    src = tmp_path / "model.bin"
    src.write_bytes(b"secret weights \x00\x01\x02")
    key = generate_key()
    enc = encrypt_file(src, tmp_path / "model.enc", key)
    assert enc.read_bytes() != src.read_bytes()
    out = decrypt_file(enc, tmp_path / "model.dec", key)
    assert out.read_bytes() == b"secret weights \x00\x01\x02"


def test_wrong_key_fails(tmp_path):
    src = tmp_path / "f.bin"
    src.write_bytes(b"data")
    enc = encrypt_file(src, tmp_path / "f.enc", generate_key())
    with pytest.raises(InvalidTag):
        decrypt_file(enc, tmp_path / "f.dec", generate_key())


def test_bad_key_length_rejected(tmp_path):
    src = tmp_path / "f.bin"
    src.write_bytes(b"data")
    with pytest.raises(ValueError):
        encrypt_file(src, tmp_path / "f.enc", b"tooshort")
