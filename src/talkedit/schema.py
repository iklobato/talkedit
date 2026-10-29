from typing import Any


class StrictSchema:
    """JSON Schema pieces for OpenRouter strict structured outputs: every property is
    required and no extra keys are allowed."""

    def object(self, properties: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        }

    def array_of(self, properties: dict[str, Any]) -> dict[str, Any]:
        return {"type": "array", "items": self.object(properties)}
