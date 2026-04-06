from app.core.encryption import encrypt_data, decrypt_data


def test_encryption():

    original = "John Doe"
    encrypted = encrypt_data(original)
    decrypted = decrypt_data(encrypted)

    assert decrypted == original