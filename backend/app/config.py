from pydantic_settings import BaseSettings, SettingsConfigDict


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
        # Drop blanks so a trailing comma or empty value can't become a bogus
        # "" origin that CORSMiddleware would treat as a real allowed entry.
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
