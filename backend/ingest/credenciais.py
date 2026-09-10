"""Credenciais cifradas com uma chave derivada do SECRET_KEY da instalação."""
import base64
import hashlib
from cryptography.fernet import Fernet
from django.conf import settings


def cifra():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()))


def cifrar(senha):
    return cifra().encrypt(senha.encode()).decode()


def decifrar(valor):
    return cifra().decrypt(valor.encode()).decode()
