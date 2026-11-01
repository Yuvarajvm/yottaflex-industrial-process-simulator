from dataclasses import dataclass, replace
import math

DEFAULT_SEED = 20261022

@dataclass(frozen=True)
class Config:
    seed: int = DEFAULT_SEED
    profile: str = "starter"
    scenario: str = "all"
    run_number: int = 1
    telemetry_count: int = 7000
    facilities: int = 3
    pumps: int = 20
    tanks: int = 30
    valves: int = 60
    pipes: int = 60
    # Number of one-minute steps required to emit telemetry_count readings.
    # This is derived from the deterministic sensor inventory, never an input knob.
    steps: int | None = None

    @property
    def sensor_count(self) -> int:
        # Two measurements per pipe plus one redundant flow pickup on each of
        # the two controlled sensor-fault pipes, one per tank and one per pump.
        return 2 * self.pipes + 2 + self.tanks + self.pumps

    @property
    def actual_steps(self) -> int:
        if self.telemetry_count <= 0 or self.sensor_count <= 0:
            raise ValueError("telemetry_count and generated sensor count must be positive")
        return math.ceil(self.telemetry_count / self.sensor_count)

    @classmethod
    def for_profile(cls, profile: str, seed: int = DEFAULT_SEED, telemetry_count: int | None = None, scenario: str = "all"):
        if profile not in {"starter", "full"}:
            raise ValueError("profile must be starter or full")
        if scenario not in {"all", "normal"}: raise ValueError("scenario must be all or normal")
        cfg=cls(seed=seed, profile=profile, scenario=scenario, telemetry_count=(telemetry_count if telemetry_count is not None else (100_000 if profile == "full" else 7_000)))
        return replace(cfg,steps=cfg.actual_steps)
