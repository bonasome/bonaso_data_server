from .settings import *
import dj_database_url
import os
from dotenv import load_dotenv
import pathlib

# Load your .env first
env_path = pathlib.Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

DATABASES = {
    "default": dj_database_url.parse(
        os.environ["TEST_DATABASE_URL"],
        conn_max_age=600,
        ssl_require = False
    )
}

TEST_SETUP = True

