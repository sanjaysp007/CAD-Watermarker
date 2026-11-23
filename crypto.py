"""Authenticated payload framing and password-based key separation."""

import hashlib
import hmac
import struct
import zlib

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes


def keys(password, salt):
    if not password:
        raise ValueError("Enter a password.")
    root = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return tuple(
        hmac.digest(root, label, "sha256")
        for label in (b"payload-v1", b"locations-v1", b"record-v1")
    )


def seal(key, data, context):
    nonce = get_random_bytes(12)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    cipher.update(context)
    body, tag = cipher.encrypt_and_digest(data)
    return nonce + tag + body


def unseal(key, packet, context):
    cipher = AES.new(key, AES.MODE_GCM, nonce=packet[:12])
    cipher.update(context)
    return cipher.decrypt_and_verify(packet[28:], packet[12:28])


def pack(key, data):
    header = struct.pack(">4sII", b"CWM1", len(data), zlib.crc32(data))
    return seal(key, header + data, b"frame-v1")


def unpack(key, packet):
    data = unseal(key, packet, b"frame-v1")
    sync, size, crc = struct.unpack(">4sII", data[:12])
    payload = data[12:]
    if (sync, size, crc) != (b"CWM1", len(payload), zlib.crc32(payload)):
        raise ValueError("Invalid watermark frame.")
    return payload
