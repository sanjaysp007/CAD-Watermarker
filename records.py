"""Atomic local registration. Geometry and expected ciphertext are encrypted at rest."""

import io
import sqlite3
import uuid
from contextlib import closing

import numpy as np

from crypto import keys, seal, unseal


def connect(path):
    db = sqlite3.connect(path, timeout=15)
    db.execute(
        "CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, salt BLOB, data BLOB)"
    )
    return db


def save(path, salt, key, record):
    uid = uuid.uuid4().hex
    buf = io.BytesIO()
    np.savez_compressed(buf, **record)
    encrypted = seal(key, buf.getvalue(), uid.encode())
    with closing(connect(path)) as db, db:
        db.execute("INSERT INTO records VALUES (?,?,?)", (uid, salt, encrypted))
    return uid


def load(path, uid, password):
    with closing(connect(path)) as db:
        row = db.execute("SELECT salt,data FROM records WHERE id=?", (uid,)).fetchone()
    if row is None:
        raise ValueError("Unknown record.")
    keyset = keys(password, row[0])
    with np.load(
        io.BytesIO(unseal(keyset[2], row[1], uid.encode())), allow_pickle=False
    ) as data:
        return keyset, dict(data)
