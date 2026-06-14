"""Bot konfiguratsiyasi - Pydantic Settings asosida."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List
from pathlib import Path
import os


class Settings(BaseSettings):
    """Asosiy sozlamalar. .env dan o'qiydi."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # === Bot ===
    bot_token: str = ""
    bot_username: str = "QuizMasterBot"
    admin_ids: str = ""

    # === API ===
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    api_base_url: str = ""
    webapp_url: str = ""

    # === Database (SQLite - bepul, Render uchun) ===
    database_url: str = "sqlite+aiosqlite:///./data/quiz.db"

    # === Security ===
    jwt_secret: str = "change-me-in-production-use-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24

    # === Files ===
    max_file_size_mb: int = 20
    upload_dir: str = "./uploads"
    allowed_extensions: str = "pdf,doc,docx,xlsx,xls,txt,pptx"

    # === Limits (Free) ===
    free_tests_per_day: int = 5
    free_tests_per_month: int = 20
    max_questions_per_test: int = 50
    max_free_questions: int = 10

    # === Payments ===
    provider_payme: str = ""
    provider_click: str = ""

    # === Monitoring ===
    log_level: str = "INFO"

    # === Premium ===
    premium_monthly_price: int = 49900
    premium_yearly_price: int = 499000
    premium_lifetime_price: int = 999000
    trial_days: int = 3

    # === Computed ===
    @property
    def admin_list(self) -> List[int]:
        return [int(x.strip()) for x in self.admin_ids.split(",") if x.strip()]

    @property
    def allowed_ext_list(self) -> List[str]:
        return [x.strip().lower() for x in self.allowed_extensions.split(",")]

    @property
    def upload_path(self) -> Path:
        path = Path(self.upload_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def is_production(self) -> bool:
        """Render.com da RENDER env variable mavjud."""
        return os.getenv("RENDER") is not None or os.getenv("ENV", "dev") == "production"

    @property
    def effective_webapp_url(self) -> str:
        """WebApp URL - Render URL yoki manual."""
        if self.webapp_url:
            return self.webapp_url
        # Render.com RENDER_EXTERNAL_URL beradi
        render_url = os.getenv("RENDER_EXTERNAL_URL", "")
        if render_url:
            return render_url
        return f"http://localhost:{self.api_port}"

    @property
    def effective_api_url(self) -> str:
        if self.api_base_url:
            return self.api_base_url
        render_url = os.getenv("RENDER_EXTERNAL_URL", "")
        if render_url:
            return render_url
        return f"http://localhost:{self.api_port}"


# Global instance
settings = Settings()
