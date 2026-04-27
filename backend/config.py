import os
from pathlib import Path
import yaml
from pydantic import BaseModel


class PolymarketConfig(BaseModel):
    enabled: bool = True


class SmarketsConfig(BaseModel):
    enabled: bool = True


class BetfairConfig(BaseModel):
    enabled: bool = False
    api_key: str = ""
    username: str = ""
    password: str = ""


class OddsApiConfig(BaseModel):
    enabled: bool = False
    api_key: str = ""
    sports: list[str] = []
    poll_interval_seconds: int = 900  # 15 min — preserves free-tier credits


class ExchangesConfig(BaseModel):
    polymarket: PolymarketConfig = PolymarketConfig()
    smarkets: SmarketsConfig = SmarketsConfig()
    betfair: BetfairConfig = BetfairConfig()
    odds_api: OddsApiConfig = OddsApiConfig()


class SettingsConfig(BaseModel):
    bankroll: float = 1000.0
    min_arb_percent: float = 0.5
    poll_interval_seconds: int = 60
    match_threshold: float = 80.0


class CorsConfig(BaseModel):
    allowed_origins: list[str] = ["*"]


class Config(BaseModel):
    exchanges: ExchangesConfig = ExchangesConfig()
    settings: SettingsConfig = SettingsConfig()
    cors: CorsConfig = CorsConfig()


def load_config() -> Config:
    config_path = Path(__file__).parent.parent / "config.yaml"
    data: dict = {}

    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}

    # Allow env var overrides for secrets
    cfg = Config(**data)

    if os.getenv("BETFAIR_API_KEY"):
        cfg.exchanges.betfair.api_key = os.environ["BETFAIR_API_KEY"]
        cfg.exchanges.betfair.username = os.getenv("BETFAIR_USERNAME", "")
        cfg.exchanges.betfair.password = os.getenv("BETFAIR_PASSWORD", "")
        cfg.exchanges.betfair.enabled = True

    if os.getenv("ODDS_API_KEY"):
        cfg.exchanges.odds_api.api_key = os.environ["ODDS_API_KEY"]
        cfg.exchanges.odds_api.enabled = True

    if os.getenv("BANKROLL"):
        cfg.settings.bankroll = float(os.environ["BANKROLL"])

    return cfg


config = load_config()
