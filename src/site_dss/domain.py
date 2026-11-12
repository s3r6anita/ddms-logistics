from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from shapely.geometry import shape

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, validate_default=True)

class Evidence(Contract):
    source_id: str
    source_kind: Literal['observed','document','expert','synthetic','derived']
    observed_at: date
    valid_until: date
    unit: str
    quality_status: Literal['confirmed','unknown','rejected']
    evidence_uri: str
    confirmed_by: str | None = None
    @model_validator(mode='after')
    def dates(self):
        if self.valid_until < self.observed_at: raise ValueError('invalid evidence validity')
        return self

class Site(Contract):
    site_id: str
    name: str
    geometry: dict
    crs: Literal['EPSG:4326'] = 'EPSG:4326'
    legal_status: Literal['confirmed','rejected','unknown']
    project_id: str
    evidence_ids: list[str]
    capex_rub: float = Field(ge=0)
    launch_months: float = Field(gt=0)
    expandable_fraction: float | None = Field(default=None, ge=0)
    access_confirmed: bool | None
    utilities_sufficient: bool | None
    prohibiting_condition: bool | None
    power_available_kw: float | None = Field(default=None, ge=0)
    document_area_m2: float = Field(gt=0)
    @model_validator(mode='after')
    def polygon(self):
        g=shape(self.geometry)
        if g.geom_type != 'Polygon' or g.is_empty or not g.is_valid: raise ValueError('invalid polygon')
        if not (-180<=g.bounds[0]<=g.bounds[2]<=180 and -90<=g.bounds[1]<=g.bounds[3]<=90): raise ValueError('coordinates out of range')
        return self

class WarehouseDesign(Contract):
    project_id: str
    storage_pallets: float = Field(gt=0)
    throughput_pallets_month: list[float] = Field(min_length=12,max_length=12)
    power_required_kw: float = Field(gt=0)
    @model_validator(mode='after')
    def positive(self):
        if min(self.throughput_pallets_month)<=0: raise ValueError('invalid capacity')
        return self

class DemandObservation(Contract):
    zone_id: str
    month: date
    ordered_pallets: float = Field(ge=0)
    shipped_pallets: float = Field(ge=0)
    unfulfilled_pallets: float = Field(ge=0)
    evidence_id: str
    unit: Literal['pallet'] = 'pallet'
    @model_validator(mode='after')
    def balance(self):
        if self.month.day!=1: raise ValueError('month must be first day')
        if abs(self.ordered_pallets-self.shipped_pallets-self.unfulfilled_pallets)>1e-6: raise ValueError('demand balance')
        return self

class RouteFact(Contract):
    site_id: str
    zone_id: str
    period: Literal['peak','offpeak']
    vehicle_profile: Literal['truck_20t']
    reachable: bool | None
    minutes: float | None = Field(ge=0)
    km: float | None = Field(ge=0)
    variable_cost_rub_pallet: float | None = Field(ge=0)
    evidence_id: str
    @model_validator(mode='after')
    def known_route(self):
        if self.reachable is True and any(v is None for v in [self.minutes,self.km,self.variable_cost_rub_pallet]): raise ValueError('reachable route lacks metrics')
        return self

class CostItem(Contract):
    site_id: str
    category: str
    cashflow_date: date
    amount: float = Field(ge=0)
    currency: Literal['RUB']
    price_date: date
    vat_policy: Literal['excluded','included']
    real_or_nominal: Literal['real','nominal']
    scenario_id: str
    evidence_id: str

class Snapshot(Contract):
    schema_version: Literal['1.0']
    as_of: date
    synthetic: bool
    evidence: list[Evidence]
    designs: list[WarehouseDesign]
    sites: list[Site]
    zones: list[str]
    demand: list[DemandObservation]
    routes: list[RouteFact]
    costs: list[CostItem]

class ForecastPoint(Contract):
    model_id: str
    zone_id: str
    origin: date
    target_month: date
    point: float = Field(ge=0)
    p10: float = Field(ge=0)
    p90: float = Field(ge=0)
    p025: float = Field(ge=0)
    p975: float = Field(ge=0)
    training_cutoff: date
    data_hash: str
    @model_validator(mode='after')
    def ordered(self):
        if not self.p025<=self.p10<=self.point<=self.p90<=self.p975: raise ValueError('interval ordering')
        if self.target_month<=self.training_cutoff: raise ValueError('forecast must follow cutoff')
        return self

class Scenario(Contract):
    scenario_id: str
    probability: float = Field(ge=0,le=1)
    kind: Literal['synthetic']
    demand_paths: dict[str,list[float]]
    demand_growth_factors: list[float]
    tariff_factors: list[float]
    capex_factors: list[float]
    route_state: Literal['normal','restricted']
    connection_delay: int = Field(ge=0)
    seed: int
    @model_validator(mode='after')
    def paths(self):
        if not self.demand_paths or any(len(x)!=12 or min(x)<0 for x in self.demand_paths.values()): raise ValueError('invalid demand path')
        if len(self.demand_growth_factors)!=5 or min(self.demand_growth_factors)<=0: raise ValueError('invalid demand growth factors')
        if len(self.tariff_factors)!=5 or len(self.capex_factors)!=5 or min(self.tariff_factors+self.capex_factors)<=0: raise ValueError('invalid five year factors')
        return self

class DecisionRequest(Contract):
    budget_rub: float = Field(default=900e6, gt=0)
    max_launch_months: float = Field(default=18, gt=0)
    sla_target: float = Field(default=.9,ge=0,le=1)
    max_delivery_minutes: float = Field(default=120,gt=0)
    alpha: float = Field(default=.9,gt=0,le=1)
    risk_policy: Literal['point','wilson_lower'] = 'wilson_lower'
    demand_scale: float = Field(default=1,gt=0,le=5)
    horizon_years: Literal[5] = 5
    discount_rate: float = Field(default=.1,ge=0,le=1)
    planning_scenarios: int = Field(default=100,ge=1,le=1000)
    validation_scenarios: int = Field(default=1000,ge=100,le=5000)
    seed: int = 20261112
    comparisons: list[float] = Field(default_factory=lambda:[4/3,2,4,1.5,3,2],min_length=6,max_length=6)
    allow_demo: bool = False
    transport_backend: Literal['hybrid','cbc'] = 'hybrid'
    solver_time_limit: float = Field(default=10,gt=0,le=120)

class SiteFinance(Contract):
    fixed_opex_rub_year: float = Field(ge=0)
    dwell_days: float = Field(gt=0)
    unserved_loss_rub_pallet: float = Field(gt=0)
    waiting_cost_rub_month: float = Field(ge=0)
    residual_value_rub: float = Field(ge=0)

class FinanceConfig(Contract):
    synthetic: bool
    source_id: str
    price_date: date
    currency: Literal['RUB']
    prices: Literal['real']
    vat_policy: Literal['excluded']
    sites: dict[str,SiteFinance]

class SiteResult(Contract):
    site_id: str
    status: str
    knowledge: dict
    planning: dict | None = None
    validation: dict | None = None
    utilities: list[float] | None = None
    score: float | None = None
    diagnostics: list[str] = Field(default_factory=list)
    solver_status: str = 'NOT_RUN'

class DecisionRun(Contract):
    run_id: str
    created_at: str
    version: str
    synthetic: bool
    request: DecisionRequest
    provenance: dict
    forecast: dict
    sites: list[SiteResult]
    recommendation: str | None
    alternatives: list[str]
    explanation: dict
    sensitivity: list[dict]
    stresses: list[dict]
    scenario_metrics: list[dict]
    decision_tree: dict
    elapsed_seconds: float
