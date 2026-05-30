from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-pro"
    deepseek_base_url: str = "https://api.deepseek.com"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Optional API key guarding the write/expensive endpoints (/api/custom,
    # /api/ai). When empty (the default) auth is disabled so local/demo runs
    # and the existing test-suite keep working unchanged; set API_KEY in the
    # environment to require an `X-API-Key` header on those routers.
    api_key: str = ""

    @property
    def llm_available(self) -> bool:
        return bool(self.deepseek_api_key)

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    class Config:
        env_file = ".env"


settings = Settings()
