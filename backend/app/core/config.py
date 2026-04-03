import os
from dotenv import load_dotenv

load_dotenv()

class config:
    SUPABASE_URL: str = os.getenv("SUPABASE_URL")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY")
    DB_SCHEMA: str = os.getenv("DB_SCHEMA", "sdoc")

config = config()