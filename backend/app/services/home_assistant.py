"""
Home Assistant API Client
"""
import logging
from typing import Dict, Any, Optional
import httpx
from datetime import datetime

from app.config import settings

logger = logging.getLogger(__name__)


class HomeAssistantClient:
    """Client for interacting with Home Assistant API"""
    
    def __init__(self):
        self.base_url = settings.ha_url
        self.token = settings.ha_token
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        self.timeout = 10.0
    
    async def get_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current state of an entity
        
        Args:
            entity_id: The entity ID to query
            
        Returns:
            Entity state dict or None if error
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/states/{entity_id}",
                    headers=self.headers
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to get state for {entity_id}: {e}")
            return None
    
    async def get_states(self, entity_ids: list[str]) -> Dict[str, Optional[Dict]]:
        """
        Get states for multiple entities efficiently
        
        Args:
            entity_ids: List of entity IDs
            
        Returns:
            Dict mapping entity_id to state
        """
        states = {}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Get all states at once
                response = await client.get(
                    f"{self.base_url}/api/states",
                    headers=self.headers
                )
                response.raise_for_status()
                all_states = response.json()
                
                # Filter to requested entities
                state_map = {s["entity_id"]: s for s in all_states}
                for entity_id in entity_ids:
                    states[entity_id] = state_map.get(entity_id)
        
        except Exception as e:
            logger.error(f"Failed to get states: {e}")
            # Return partial results
            for entity_id in entity_ids:
                if entity_id not in states:
                    states[entity_id] = None
        
        return states
    
    async def call_service(
        self,
        domain: str,
        service: str,
        entity_id: str,
        data: Optional[Dict] = None
    ) -> bool:
        """
        Call a Home Assistant service
        
        Args:
            domain: Service domain (e.g., 'switch', 'select')
            service: Service name (e.g., 'turn_on', 'select_option')
            entity_id: Target entity
            data: Additional service data
            
        Returns:
            True if successful
        """
        try:
            service_data = {"entity_id": entity_id}
            if data:
                service_data.update(data)
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/services/{domain}/{service}",
                    headers=self.headers,
                    json=service_data
                )
                response.raise_for_status()
                logger.info(f"Called {domain}.{service} on {entity_id}")
                return True
        
        except Exception as e:
            logger.error(f"Failed to call service {domain}.{service}: {e}")
            return False
    
    async def set_battery_mode(self, mode: str) -> bool:
        """Set battery work mode"""
        return await self.call_service(
            "select",
            "select_option",
            settings.ha_entity_battery_mode,
            {"option": mode}
        )
    
    async def set_discharge_current(self, current: int) -> bool:
        """Set battery discharge current"""
        return await self.call_service(
            "number",
            "set_value",
            settings.ha_entity_discharge_current,
            {"value": current}
        )
    
    async def set_immersion_switch(self, entity_id: str, state: bool) -> bool:
        """Turn immersion switch on or off"""
        service = "turn_on" if state else "turn_off"
        return await self.call_service("switch", service, entity_id)
    
    async def get_battery_soc(self) -> Optional[float]:
        """Get current battery state of charge"""
        state = await self.get_state(settings.ha_entity_battery_soc)
        if state:
            try:
                return float(state["state"])
            except (ValueError, KeyError):
                return None
        return None
    
    async def get_solar_power(self) -> Optional[float]:
        """Get current solar power generation"""
        state = await self.get_state(settings.ha_entity_solar_power)
        if state:
            try:
                return float(state["state"])
            except (ValueError, KeyError):
                return None
        return None
    
    async def get_system_state(self) -> Dict[str, Any]:
        """
        Get complete system state
        
        Returns:
            Dict with all sensor values
        """
        entity_ids = [
            settings.ha_entity_battery_soc,
            settings.ha_entity_solar_power,
            settings.ha_entity_solar_forecast_today,
            settings.ha_entity_solar_forecast_next_hour,
            settings.ha_entity_battery_mode,
            settings.ha_entity_discharge_current,
            settings.ha_entity_immersion_main,
            settings.ha_entity_immersion_lucy
        ]
        
        states = await self.get_states(entity_ids)
        
        def safe_float(val: Optional[Dict], default: float = 0.0) -> float:
            if val and "state" in val:
                try:
                    return float(val["state"])
                except (ValueError, TypeError):
                    return default
            return default
        
        def safe_str(val: Optional[Dict], default: str = "") -> str:
            if val and "state" in val:
                return str(val["state"])
            return default
        
        def safe_bool(val: Optional[Dict], default: bool = False) -> bool:
            if val and "state" in val:
                state = str(val["state"]).lower()
                return state in ("on", "true", "1")
            return default
        
        return {
            "battery_soc": safe_float(states[settings.ha_entity_battery_soc]),
            "solar_power_kw": safe_float(states[settings.ha_entity_solar_power]),
            "solar_forecast_today_kwh": safe_float(states[settings.ha_entity_solar_forecast_today]),
            "solar_forecast_next_hour_kw": safe_float(states[settings.ha_entity_solar_forecast_next_hour]) / 1000,
            "battery_mode": safe_str(states[settings.ha_entity_battery_mode]),
            "discharge_current": int(safe_float(states[settings.ha_entity_discharge_current])),
            "immersion_main_on": safe_bool(states[settings.ha_entity_immersion_main]),
            "immersion_lucy_on": safe_bool(states[settings.ha_entity_immersion_lucy]),
            "timestamp": datetime.now().isoformat()
        }