from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "The State House"
    app_env: str = "development"
    secret_key: str = "dev-secret-change-me"
    access_token_expire_minutes: int = 60 * 24 * 7
    database_url: str = "sqlite+aiosqlite:///./statehouse.db"
    # Neon env pull also provides these (pooled URL is preferred for the app)
    database_url_unpooled: str | None = None
    neon_branch: str | None = None
    neon_auth_base_url: str | None = None
    neon_auth_jwks_url: str | None = None
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    # Also allow Vercel preview/prod hosts (FastAPI allow_origin_regex)
    cors_origin_regex: str = r"https://.*\.vercel\.app"

    # 8:1 calendar — 4 game years = 6 real months
    game_time_ratio: int = 8
    home_state_reset_days: int = 3
    starting_cash: float = 500.0
    starting_age: int = 18

    # Torn-like regen: 1 energy every N minutes
    energy_regen_minutes: int = 5
    # Heat decays by this amount every hour while free
    heat_decay_per_hour: float = 2.0

    # Travel
    travel_base_cost: float = 25.0
    travel_base_minutes: int = 20

    # Bank / loans
    loan_interest_rate: float = 0.12
    loan_max_amount: float = 5000.0
    loan_term_real_days: float = 45.0  # ~1 game year on 8:1
    savings_apr: float = 0.04  # annualized; applied daily on tick
    bank_transfer_fee: float = 5.0
    bank_min_transfer: float = 10.0

    # Stock exchange (separate from bank)
    stock_ipo_min_business_cash: float = 2000.0
    stock_ipo_min_business_age_days: float = 3.0
    stock_ipo_listing_fee: float = 500.0
    stock_ipo_min_owner_reputation: int = 5
    stock_ipo_min_shares: int = 1000
    stock_ipo_max_shares: int = 100000
    stock_trade_fee_rate: float = 0.01  # 1% brokerage on secondary trades
    stock_price_impact: float = 0.002  # price moves slightly per trade volume

    # Health
    health_regen_minutes: int = 10  # +1 HP when not hospitalized/sick
    clinic_heal_cost_per_hp: float = 2.5
    hospital_base_hours: float = 4.0

    # Politics (8:1 calendar: election ~ every 6 real months)
    mp_min_age: float = 25.0
    president_min_age: float = 30.0
    election_campaign_days: float = 21.0
    election_voting_days: float = 7.0
    election_term_days: float = 182.0
    candidacy_fee_mp: float = 250.0
    candidacy_fee_president: float = 1000.0
    max_heat_to_run: float = 40.0
    bill_debate_days: float = 2.5
    budget_debate_days: float = 3.0
    budget_interval_days: float = 45.0  # ~6.5 weeks
    cabinet_require_mp: bool = True
    minister_weekly_salary: float = 400.0
    # Tax / treasury (keep moderate — felt but not crushing)
    default_national_tax_rate: float = 0.05
    corporate_tax_multiplier: float = 0.70  # corp rate = national * this (~3.5%)
    treasury_max_disburse: float = 5000.0  # per transfer by Finance/President
    min_national_tax_rate: float = 0.03
    max_national_tax_rate: float = 0.10

    # Chat
    chat_max_length: int = 280
    chat_cooldown_seconds: int = 10

    # Automated NPC citizens (populate states + act like players)
    npc_sim_enabled: bool = True
    npc_per_state: int = 14
    npc_sim_interval_seconds: float = 18.0
    npc_sim_batch_size: int = 10

    # Nerve / gym / combat
    nerve_regen_minutes: int = 8
    gym_energy_cost: int = 5
    gym_gain_base: float = 1.2
    attack_energy_cost: int = 20
    jail_bail_per_hour: float = 40.0

    # Business ops
    business_ops_interval_hours: float = 6.0
    business_payroll_days: float = 7.0
    business_base_revenue_per_interval: float = 40.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_neon_postgres(self) -> bool:
        url = (self.database_url or "").lower()
        return "neon.tech" in url or (
            url.startswith("postgresql") and bool(self.neon_branch)
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
