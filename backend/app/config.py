from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-pro"
    deepseek_base_url: str = "https://api.deepseek.com"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    rate_limit_enabled: bool = True
    # Optional shared-secret auth. Empty string = auth disabled (single-tenant
    # default, backward-compatible). Set APP_API_TOKEN to require the
    # X-API-Token header on every /api route.
    app_api_token: str = ""
    # Synthetic-book calibration targets: the per-strategy approval rate the
    # model-score cutoff is calibrated to hit on the reference population.
    # This is a DEMO-BOOK tuning input (not a production metric override);
    # override via env PD_TARGET_APPROVAL_RATES as a JSON object if desired.
    pd_target_approval_rates: dict[str, float] = {
        "v2.2": 0.23, "v2.3": 0.44, "v2.4-Beta": 0.66, "v2.5-RC": 0.49,
    }

    @property
    def llm_available(self) -> bool:
        return bool(self.deepseek_api_key)

    @property
    def auth_enabled(self) -> bool:
        return bool(self.app_api_token)

    @property
    def cors_list(self) -> list[str]:
        # Drop blanks so a trailing comma or empty value can't become a bogus
        # "" origin that CORSMiddleware would treat as a real allowed entry.
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
