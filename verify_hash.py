from werkzeug.security import check_password_hash

hash_val = "pbkdf2:sha256:1000000$RqdtZHLepONrATyS$6aba0e5cbf2cf8e242bb7cb37faf29f86da49564a4018c44509b448b63c26ef4"
password = "admin"

is_valid = check_password_hash(hash_val, password)
print(f"Is valid: {is_valid}")
