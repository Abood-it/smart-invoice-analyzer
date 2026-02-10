import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = "secret-key"
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(
        BASE_DIR, "database", "db.sqlite"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False