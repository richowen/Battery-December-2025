"""
Battery Optimization Engine using Linear Programming
"""
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np
from pulp import LpProblem, LpMinimize, LpVariable, LpStatus, lpSum, value
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)


class BatteryOptimizer:
    """
    Optimizes battery charge/discharge schedule using Linear Programming
    to minimize electricity costs over a 24-48 hour horizon
    """
    
    def __init__(self):
        self.capacity_kwh = settings.battery_capacity_kwh
        self.max_charge_kw = settings.battery_max_charge_kw
        self.max_discharge_kw = settings.battery_max_discharge_kw
        self.efficiency = settings.battery_efficiency
        self.min_soc = settings.battery_min_soc
        self.max_soc = settings.battery_max_soc
        
    def optimize_schedule(
        self,
        current_soc: float,
        prices: List[Dict],
        solar_forecast: List[float],
        load_forecast: Optional[List[float]] = None,
        horizon_hours: int = 24,
        schedule_status: Optional[Dict] = None,
        manual_override_status: Optional[Dict] = None
    ) -> Dict:
        """
        Generate optimal battery schedule
        
        Args:
            current_soc: Current battery state of charge (%)
            prices: List of price periods with 'from', 'to', 'price_pence'
            solar_forecast: Hourly solar generation forecast (kW)
            load_forecast: Hourly load forecast (kW), defaults to 2kW constant
            horizon_hours: Optimization horizon in hours
            schedule_status: Schedule override status dict
            manual_override_status: Manual override status dict
            
        Returns:
            Dict with schedule, current recommendation, and metrics
        """
        try:
            start_time = datetime.now()
            
            # Prepare time periods (30-minute intervals)
            num_periods = horizon_hours * 2  # 30-min intervals
            
            # Align prices to 30-min periods
            period_prices = self._align_prices_to_periods(prices, num_periods)
            
            # Align solar forecast to periods
            period_solar = self._align_solar_to_periods(solar_forecast, num_periods)
            
            # Use constant load if not provided
            if load_forecast is None:
                period_load = [2.0] * num_periods  # Assume 2kW constant load
            else:
                period_load = self._align_load_to_periods(load_forecast, num_periods)
            
            # Create optimization problem
            prob = LpProblem("Battery_Optimization", LpMinimize)
            
            # Decision variables
            # charge[t] = kW charging in period t (positive)
            charge = [LpVariable(f"charge_{t}", 0, self.max_charge_kw) 
                     for t in range(num_periods)]
            
            # discharge[t] = kW discharging in period t (positive)
            discharge = [LpVariable(f"discharge_{t}", 0, self.max_discharge_kw) 
                        for t in range(num_periods)]
            
            # soc[t] = state of charge at end of period t (%)
            soc = [LpVariable(f"soc_{t}", self.min_soc, self.max_soc) 
                  for t in range(num_periods)]
            
            # grid_import[t] = kW imported from grid (positive)
            grid_import = [LpVariable(f"grid_import_{t}", 0, None)
                          for t in range(num_periods)]
            
            # grid_export[t] = kW exported to grid (positive)
            grid_export = [LpVariable(f"grid_export_{t}", 0, None) 
                          for t in range(num_periods)]
            
            # Objective: Minimize total cost
            # Cost = Import × Price - Export × Price (export gets paid)
            prob += lpSum([
                (grid_import[t] * period_prices[t] * 0.5 -  # 0.5 for 30-min period
                 grid_export[t] * period_prices[t] * 0.5 * 0.15)  # 15% of import price for export
                for t in range(num_periods)
            ])
            
            # Constraints
            
            # 1. Initial SOC
            # Note: Can't divide LpVariable, so multiply by inverse
            efficiency_loss = 1.0 / self.efficiency
            prob += soc[0] == current_soc + (
                (charge[0] * self.efficiency - discharge[0] * efficiency_loss) *
                0.5 * 100 / self.capacity_kwh  # Convert kW to % change
            )
            
            # 2. SOC evolution
            for t in range(1, num_periods):
                prob += soc[t] == soc[t-1] + (
                    (charge[t] * self.efficiency - discharge[t] * efficiency_loss) *
                    0.5 * 100 / self.capacity_kwh
                )
            
            # 3. Energy balance at each period
            for t in range(num_periods):
                # Solar + Battery Discharge + Grid Import = Load + Battery Charge + Grid Export
                prob += (
                    period_solar[t] + discharge[t] + grid_import[t] == 
                    period_load[t] + charge[t] + grid_export[t]
                )
            
            # 4. Cannot charge and discharge simultaneously (simplified)
            # This is handled implicitly by the objective function
            
            # 5. Minimum SOC at end for resilience
            prob += soc[num_periods - 1] >= 20
            
            # Solve
            prob.solve()
            
            # Check solution status
            status = LpStatus[prob.status]
            
            if status != "Optimal":
                logger.warning(f"Optimization status: {status}")
                return self._fallback_schedule(current_soc, period_prices[0])
            
            # Extract solution
            schedule = []
            for t in range(num_periods):
                schedule.append({
                    "period": t,
                    "charge_kw": value(charge[t]),
                    "discharge_kw": value(discharge[t]),
                    "soc": value(soc[t]),
                    "grid_import_kw": value(grid_import[t]),
                    "grid_export_kw": value(grid_export[t]),
                    "price_pence": period_prices[t]
                })
            
            # Current recommendation (first period)
            current_action = schedule[0]
            
            # Determine mode and discharge current
            current_price = period_prices[0]
            
            # Calculate expensive threshold
            sorted_prices = sorted(period_prices)
            expensive_threshold = sorted_prices[int(len(sorted_prices) * 0.75)]
            
            # OVERRIDE: If price is expensive, ALWAYS max discharge - no compromises
            if current_price >= expensive_threshold:
                mode = "Self Use"
                discharge_current = 50
            elif current_action["charge_kw"] > 0.5:
                mode = "Force Charge"
                discharge_current = 0
            elif current_action["discharge_kw"] > 2.0:
                mode = "Self Use"
                discharge_current = min(50, int(current_action["discharge_kw"] * 10))
            else:
                mode = "Self Use"
                discharge_current = 20  # Minimal discharge
            
            # Determine immersion heater status with 3-tier priority system
            immersion_main = False
            immersion_lucy = False
            immersion_main_source = "optimizer"
            immersion_lucy_source = "optimizer"
            immersion_main_reason = ""
            immersion_lucy_reason = ""
            schedule_override_active = False
            manual_override_active = False
            
            # Initialize status dicts
            if schedule_status is None:
                schedule_status = {}
            if manual_override_status is None:
                manual_override_status = {}
            
            current_price = period_prices[0]
            
            # === MAIN IMMERSION 3-TIER PRIORITY ===
            
            # PRIORITY 1: Manual Override (highest)
            manual_main = manual_override_status.get('main', {}).get('is_active', False)
            if manual_main:
                immersion_main = manual_override_status['main']['desired_state']
                immersion_main_source = "manual_override"
                time_left = manual_override_status['main'].get('time_remaining_minutes', 0)
                immersion_main_reason = f"Manual override active ({time_left}min remaining)"
                manual_override_active = True
            # PRIORITY 2: Schedule Override (medium)
            elif schedule_status.get('main', {}).get('is_active', False):
                immersion_main = True
                immersion_main_source = "schedule_override"
                immersion_main_reason = schedule_status['main'].get('schedule_reason', 'Schedule active')
                schedule_override_active = True
            # PRIORITY 3: Optimizer Logic (normal)
            else:
                # Turn on main immersion if:
                # 1. Price is negative AND battery is near full
                # 2. Price is very cheap (<2p) AND battery is full
                # 3. High solar generation AND battery is full
                if current_price < 0 and current_soc >= 90:
                    immersion_main = True
                    immersion_main_reason = f"Negative price ({current_price:.1f}p) + High SOC ({current_soc:.0f}%)"
                elif current_price < 2 and current_soc >= 95:
                    immersion_main = True
                    immersion_main_reason = f"Very cheap price ({current_price:.1f}p) + Battery full ({current_soc:.0f}%)"
                elif solar_forecast[0] > 5.0 and current_soc >= 95:
                    immersion_main = True
                    immersion_main_reason = f"High solar ({solar_forecast[0]:.1f}kW) + Battery full ({current_soc:.0f}%)"
                else:
                    immersion_main_reason = f"Conditions not met (price: {current_price:.1f}p, SOC: {current_soc:.0f}%)"
            
            # === LUCY IMMERSION 3-TIER PRIORITY ===
            
            # PRIORITY 1: Manual Override (highest)
            manual_lucy = manual_override_status.get('lucy', {}).get('is_active', False)
            if manual_lucy:
                immersion_lucy = manual_override_status['lucy']['desired_state']
                immersion_lucy_source = "manual_override"
                time_left = manual_override_status['lucy'].get('time_remaining_minutes', 0)
                immersion_lucy_reason = f"Manual override active ({time_left}min remaining)"
                manual_override_active = True
            # PRIORITY 2: Schedule Override (medium)
            elif schedule_status.get('lucy', {}).get('is_active', False):
                immersion_lucy = True
                immersion_lucy_source = "schedule_override"
                immersion_lucy_reason = schedule_status['lucy'].get('schedule_reason', 'Schedule active')
                schedule_override_active = True
            # PRIORITY 3: Optimizer Logic (normal)
            else:
                # Lucy follows same logic as main
                if current_price < 0 and current_soc >= 90:
                    immersion_lucy = True
                    immersion_lucy_reason = f"Negative price ({current_price:.1f}p) + High SOC ({current_soc:.0f}%)"
                elif current_price < 2 and current_soc >= 95:
                    immersion_lucy = True
                    immersion_lucy_reason = f"Very cheap price ({current_price:.1f}p) + Battery full ({current_soc:.0f}%)"
                elif solar_forecast[0] > 5.0 and current_soc >= 95:
                    immersion_lucy = True
                    immersion_lucy_reason = f"High solar ({solar_forecast[0]:.1f}kW) + Battery full ({current_soc:.0f}%)"
                else:
                    immersion_lucy_reason = f"Conditions not met (price: {current_price:.1f}p, SOC: {current_soc:.0f}%)"
            
            optimization_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            result = {
                "status": "optimal",
                "optimization_time_ms": optimization_time_ms,
                "objective_value": value(prob.objective),
                "current_recommendation": {
                    "mode": mode,
                    "discharge_current": discharge_current,
                    "charge_kw": current_action["charge_kw"],
                    "discharge_kw": current_action["discharge_kw"],
                    "expected_soc": current_action["soc"],
                    "immersion_main": immersion_main,
                    "immersion_lucy": immersion_lucy,
                    "immersion_main_source": immersion_main_source,
                    "immersion_lucy_source": immersion_lucy_source,
                    "immersion_main_reason": immersion_main_reason,
                    "immersion_lucy_reason": immersion_lucy_reason,
                    "schedule_override_active": schedule_override_active,
                    "manual_override_active": manual_override_active,
                    "reason": self._generate_reason(current_action, period_prices[0])
                },
                "schedule": schedule[:48],  # Return first 24 hours (48 periods)
                "next_action_time": datetime.now() + timedelta(minutes=30)
            }
            
            logger.info(f"Optimization complete in {optimization_time_ms:.1f}ms - {mode} at {discharge_current}A")
            
            return result
            
        except Exception as e:
            logger.error(f"Optimization failed: {e}", exc_info=True)
            return self._fallback_schedule(current_soc, prices[0]["price_pence"] if prices else 25)
    
    def _align_prices_to_periods(self, prices: List[Dict], num_periods: int) -> List[float]:
        """Convert price data to 30-minute period array"""
        period_prices = []
        now = datetime.now()
        
        for i in range(num_periods):
            period_start = now + timedelta(minutes=i * 30)
            
            # Find price for this period
            price = 25.0  # Default
            for p in prices:
                if isinstance(p["valid_from"], str):
                    valid_from = datetime.fromisoformat(p["valid_from"].replace('Z', '+00:00'))
                else:
                    valid_from = p["valid_from"]
                
                if isinstance(p["valid_to"], str):
                    valid_to = datetime.fromisoformat(p["valid_to"].replace('Z', '+00:00'))
                else:
                    valid_to = p["valid_to"]
                
                if valid_from <= period_start < valid_to:
                    price = p["price_pence"]
                    break
            
            period_prices.append(price)
        
        return period_prices
    
    def _align_solar_to_periods(self, solar_hourly: List[float], num_periods: int) -> List[float]:
        """Convert hourly solar forecast to 30-minute periods"""
        period_solar = []
        for i in range(num_periods):
            hour_index = i // 2
            if hour_index < len(solar_hourly):
                period_solar.append(solar_hourly[hour_index])
            else:
                period_solar.append(0.0)
        return period_solar
    
    def _align_load_to_periods(self, load_hourly: List[float], num_periods: int) -> List[float]:
        """Convert hourly load forecast to 30-minute periods"""
        period_load = []
        for i in range(num_periods):
            hour_index = i // 2
            if hour_index < len(load_hourly):
                period_load.append(load_hourly[hour_index])
            else:
                period_load.append(2.0)  # Default 2kW
        return period_load
    
    def _generate_reason(self, action: Dict, price: float) -> str:
        """Generate human-readable reason for recommendation"""
        if action["charge_kw"] > 0.5:
            if price < 0:
                return f"Negative pricing ({price:.1f}p) → Maximum charging"
            elif price < 10:
                return f"Cheap pricing ({price:.1f}p) → Opportunity charging"
            else:
                return f"Optimal to charge now ({price:.1f}p)"
        elif action["discharge_kw"] > 2.0:
            return f"Price is {price:.1f}p → Using battery to avoid grid import"
        else:
            return "Minimal battery use → Preserving for better opportunities"
    
    def _fallback_schedule(self, current_soc: float, current_price: float) -> Dict:
        """Simple fallback when optimization fails"""
        logger.warning("Using fallback heuristic schedule")
        
        # Simple rules
        if current_price < 0:
            mode = "Force Charge"
            discharge_current = 0
            reason = f"Negative price ({current_price:.1f}p) → Force charge"
        elif current_price < 10:
            mode = "Force Charge"
            discharge_current = 0
            reason = f"Cheap price ({current_price:.1f}p) → Charge"
        elif current_price > 25:
            mode = "Self Use"
            discharge_current = 50
            reason = f"Expensive price ({current_price:.1f}p) → Discharge"
        else:
            mode = "Self Use"
            discharge_current = 30
            reason = "Normal operation"
        
        return {
            "status": "fallback",
            "optimization_time_ms": 0,
            "objective_value": None,
            "current_recommendation": {
                "mode": mode,
                "discharge_current": discharge_current,
                "immersion_main": False,
                "immersion_lucy": False,
                "immersion_main_source": "optimizer",
                "immersion_lucy_source": "optimizer",
                "immersion_main_reason": "Fallback mode - no immersion control",
                "immersion_lucy_reason": "Fallback mode - no immersion control",
                "schedule_override_active": False,
                "reason": reason
            },
            "schedule": [],
            "next_action_time": datetime.now() + timedelta(minutes=5)
        }