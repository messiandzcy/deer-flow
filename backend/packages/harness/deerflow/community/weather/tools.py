"""Weather Tool - Get current weather using wttr.in (no API key required)."""
import json
import logging

import httpx
from langchain.tools import tool

logger = logging.getLogger(__name__)

_WTTR_ENDPOINT = "https://wttr.in"


@tool("get_weather", parse_docstring=True)
def get_weather_tool(city: str) -> str:
    """Get current weather for a city using wttr.in.

    Args:
        city: City name (e.g., 'Beijing', 'London', 'Tokyo'). Supports Chinese city names.
    """
    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(f"{_WTTR_ENDPOINT}/{city}", params={"format": "j1"})
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"wttr.in returned HTTP {e.response.status_code}")
        return json.dumps({"error": f"Weather service error: HTTP {e.response.status_code}", "city": city}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Weather request failed: {type(e).__name__}: {e}")
        return json.dumps({"error": str(e), "city": city}, ensure_ascii=False)

    current = data.get("current_condition", [])
    if not current:
        return json.dumps({"error": f"No weather data found for '{city}'", "city": city}, ensure_ascii=False)

    c = current[0]
    result = {
        "city": city,
        "temperature": f"{c.get('temp_C', '?')}°C",
        "feels_like": f"{c.get('FeelsLikeC', '?')}°C",
        "humidity": f"{c.get('humidity', '?')}%",
        "wind": f"{c.get('windspeedKmph', '?')} km/h {c.get('winddir16Point', '?')}",
        "condition": c.get("weatherDesc", [{}])[0].get("value", "Unknown"),
        "visibility": f"{c.get('visibility', '?')} km",
    }

    return json.dumps(result, indent=2, ensure_ascii=False)
