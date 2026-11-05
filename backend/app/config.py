from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    redis_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    max_unknowns: int = 5000
    max_json_unknowns: int = 1000
    max_task_seconds: int = 120
    max_active_tasks_per_user: int = 3
    max_queue_size: int = 20

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
