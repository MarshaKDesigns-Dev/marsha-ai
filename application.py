"""Shared Flask application configured for every entry point."""

import os

from dotenv import load_dotenv
from flask import Flask

from extensions import db


load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY",
    "dev-only-change-me",
)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL",
    "sqlite:///sponsorship.db",
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)
