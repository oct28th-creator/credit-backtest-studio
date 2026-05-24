from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-pro"
    deepseek_base_url: str = "https://api.deepseek.com"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def llm_available(self) -> bool:
        return bool(self.deepseek_api_key)

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    class Config:
        env_file = ".env"


settings = Settings()
