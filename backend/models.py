from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from enum import Enum

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class ItemStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    FOUND = "found"
    NOT_FOUND = "not_found"
    ERROR = "error"

class SupplierStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"

# Response Models (no _id)
class Supplier(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str
    name: str
    url_login: str
    url_search: str
    username: str
    password: str  # Will be hashed
    selectors: Optional[Dict[str, str]] = None
    is_active: bool = True
    status: SupplierStatus = SupplierStatus.ACTIVE
    last_test: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SupplierCreate(BaseModel):
    name: str
    url_login: str
    url_search: str
    username: str
    password: str
    selectors: Optional[Dict[str, str]] = None

class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    url_login: Optional[str] = None
    url_search: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    selectors: Optional[Dict[str, str]] = None
    is_active: Optional[bool] = None

class Job(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str
    filename: str
    status: JobStatus = JobStatus.PENDING
    total_items: int
    processed_items: int = 0
    found_items: int = 0
    total_savings: float = 0.0
    threshold_euro: float
    threshold_percent: float
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

class JobCreate(BaseModel):
    filename: str
    total_items: int
    threshold_euro: float = 5.0
    threshold_percent: float = 10.0

class JobItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str
    job_id: str
    ref_id: str
    medida: str
    marca: str
    modelo: str
    indice: str
    meu_preco: float
    melhor_preco: Optional[float] = None
    melhor_fornecedor: Optional[str] = None
    economia_euro: Optional[float] = None
    economia_percent: Optional[float] = None
    status: ItemStatus = ItemStatus.PENDING
    supplier_prices: Dict[str, Any] = {}  # {supplier_id: price or status}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Price(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str
    job_id: str
    item_id: str
    supplier_id: str
    supplier_name: str
    price: Optional[float] = None
    status: ItemStatus
    found_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Log(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str
    job_id: Optional[str] = None
    supplier_id: Optional[str] = None
    level: str  # INFO, WARNING, ERROR
    message: str
    screenshot_path: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class TestLoginResponse(BaseModel):
    success: bool
    message: str
    screenshot_path: Optional[str] = None

class JobProgress(BaseModel):
    job_id: str
    status: JobStatus
    total_items: int
    processed_items: int
    found_items: int
    progress_percent: float
    current_supplier: Optional[str] = None
