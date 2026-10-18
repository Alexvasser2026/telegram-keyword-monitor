"""Generate the Fernet key used to encrypt the checkpoint committed to GitHub."""
from cryptography.fernet import Fernet

print(Fernet.generate_key().decode("ascii"))
