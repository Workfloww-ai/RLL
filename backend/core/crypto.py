import base64
import os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend

def encrypt_payload(data: str, key_hex: str) -> str:
    if not key_hex or len(key_hex) != 64:
        raise ValueError("Encryption key must be a 64-character hex string (32 bytes).")
    key = bytes.fromhex(key_hex)
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded_data = padder.update(data.encode('utf-8')) + padder.finalize()
    
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()
    return base64.b64encode(iv + ciphertext).decode('utf-8')

def decrypt_payload(encrypted_b64: str, key_hex: str) -> str:
    if not key_hex or len(key_hex) != 64:
        raise ValueError("Encryption key must be a 64-character hex string (32 bytes).")
    key = bytes.fromhex(key_hex)
    encrypted_data = base64.b64decode(encrypted_b64)
    
    iv = encrypted_data[:16]
    ciphertext = encrypted_data[16:]
    
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    
    padded_data = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    data = unpadder.update(padded_data) + unpadder.finalize()
    
    return data.decode('utf-8')
