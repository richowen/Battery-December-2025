"""
Configuration management using Pydantic Settings
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Database
    db_host: str = Field(default="192.168.1.3", env="DB_HOST")
    db_port: int = Field(default=3306, env="DB_PORT")
    db_user: str = Field(default="optimizer", env="DB_USER")
    db_password: str = Field(env="DB_PASSWORD")
    db_name: str = Field(default="battery_optimizer", env="DB_NAME")
    
    # Home Assistant
    ha_url: str = Field(default="http://192.168.1.3:8123", env="HA_URL")
    ha_token: str = Field(env="HA_TOKEN")
    
    # InfluxDB
    influx_enabled: bool = Field(default=False, env="INFLUX_ENABLED")
    influx_url: Optional[str] = Field(default=None, env="INFLUX_URL")
    influx_token: Optional[str] = Field(default=None, env="INFLUX_TOKEN")
    influx_org: Optional[str] = Field(default="unraid", env="INFLUX_ORG")
    influx_bucket: Optional[str] = Field(default="battery-optimizer", env="INFLUX_BUCKET")
    
    # Octopus Energy
    octopus_product: str = Field(default="AGILE-24-10-01", env="OCTOPUS_PRODUCT")
    octopus_tariff: str = Field(default="E-1R-AGILE-24-10-01-E", env="OCTOPUS_TARIFF")
    octopus_region: str = Field(default="E", env="OCTOPUS_REGION")
    
    # Application
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    optimization_interval: int = Field(default=300, env="OPTIMIZATION_INTERVAL")
    price_fetch_interval: int = Field(default=1800, env="PRICE_FETCH_INTERVAL")
    api_port: int = Field(default=8000, env="API_PORT")
    
    # Battery Configuration
    battery_capacity_kwh: float = Field(default=10.0, env="BATTERY_CAPACITY_KWH")
    battery_max_charge_kw: float = Field(default=5.0, env="BATTERY_MAX_CHARGE_KW")
    battery_max_discharge_kw: float = Field(default=5.0, env="BATTERY_MAX_DISCHARGE_KW")
    battery_efficiency: float = Field(default=0.95, env="BATTERY_EFFICIENCY")
    battery_min_soc: int = Field(default=10, env="BATTERY_MIN_SOC")
    battery_max_soc: int = Field(default=100, env="BATTERY_MAX_SOC")
    
    # Solar Configuration
    solar_capacity_kw: float = Field(default=8.0, env="SOLAR_CAPACITY_KW")
    
    # Home Assistant Entity IDs
    ha_entity_battery_soc: str = Field(
        default="sensor.foxinverter_battery_soc",
        env="HA_ENTITY_BATTERY_SOC"
    )
    ha_entity_solar_power: str = Field(
        default="sensor.pv_power_foxinverter",
        env="HA_ENTITY_SOLAR_POWER"
    )
    ha_entity_solar_forecast_today: str = Field(
        default="sensor.solcast_pv_forecast_forecast_remaining_today",
        env="HA_ENTITY_SOLAR_FORECAST_TODAY"
    )
    ha_entity_solar_forecast_next_hour: str = Field(
        default="sensor.solcast_pv_forecast_power_in_1_hour",
        env="HA_ENTITY_SOLAR_FORECAST_NEXT_HOUR"
    )
    ha_entity_battery_mode: str = Field(
        default="select.foxinverter_work_mode",
        env="HA_ENTITY_BATTERY_MODE"
    )
    ha_entity_discharge_current: str = Field(
        default="number.foxinverter_max_discharge_current",
        env="HA_ENTITY_DISCHARGE_CURRENT"
    )
    ha_entity_immersion_main: str = Field(
        default="switch.immersion_switch",
        env="HA_ENTITY_IMMERSION_MAIN"
    )
    ha_entity_immersion_lucy: str = Field(
        default="switch.immersion_lucy_switch",
        env="HA_ENTITY_IMMERSION_LUCY"
    )
    
    @property
    def database_url(self) -> str:
        """Construct database URL"""
        return f"mysql+pymysql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    @property
    def octopus_api_url(self) -> str:
        """Construct Octopus Energy API URL"""
        return f"https://api.octopus.energy/v1/products/{self.octopus_product}/electricity-tariffs/{self.octopus_tariff}/standard-unit-rates/"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()