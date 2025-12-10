"""
API Routes for Battery Optimization Service
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_

from app.database import get_db
from app.models import ElectricityPrice, OptimizationResult, SystemState, PriceAnalysis, ScheduleOverride, ManualOverride
from app.optimizer import BatteryOptimizer
from app.services.home_assistant import HomeAssistantClient
from app.services.octopus_energy import OctopusEnergyClient
from app.services.influxdb_client import InfluxDBService

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize clients
ha_client = HomeAssistantClient()
octopus_client = OctopusEnergyClient()
influx_client = InfluxDBService()
optimizer = BatteryOptimizer()


# Pydantic models for request/response
class RecommendationResponse(BaseModel):
    """Current recommendation for battery control"""
    mode: str = Field(..., description="Battery mode (Self Use, Force Charge, Feed-in First)")
    discharge_current: int = Field(..., description="Discharge current in amps")
    immersion_main: bool = Field(False, description="Main immersion heater on/off")
    immersion_lucy: bool = Field(False, description="Lucy immersion heater on/off")
    immersion_main_source: str = Field("optimizer", description="Source: 'manual_override', 'schedule_override', or 'optimizer'")
    immersion_lucy_source: str = Field("optimizer", description="Source: 'manual_override', 'schedule_override', or 'optimizer'")
    immersion_main_reason: str = Field("", description="Specific reason for main immersion state")
    immersion_lucy_reason: str = Field("", description="Specific reason for lucy immersion state")
    schedule_override_active: bool = Field(False, description="True if any schedule is active")
    manual_override_active: bool = Field(False, description="True if any manual override is active")
    reason: str = Field(..., description="Human-readable reason for recommendation")
    timestamp: str
    optimization_status: str = Field(..., description="optimal, feasible, infeasible, error, fallback")
    expected_soc: Optional[float] = Field(None, description="Expected SoC after action")
    next_action_time: Optional[str] = None


class PriceData(BaseModel):
    """Price period data"""
    valid_from: str
    valid_to: str
    price_pence: float
    classification: Optional[str] = None


class ScheduleUpdateRequest(BaseModel):
    """Schedule override update request"""
    immersion_name: str = Field(..., description="'main' or 'lucy'")
    is_active: bool = Field(..., description="True=schedule ON, False=schedule OFF")
    schedule_reason: Optional[str] = Field(None, description="Reason for schedule activation")
    timestamp: Optional[str] = None


class ScheduleStatusInfo(BaseModel):
    """Schedule status for one immersion"""
    is_active: bool
    schedule_reason: Optional[str] = None
    activated_at: Optional[str] = None
    duration_minutes: int = 0


class ScheduleStatusResponse(BaseModel):
    """Complete schedule override status"""
    status: str
    schedules: Dict[str, ScheduleStatusInfo]
    any_active: bool


class ScheduleHistoryItem(BaseModel):
    """Historical schedule activation"""
    id: int
    immersion_name: str
    is_active: bool
    schedule_reason: Optional[str]
    activated_at: Optional[str]
    deactivated_at: Optional[str]
    duration_minutes: Optional[int]


class ManualOverrideRequest(BaseModel):
    """Manual override request"""
    immersion_name: str = Field(..., description="'main' or 'lucy'")
    desired_state: bool = Field(..., description="True=ON, False=OFF")
    source: str = Field(default="user", description="Source of override")
    duration_hours: float = Field(default=2.0, description="Duration in hours")


class ManualOverrideStatus(BaseModel):
    """Manual override status for one immersion"""
    is_active: bool
    desired_state: Optional[bool] = None
    expires_at: Optional[str] = None
    time_remaining_minutes: int = 0
    source: Optional[str] = None


class ManualOverrideStatusResponse(BaseModel):
    """Complete manual override status"""
    status: str
    overrides: Dict[str, ManualOverrideStatus]
    any_active: bool


class SystemStateResponse(BaseModel):
    """Current system state"""
    battery_soc: float
    solar_power_kw: float
    solar_forecast_today_kwh: float
    solar_forecast_next_hour_kw: float
    battery_mode: str
    discharge_current: int
    immersion_main_on: bool
    immersion_lucy_on: bool
    current_price: Optional[float] = None
    timestamp: str


@router.get("/recommendation/now", response_model=RecommendationResponse)
async def get_current_recommendation(db: Session = Depends(get_db)):
    """
    Get current battery control recommendation
    
    This is the main endpoint that Node-RED will call every 5 minutes
    """
    try:
        # Get current system state from Home Assistant
        system_state = await ha_client.get_system_state()
        current_soc = system_state["battery_soc"]
        solar_now = system_state["solar_power_kw"]
        
        # Get prices from database
        now = datetime.now()
        prices_query = db.query(ElectricityPrice).filter(
            ElectricityPrice.valid_from >= now - timedelta(hours=1),
            ElectricityPrice.valid_to <= now + timedelta(hours=48)
        ).order_by(ElectricityPrice.valid_from).all()
        
        if not prices_query:
            raise HTTPException(
                status_code=503,
                detail="No price data available. Run /prices/refresh first."
            )
        
        prices = [
            {
                "valid_from": p.valid_from,
                "valid_to": p.valid_to,
                "price_pence": p.price_pence,
                "classification": p.classification
            }
            for p in prices_query
        ]
        
        # Simple solar forecast (could be improved)
        hour = now.hour
        solar_forecast = []
        for h in range(24):
            forecast_hour = (hour + h) % 24
            if 6 <= forecast_hour <= 18:
                # Daytime - use simple pattern
                solar_forecast.append(min(solar_now * 1.2, 5.0))
            else:
                solar_forecast.append(0.0)
        
        # Query schedule override status
        schedule_status_dict = {}
        try:
            for immersion_name in ['main', 'lucy']:
                active_override = db.query(ScheduleOverride).filter(
                    and_(
                        ScheduleOverride.immersion_name == immersion_name,
                        ScheduleOverride.is_active == True
                    )
                ).order_by(desc(ScheduleOverride.activated_at)).first()
                
                # Check if active and not stale (updated within 5 minutes)
                if active_override and active_override.activated_at:
                    time_since_activation = (now - active_override.activated_at).total_seconds() / 60
                    if time_since_activation <= 5:
                        schedule_status_dict[immersion_name] = {
                            'is_active': True,
                            'schedule_reason': active_override.schedule_reason
                        }
                    else:
                        # Mark as inactive if stale
                        active_override.is_active = False
                        active_override.deactivated_at = now
                        db.commit()
        except Exception as e:
            # If schedule query fails, continue without schedule override
            logger.warning(f"Failed to query schedule status: {e}")
        
        # Query manual override status
        manual_override_dict = {}
        try:
            for immersion_name in ['main', 'lucy']:
                active_override = db.query(ManualOverride).filter(
                    and_(
                        ManualOverride.immersion_name == immersion_name,
                        ManualOverride.is_active == True,
                        ManualOverride.expires_at > now
                    )
                ).order_by(desc(ManualOverride.created_at)).first()
                
                if active_override:
                    time_remaining = int((active_override.expires_at - now).total_seconds() / 60)
                    manual_override_dict[immersion_name] = {
                        'is_active': True,
                        'desired_state': active_override.desired_state,
                        'time_remaining_minutes': max(0, time_remaining)
                    }
        except Exception as e:
            # If manual override query fails, continue without it
            logger.warning(f"Failed to query manual override status: {e}")
        
        # Run optimization with schedule and manual override status
        result = optimizer.optimize_schedule(
            current_soc=current_soc,
            prices=prices,
            solar_forecast=solar_forecast,
            horizon_hours=24,
            schedule_status=schedule_status_dict,
            manual_override_status=manual_override_dict
        )
        
        recommendation = result["current_recommendation"]
        
        # Store optimization result in database
        opt_result = OptimizationResult(
            timestamp=now,
            current_soc=current_soc,
            current_solar_kw=solar_now,
            current_price_pence=prices[0]["price_pence"],
            recommended_mode=recommendation["mode"],
            recommended_discharge_current=recommendation["discharge_current"],
            recommended_immersion_main=False,  # TODO: Add immersion logic
            recommended_immersion_lucy=False,
            optimization_status=result["status"],
            optimization_time_ms=result.get("optimization_time_ms", 0),
            objective_value=result.get("objective_value"),
            decision_reason=recommendation["reason"],
            next_action_time=result.get("next_action_time")
        )
        db.add(opt_result)
        db.commit()
        
        # Write to InfluxDB if enabled
        if influx_client.enabled:
            influx_client.write_optimization_result(result)
        
        return RecommendationResponse(
            mode=recommendation["mode"],
            discharge_current=recommendation["discharge_current"],
            immersion_main=recommendation.get("immersion_main", False),
            immersion_lucy=recommendation.get("immersion_lucy", False),
            immersion_main_source=recommendation.get("immersion_main_source", "optimizer"),
            immersion_lucy_source=recommendation.get("immersion_lucy_source", "optimizer"),
            immersion_main_reason=recommendation.get("immersion_main_reason", recommendation["reason"]),
            immersion_lucy_reason=recommendation.get("immersion_lucy_reason", recommendation["reason"]),
            schedule_override_active=recommendation.get("schedule_override_active", False),
            manual_override_active=recommendation.get("manual_override_active", False),
            reason=recommendation["reason"],
            timestamp=now.isoformat(),
            optimization_status=result["status"],
            expected_soc=recommendation.get("expected_soc"),
            next_action_time=result["next_action_time"].isoformat() if result.get("next_action_time") else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting recommendation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/prices/refresh")
async def refresh_prices(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Fetch latest prices from Octopus Energy and store in database
    
    This should be called every 30 minutes
    """
    try:
        # Fetch prices
        prices = await octopus_client.fetch_prices()
        
        if not prices:
            raise HTTPException(status_code=503, detail="Failed to fetch prices from Octopus Energy")
        
        # Classify prices
        classified_prices = octopus_client.classify_prices(prices)
        
        # Store in database (delete old, insert new)
        cutoff = datetime.now() - timedelta(hours=24)
        db.query(ElectricityPrice).filter(
            ElectricityPrice.valid_from < cutoff
        ).delete()
        
        for price_data in classified_prices:
            # Check if already exists
            existing = db.query(ElectricityPrice).filter(
                ElectricityPrice.valid_from == price_data["valid_from"]
            ).first()
            
            if not existing:
                price_record = ElectricityPrice(
                    valid_from=price_data["valid_from"],
                    valid_to=price_data["valid_to"],
                    price_pence=price_data["price_pence"],
                    classification=price_data["classification"]
                )
                db.add(price_record)
        
        db.commit()
        
        # Calculate and store price analysis
        stats = octopus_client.get_price_statistics(classified_prices)
        if stats:
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            analysis = db.query(PriceAnalysis).filter(
                PriceAnalysis.date == today
            ).first()
            
            if analysis:
                # Update existing
                analysis.min_price_pence = stats["min"]
                analysis.max_price_pence = stats["max"]
                analysis.mean_price_pence = stats["mean"]
                analysis.median_price_pence = stats["median"]
                analysis.cheap_threshold_pence = stats["cheap_threshold"]
                analysis.expensive_threshold_pence = stats["expensive_threshold"]
                analysis.negative_count = stats["negative_count"]
                analysis.total_periods = stats["total_periods"]
            else:
                # Create new
                analysis = PriceAnalysis(
                    date=today,
                    min_price_pence=stats["min"],
                    max_price_pence=stats["max"],
                    mean_price_pence=stats["mean"],
                    median_price_pence=stats["median"],
                    cheap_threshold_pence=stats["cheap_threshold"],
                    expensive_threshold_pence=stats["expensive_threshold"],
                    negative_count=stats["negative_count"],
                    cheap_count=stats.get("cheap_count", 0),
                    normal_count=stats["total_periods"] - stats["negative_count"] - stats.get("cheap_count", 0) - stats.get("expensive_count", 0),
                    expensive_count=stats.get("expensive_count", 0),
                    total_periods=stats["total_periods"],
                    data_coverage_hours=stats["total_periods"] * 0.5
                )
                db.add(analysis)
            
            db.commit()
        
        # Write to InfluxDB if enabled
        if influx_client.enabled:
            # Write individual price points
            influx_client.write_prices(classified_prices)
            # Write summary statistics
            influx_client.write_price_analysis(stats)
        
        logger.info(f"Stored {len(classified_prices)} price periods")
        
        return {
            "status": "success",
            "prices_stored": len(classified_prices),
            "coverage_hours": len(classified_prices) * 0.5,
            "statistics": stats
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing prices: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prices/current", response_model=List[PriceData])
async def get_current_prices(
    hours: int = 24,
    db: Session = Depends(get_db)
):
    """Get current and upcoming prices"""
    try:
        now = datetime.now()
        prices = db.query(ElectricityPrice).filter(
            ElectricityPrice.valid_from >= now,
            ElectricityPrice.valid_from < now + timedelta(hours=hours)
        ).order_by(ElectricityPrice.valid_from).all()
        
        return [
            PriceData(
                valid_from=p.valid_from.isoformat(),
                valid_to=p.valid_to.isoformat(),
                price_pence=p.price_pence,
                classification=p.classification
            )
            for p in prices
        ]
    
    except Exception as e:
        logger.error(f"Error getting prices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/state/current", response_model=SystemStateResponse)
async def get_system_state(db: Session = Depends(get_db)):
    """Get current system state from Home Assistant"""
    try:
        state = await ha_client.get_system_state()
        
        # Get current price
        now = datetime.now()
        current_price_query = db.query(ElectricityPrice).filter(
            ElectricityPrice.valid_from <= now,
            ElectricityPrice.valid_to > now
        ).first()
        
        current_price = current_price_query.price_pence if current_price_query else None
        
        # Store state in database
        state_record = SystemState(
            timestamp=now,
            battery_soc=state["battery_soc"],
            battery_mode=state["battery_mode"],
            battery_discharge_current=state["discharge_current"],
            solar_power_kw=state["solar_power_kw"],
            solar_forecast_today_kwh=state["solar_forecast_today_kwh"],
            solar_forecast_next_hour_kw=state["solar_forecast_next_hour_kw"],
            current_price_pence=current_price,
            immersion_main_on=state["immersion_main_on"],
            immersion_lucy_on=state["immersion_lucy_on"]
        )
        db.add(state_record)
        db.commit()
        
        return SystemStateResponse(
            **state,
            current_price=current_price
        )
    
    except Exception as e:
        logger.error(f"Error getting system state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/recommendations")
async def get_recommendation_history(
    hours: int = 24,
    db: Session = Depends(get_db)
):
    """Get historical recommendations"""
    try:
        cutoff = datetime.now() - timedelta(hours=hours)
        results = db.query(OptimizationResult).filter(
            OptimizationResult.timestamp >= cutoff
        ).order_by(desc(OptimizationResult.timestamp)).all()
        
        return [
            {
                "timestamp": r.timestamp.isoformat(),
                "mode": r.recommended_mode,
                "discharge_current": r.recommended_discharge_current,
                "soc": r.current_soc,
                "solar_kw": r.current_solar_kw,
                "price_pence": r.current_price_pence,
                "reason": r.decision_reason,
                "optimization_status": r.optimization_status
            }
            for r in results
        ]
    
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/daily")
async def get_daily_stats(db: Session = Depends(get_db)):
    """Get today's statistics"""
    try:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Price analysis
        price_analysis = db.query(PriceAnalysis).filter(
            PriceAnalysis.date == today
        ).first()
        
        # Latest system state
        latest_state = db.query(SystemState).order_by(
            desc(SystemState.timestamp)
        ).first()
        
        return {
            "date": today.isoformat(),
            "price_stats": {
                "min": price_analysis.min_price_pence if price_analysis else None,
                "max": price_analysis.max_price_pence if price_analysis else None,
                "mean": price_analysis.mean_price_pence if price_analysis else None,
                "negative_count": price_analysis.negative_count if price_analysis else 0
            } if price_analysis else None,
            "current_state": {
                "battery_soc": latest_state.battery_soc if latest_state else None,
                "solar_power_kw": latest_state.solar_power_kw if latest_state else None,
                "battery_mode": latest_state.battery_mode if latest_state else None
            } if latest_state else None
        }
    
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Schedule Override Endpoints

@router.post("/schedule/update")
async def update_schedule(
    request: ScheduleUpdateRequest,
    db: Session = Depends(get_db)
):
    """
    Update schedule override status
    
    Called by Node-RED schedule flow when schedule period starts/ends
    """
    try:
        immersion_name = request.immersion_name.lower()
        if immersion_name not in ['main', 'lucy']:
            raise HTTPException(
                status_code=400,
                detail="immersion_name must be 'main' or 'lucy'"
            )
        
        timestamp = datetime.fromisoformat(request.timestamp) if request.timestamp else datetime.now()
        
        # Deactivate any existing active override for this immersion
        active_overrides = db.query(ScheduleOverride).filter(
            and_(
                ScheduleOverride.immersion_name == immersion_name,
                ScheduleOverride.is_active == True
            )
        ).all()
        
        for override in active_overrides:
            override.is_active = False
            override.deactivated_at = timestamp
        
        # Create new override record
        new_override = ScheduleOverride(
            immersion_name=immersion_name,
            is_active=request.is_active,
            schedule_reason=request.schedule_reason,
            activated_at=timestamp if request.is_active else None,
            deactivated_at=None if request.is_active else timestamp
        )
        db.add(new_override)
        db.commit()
        db.refresh(new_override)
        
        status_msg = "active" if request.is_active else "inactive"
        logger.info(
            f"Schedule override for '{immersion_name}' immersion set to {status_msg}"
            + (f" - {request.schedule_reason}" if request.schedule_reason else "")
        )
        
        return {
            "status": "success",
            "message": f"Schedule override for '{immersion_name}' immersion set to {status_msg}",
            "override_id": new_override.id,
            "effective_until": None
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating schedule: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schedule/status", response_model=ScheduleStatusResponse)
async def get_schedule_status(db: Session = Depends(get_db)):
    """
    Get current schedule override status for all immersions
    
    Called by optimizer to check if schedule is active
    """
    try:
        now = datetime.now()
        schedules = {}
        
        for immersion_name in ['main', 'lucy']:
            # Get most recent active override
            active_override = db.query(ScheduleOverride).filter(
                and_(
                    ScheduleOverride.immersion_name == immersion_name,
                    ScheduleOverride.is_active == True
                )
            ).order_by(desc(ScheduleOverride.activated_at)).first()
            
            if active_override and active_override.activated_at:
                # Check if stale (not updated in 5 minutes)
                time_since_activation = (now - active_override.activated_at).total_seconds() / 60
                if time_since_activation > 5:
                    # Mark as inactive if stale
                    active_override.is_active = False
                    active_override.deactivated_at = now
                    db.commit()
                    active_override = None
            
            if active_override:
                duration = int((now - active_override.activated_at).total_seconds() / 60) if active_override.activated_at else 0
                schedules[immersion_name] = ScheduleStatusInfo(
                    is_active=True,
                    schedule_reason=active_override.schedule_reason,
                    activated_at=active_override.activated_at.isoformat() if active_override.activated_at else None,
                    duration_minutes=duration
                )
            else:
                schedules[immersion_name] = ScheduleStatusInfo(
                    is_active=False,
                    schedule_reason=None,
                    activated_at=None,
                    duration_minutes=0
                )
        
        any_active = any(s.is_active for s in schedules.values())
        
        return ScheduleStatusResponse(
            status="success",
            schedules=schedules,
            any_active=any_active
        )
    
    except Exception as e:
        logger.error(f"Error getting schedule status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schedule/history")
async def get_schedule_history(
    immersion_name: Optional[str]= None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    Get historical schedule activations
    
    Query parameters:
    - immersion_name: Filter by 'main' or 'lucy' (optional)
    - start_date: ISO 8601 date (optional)
    - end_date: ISO 8601 date (optional)
    - limit: Maximum records (default 100)
    """
    try:
        query = db.query(ScheduleOverride)
        
        # Apply filters
        if immersion_name:
            if immersion_name.lower() not in ['main', 'lucy']:
                raise HTTPException(
                    status_code=400,
                    detail="immersion_name must be 'main' or 'lucy'"
                )
            query = query.filter(ScheduleOverride.immersion_name == immersion_name.lower())
        
        if start_date:
            start_dt = datetime.fromisoformat(start_date)
            query = query.filter(ScheduleOverride.activated_at >= start_dt)
        
        if end_date:
            end_dt = datetime.fromisoformat(end_date)
            query = query.filter(ScheduleOverride.activated_at <= end_dt)
        
        # Order and limit
        results = query.order_by(desc(ScheduleOverride.activated_at)).limit(limit).all()
        
        history = []
        for r in results:
            duration = None
            if r.activated_at and r.deactivated_at:
                duration = int((r.deactivated_at - r.activated_at).total_seconds() / 60)
            
            history.append(ScheduleHistoryItem(
                id=r.id,
                immersion_name=r.immersion_name,
                is_active=r.is_active,
                schedule_reason=r.schedule_reason,
                activated_at=r.activated_at.isoformat() if r.activated_at else None,
                deactivated_at=r.deactivated_at.isoformat() if r.deactivated_at else None,
                duration_minutes=duration
            ))
        
        return {
            "status": "success",
            "history": history,
            "total_records": len(history)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting schedule history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Manual Override Endpoints

@router.post("/manual-override/set")
async def set_manual_override(
    request: ManualOverrideRequest,
    db: Session = Depends(get_db)
):
    """
    Set manual override for immersion heater
    
    Called by Node-RED state monitor when user manually toggles switch
    """
    try:
        immersion_name = request.immersion_name.lower()
        if immersion_name not in ['main', 'lucy']:
            raise HTTPException(
                status_code=400,
                detail="immersion_name must be 'main' or 'lucy'"
            )
        
        now = datetime.now()
        expires_at = now + timedelta(hours=request.duration_hours)
        
        # Deactivate any existing active override for this immersion
        active_overrides = db.query(ManualOverride).filter(
            and_(
                ManualOverride.immersion_name == immersion_name,
                ManualOverride.is_active == True
            )
        ).all()
        
        for override in active_overrides:
            override.is_active = False
            override.cleared_at = now
            override.cleared_by = 'system_replaced'
        
        # Create new override
        new_override = ManualOverride(
            immersion_name=immersion_name,
            is_active=True,
            desired_state=request.desired_state,
            source=request.source,
            expires_at=expires_at
        )
        db.add(new_override)
        db.commit()
        db.refresh(new_override)
        
        logger.info(
            f"Manual override set: {immersion_name} = "
            f"{'ON' if request.desired_state else 'OFF'} "
            f"(expires in {request.duration_hours}h)"
        )
        
        return {
            "status": "success",
            "message": f"Manual override set for '{immersion_name}' immersion",
            "override_id": new_override.id,
            "expires_at": expires_at.isoformat(),
            "current_state": request.desired_state
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting manual override: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/manual-override/status", response_model=ManualOverrideStatusResponse)
async def get_manual_override_status(db: Session = Depends(get_db)):
    """
    Get current manual override status for all immersions
    
    Called by optimizer to check if manual override is active
    """
    try:
        now = datetime.now()
        overrides = {}
        
        for immersion_name in ['main', 'lucy']:
            # Get most recent active override that hasn't expired
            active_override = db.query(ManualOverride).filter(
                and_(
                    ManualOverride.immersion_name == immersion_name,
                    ManualOverride.is_active == True,
                    ManualOverride.expires_at > now
                )
            ).order_by(desc(ManualOverride.created_at)).first()
            
            if active_override:
                time_remaining = int((active_override.expires_at - now).total_seconds() / 60)
                overrides[immersion_name] = ManualOverrideStatus(
                    is_active=True,
                    desired_state=active_override.desired_state,
                    expires_at=active_override.expires_at.isoformat(),
                    time_remaining_minutes=max(0, time_remaining),
                    source=active_override.source
                )
            else:
                overrides[immersion_name] = ManualOverrideStatus(
                    is_active=False,
                    desired_state=None,
                    expires_at=None,
                    time_remaining_minutes=0,
                    source=None
                )
        
        any_active = any(o.is_active for o in overrides.values())
        
        return ManualOverrideStatusResponse(
            status="success",
            overrides=overrides,
            any_active=any_active
        )
    
    except Exception as e:
        logger.error(f"Error getting manual override status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/manual-override/clear")
async def clear_manual_override(
    immersion_name: str,
    cleared_by: str = "user",
    db: Session = Depends(get_db)
):
    """
    Clear manual override for specified immersion
    
    Called when user clicks "Resume Auto" button or override expires
    """
    try:
        immersion_name = immersion_name.lower()
        if immersion_name not in ['main', 'lucy']:
            raise HTTPException(
                status_code=400,
                detail="immersion_name must be 'main' or 'lucy'"
            )
        
        now = datetime.now()
        
        active_overrides = db.query(ManualOverride).filter(
            and_(
                ManualOverride.immersion_name == immersion_name,
                ManualOverride.is_active == True
            )
        ).all()
        
        cleared_count = 0
        for override in active_overrides:
            override.is_active = False
            override.cleared_at = now
            override.cleared_by = cleared_by
            cleared_count += 1
        
        db.commit()
        
        logger.info(f"Manual override cleared for '{immersion_name}' by {cleared_by}")
        
        return {
            "status": "success",
            "message": f"Manual override cleared for '{immersion_name}' immersion",
            "cleared_count": cleared_count,
            "system_resuming_control": True
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing manual override: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/manual-override/clear-all")
async def clear_all_manual_overrides(
    cleared_by: str = "user",
    db: Session = Depends(get_db)
):
    """Clear all active manual overrides"""
    try:
        now = datetime.now()
        
        active_overrides = db.query(ManualOverride).filter(
            ManualOverride.is_active == True
        ).all()
        
        for override in active_overrides:
            override.is_active = False
            override.cleared_at = now
            override.cleared_by = cleared_by
        
        db.commit()
        
        logger.info(f"All manual overrides cleared by {cleared_by} ({len(active_overrides)} total)")
        
        return {
            "status": "success",
            "cleared_count": len(active_overrides),
            "message": f"All manual overrides cleared"
        }
    
    except Exception as e:
        logger.error(f"Error clearing all manual overrides: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))