from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import time, date
import re

class TimeWindow(BaseModel):
    time: str = Field(..., regex=r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$', description="Time in HH:MM format")
    message: Optional[str] = Field(None, max_length=100)

class ConstantScheduleCreate(BaseModel):
    work_start: str = Field(..., regex=r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$')
    work_end: str = Field(..., regex=r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$')
    sleep_start: Optional[str] = Field(None, regex=r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$')
    sleep_end: Optional[str] = Field(None, regex=r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$')
    shift_type: Optional[str] = Field('day', regex=r'^(day|evening|night)$')
    coffee_windows: Optional[List[TimeWindow]] = Field(default_factory=list, max_items=5)
    meal_windows: Optional[List[TimeWindow]] = Field(default_factory=list, max_items=3)
    brightness_windows: Optional[List[TimeWindow]] = Field(default_factory=list, max_items=10)
    
    @validator('sleep_end')
    def validate_sleep_pair(cls, v, values):
        if 'sleep_start' in values and values['sleep_start'] is not None and v is None:
            raise ValueError('sleep_end is required when sleep_start is provided')
        return v
    
    @validator('work_end')
    def validate_work_hours(cls, v, values):
        if 'work_start' in values:
            start = values['work_start']
            if start == v:
                raise ValueError('work_start and work_end cannot be the same')
        return v

class RotatingPatternCreate(BaseModel):
    pattern_name: str = Field(..., min_length=1, max_length=50)
    cycle_days: int = Field(..., ge=1, le=365)
    pattern_start_date: date
    shifts: List[Dict[str, Any]] = Field(..., min_items=1, max_items=30)
    
    @validator('shifts')
    def validate_shifts(cls, v):
        for i, shift in enumerate(v):
            if 'day_number' not in shift or 'shift_type' not in shift:
                raise ValueError(f'Shift {i} missing required fields')
            if shift['shift_type'] not in ['day', 'evening', 'night', 'off']:
                raise ValueError(f'Invalid shift_type in shift {i}')
        return v

class DailyScheduleUpdate(BaseModel):
    date: date
    shift_type: str = Field(..., regex=r'^(day|evening|night|off)$')
    work_start: Optional[str] = Field(None, regex=r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$')
    work_end: Optional[str] = Field(None, regex=r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$')

class UserUpdate(BaseModel):
    timezone: Optional[str] = Field(None, regex=r'^[A-Za-z_]+/[A-Za-z_]+$')
    notification_enabled: Optional[bool] = None
    notification_prefs: Optional[Dict[str, bool]] = None

class CoffeeCheckRequest(BaseModel):
    current_time: Optional[str] = Field(None, regex=r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$')

class DayOffRequest(BaseModel):
    date: Optional[date] = None
    reason: Optional[str] = Field(None, max_length=200)

class WeeklySummaryRequest(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    
    @validator('end_date')
    def validate_date_range(cls, v, values):
        if v and 'start_date' in values and values['start_date']:
            if v < values['start_date']:
                raise ValueError('end_date must be after start_date')
        return v
