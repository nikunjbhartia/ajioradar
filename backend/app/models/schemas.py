from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class VerifiedCampaign(BaseModel):
    curated_id: str
    code: str
    title: str
    description: str
    details_url: str
    promo_type: Optional[str] = "Flash / Curated Coupon"
    department: Optional[str] = "Multi-Category"
    brands: Optional[str] = ""
    brand_list: List[str] = Field(default_factory=list)
    min_realized_discount: float = 0.0
    max_realized_discount: float = 0.0
    min_price: float = 0.0
    max_price: float = 0.0
    min_base_needed: float = 0.0
    applied_filter_tier: Optional[str] = "50% and above"
    has_70_plus_verified: bool = True
    is_standalone_deal: bool = False
    total_verified_skus: int = 0
    scanned_at: Optional[str] = None

class VerifiedProductDeal(BaseModel):
    id: str
    name: str
    brand: str
    category: str
    department: Optional[str] = "Multi-Category"
    mrp: float
    selling_price: float
    final_price: float
    base_discount_percent: float
    net_discount_percent: float
    formula_desc: Optional[str] = ""
    coupon_code: str
    product_url: str
    image_url: Optional[str] = ""
    scanned_at: Optional[str] = None

class SyncHistoryItem(BaseModel):
    sync_id: str
    timestamp: float
    formatted_time: str
    duration_seconds: float
    added_coupons: List[str] = Field(default_factory=list)
    updated_coupons: List[str] = Field(default_factory=list)
    removed_coupons: List[str] = Field(default_factory=list)
    added_count: int = 0
    updated_count: int = 0
    removed_count: int = 0
    active_70_count: int = 0
    total_campaigns: int = 0
    active_codes_count: int = 0
    total_codes_count: int = 0
    total_deals: int = 0
    active_coupons: List[str] = Field(default_factory=list)
    department_breakdown: Dict[str, int] = Field(default_factory=dict)
    highlights: List[str] = Field(default_factory=list)
    changes: List[Dict[str, Any]] = Field(default_factory=list)

class SyncStatusReport(BaseModel):
    is_active: bool
    verified_70_plus_campaigns: int
    total_campaigns: int
    verified_70_plus_products: int
    verified_70_plus_codes: Optional[int] = 0
    total_codes: Optional[int] = 0
    last_sync_timestamp: float
    seconds_since_last_sync: float
    last_sync_duration_seconds: float
    total_brands_indexed: int
    total_departments_indexed: int
    poll_interval_seconds: int
    safe_pacing_minutes: float
    latest_delta: Optional[SyncHistoryItem] = None
