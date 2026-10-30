"""Configuration shared by the collector, API and simulator.

Loaded from a YAML file (``CW_CONFIG``, default ``config.yaml``) with a few
environment overrides so containers can inject deployment specifics.
"""

from __future__ import annotations

import os
from datetime import time
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

MachineMode = Literal["serial+modbus", "serial", "modbus"]


class PlantConfig(BaseModel):
    name: str = "Plant"
    timezone: str = "Asia/Kolkata"

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, v: str) -> str:
        ZoneInfo(v)
        return v

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


class DatabaseConfig(BaseModel):
    url: str = "postgresql://cw:cw@localhost:5433/checkweigher"


class SerialConfig(BaseModel):
    # Anything pyserial's serial_for_url accepts: /dev/ttyUSB0, COM3,
    # /dev/serial/by-path/..., socket://host:port (simulator / serial-ethernet adapter)
    url: str
    baudrate: int = 9600
    bytesize: Literal[7, 8] = 8
    parity: Literal["N", "E", "O"] = "N"
    stopbits: Literal[1, 2] = 1


class ModbusConfig(BaseModel):
    host: str
    port: int = 502
    device_id: int = 1
    timeout_s: float = 2.0
    context_interval_s: float = 5.0
    reconcile_interval_s: float = 30.0
    poll_interval_s: float = 0.2
    # Manual §10.3.1 example returns 1000 as [0x03E8, 0x0000] -> low word first.
    word_order: Literal["little", "big"] = "little"
    # Manual does not state how 4-byte decimal values are encoded; assume an
    # integer scaled by the product decimal point (holding register 619).
    value_encoding: Literal["scaled_int", "float32"] = "scaled_int"


class MachineConfig(BaseModel):
    id: int = Field(ge=1, le=32767)
    code: str
    name: str
    mode: MachineMode = "serial+modbus"
    # Weighing unit configured on the indicator; used for Modbus-read values.
    # Serial lines carry their own unit.
    unit: Literal["g", "kg"] = "g"
    serial: SerialConfig | None = None
    modbus: ModbusConfig | None = None

    @model_validator(mode="after")
    def _check_mode(self) -> MachineConfig:
        if "serial" in self.mode and self.serial is None:
            raise ValueError(f"machine {self.code}: mode {self.mode} requires a serial section")
        if "modbus" in self.mode and self.modbus is None:
            raise ValueError(f"machine {self.code}: mode {self.mode} requires a modbus section")
        return self

    @property
    def uses_serial(self) -> bool:
        return "serial" in self.mode

    @property
    def uses_modbus(self) -> bool:
        return "modbus" in self.mode


class ShiftConfig(BaseModel):
    code: str
    name: str
    start: time
    end: time


class CollectorConfig(BaseModel):
    spool_dir: str = "var/spool"
    status_interval_s: float = 2.0
    batch_size: int = 200
    flush_interval_s: float = 0.5


class ApiConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    web_dist: str | None = None


class AppConfig(BaseModel):
    plant: PlantConfig = PlantConfig()
    database: DatabaseConfig = DatabaseConfig()
    collector: CollectorConfig = CollectorConfig()
    api: ApiConfig = ApiConfig()
    machines: list[MachineConfig] = []
    # Optional: when present the collector syncs these into the `shift` table on start.
    shifts: list[ShiftConfig] | None = None

    @model_validator(mode="after")
    def _unique_machines(self) -> AppConfig:
        ids = [m.id for m in self.machines]
        codes = [m.code for m in self.machines]
        if len(set(ids)) != len(ids) or len(set(codes)) != len(codes):
            raise ValueError("machine ids and codes must be unique")
        return self


def load_config(path: str | os.PathLike[str] | None = None) -> AppConfig:
    path = Path(path or os.environ.get("CW_CONFIG", "config.yaml"))
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    cfg = AppConfig.model_validate(data or {})
    if url := os.environ.get("CW_DATABASE_URL"):
        cfg.database.url = url
    if web_dist := os.environ.get("CW_WEB_DIST"):
        cfg.api.web_dist = web_dist
    return cfg
