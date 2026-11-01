def entity_id(prefix: str, number: int, width: int = 3) -> str:
    return f"{prefix}-{number:0{width}d}"

def simulation_id(number: int = 1) -> str:
    return f"SIM-2026-{number:06d}"
