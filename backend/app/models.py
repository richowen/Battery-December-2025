"""
Database models using SQLAlchemy
"""
from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean, Text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()


class ElectricityPrice(Base):
    """Electricity price data from Octopus Energy"""
    __tablename__ = "electricity_prices"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    valid_from = Column(DateTime, nullable=False, index=True)
    valid_to = Column(DateTime, nullable=False)
    price_pence = Column(Float, nullable=False)
    classification = Column(String(20))  # negative, cheap, normal, expensive
    created_at = Column(DateTime, server_default=func.now())
    
    __table_args__ = (
        Index('idx_valid_from_to', 'valid_from', 'valid_to'),
    )


class OptimizationResult(Base):
    """Results from optimization algorithm"""
    __tablename__ = "optimization_results"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    
    # Current state inputs
    current_soc = Column(Float, nullable=False)
    current_solar_kw = Column(Float, nullable=False)
    current_price_pence = Column(Float, nullable=False)
    
    # Decision outputs
    recommended_mode = Column(String(50), nullable=False)
    recommended_discharge_current = Column(Integer, nullable=False)
    recommended_immersion_main = Column(Boolean, default=False)
    recommended_immersion_lucy = Column(Boolean, default=False)
    
    # Optimization metadata
    optimization_status = Column(String(20))  # optimal, feasible, infeasible, error
    optimization_time_ms = Column(Float)
    objective_value = Column(Float)  # Total cost over optimization horizon
    
    # Reasoning
    decision_reason = Column(Text)
    
    # Schedule (JSON would be better but keeping simple)
    next_action_time = Column(DateTime)
    
    created_at = Column(DateTime, server_default=func.now())


class SystemState(Base):
    """Current system state and metrics"""
    __tablename__ = "system_state"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, unique=True, index=True)
    
    # Battery state
    battery_soc = Column(Float)
    battery_mode = Column(String(50))
    battery_discharge_current = Column(Integer)
    
    # Solar state
    solar_power_kw = Column(Float)
    solar_forecast_today_kwh = Column(Float)
    solar_forecast_next_hour_kw = Column(Float)
    
    # Grid/Price state
    current_price_pence = Column(Float)
    grid_import_kw = Column(Float, nullable=True)
    grid_export_kw = Column(Float, nullable=True)
    
    # Immersion state
    immersion_main_on = Column(Boolean)
    immersion_lucy_on = Column(Boolean)
    
    # Metrics
    daily_solar_generated_kwh = Column(Float, nullable=True)
    daily_battery_charged_kwh = Column(Float, nullable=True)
    daily_battery_discharged_kwh = Column(Float, nullable=True)
    daily_cost_gbp = Column(Float, nullable=True)
    
    created_at = Column(DateTime, server_default=func.now())


class PriceAnalysis(Base):
    """Daily price analysis and statistics"""
    __tablename__ = "price_analysis"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, nullable=False, unique=True, index=True)
    
    # Price statistics
    min_price_pence = Column(Float)
    max_price_pence = Column(Float)
    mean_price_pence = Column(Float)
    median_price_pence = Column(Float)
    
    # Thresholds
    cheap_threshold_pence = Column(Float)
    expensive_threshold_pence = Column(Float)
    
    # Classifications
    negative_count = Column(Integer)
    cheap_count = Column(Integer)
    normal_count = Column(Integer)
    expensive_count = Column(Integer)
    total_periods = Column(Integer)
    
    # Coverage
    data_coverage_hours = Column(Float)
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ScheduleOverride(Base):
    """Schedule override status for immersion heaters"""
    __tablename__ = "schedule_overrides"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    immersion_name = Column(String(50), nullable=False)  # 'main' or 'lucy'
    is_active = Column(Boolean, nullable=False, default=False, index=True)
    schedule_reason = Column(String(200))  # e.g., 'Time-based schedule: Wed 15:00-17:00'
    activated_at = Column(DateTime)
    deactivated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index('idx_immersion_active', 'immersion_name', 'is_active'),
        Index('idx_activated', 'activated_at'),
    )