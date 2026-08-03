from typing import Optional
from datetime import datetime, date
from uuid import UUID
from pydantic import BaseModel, ConfigDict

# Roles Schema
class RoleBase(BaseModel):
    role_name: str
    description: Optional[str] = None
    is_active: bool = True

class RoleCreate(RoleBase):
    pass

class RoleResponse(RoleBase):
    role_id: int
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Office Schema
class OfficeBase(BaseModel):
    office_code: str
    office_name: str
    state: Optional[str] = "Rajasthan"

class OfficeCreate(OfficeBase):
    pass

class OfficeResponse(OfficeBase):
    office_id: int
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Headquarters Schema
class HeadquartersBase(BaseModel):
    headquarters_name: str
    is_active: bool = True

class HeadquartersCreate(HeadquartersBase):
    pass

class HeadquartersResponse(HeadquartersBase):
    headquarters_id: int
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Circle Schema
class CircleBase(BaseModel):
    circle_code: str
    circle_name: str
    office_id: Optional[int] = None
    headquarters_id: Optional[int] = None

class CircleCreate(CircleBase):
    pass

class CircleResponse(CircleBase):
    circle_id: int
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Depot Schema
class DepotBase(BaseModel):
    circle_id: int
    depot_code: str
    depot_name: str
    address: Optional[str] = None

class DepotCreate(DepotBase):
    pass

class DepotResponse(DepotBase):
    depot_id: int
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Licensee Schema
class LicenseeBase(BaseModel):
    license_number: str
    licensee_name: str
    depot_id: int
    status: str = "active"

class LicenseeCreate(LicenseeBase):
    pass

class LicenseeResponse(LicenseeBase):
    licensee_id: int
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Packaging Category Schema
class PackagingCategoryBase(BaseModel):
    category_name: str
    description: Optional[str] = None

class PackagingCategoryCreate(PackagingCategoryBase):
    pass

class PackagingCategoryResponse(PackagingCategoryBase):
    packaging_category_id: int
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Brand Schema
class BrandBase(BaseModel):
    brand_code: str
    brand_name: str
    packaging_category_id: int
    is_trade: bool = True
    manufacturer: Optional[str] = None
    headquarters_id: Optional[int] = None
    is_active: bool = True

class BrandCreate(BrandBase):
    pass

class BrandResponse(BrandBase):
    brand_id: int
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Packing Size Schema
class PackingSizeBase(BaseModel):
    packing_name: str
    volume_ml: int
    bottles_per_case: int
    packaging_category_id: int
    qpn: Optional[float] = None

class PackingSizeCreate(PackingSizeBase):
    pass

class PackingSizeResponse(PackingSizeBase):
    packing_size_id: int
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# User Schema
class UserBase(BaseModel):
    email: str
    first_name: str
    last_name: Optional[str] = None
    phone: Optional[str] = None
    role_id: int
    office_id: Optional[int] = None
    circle_id: Optional[int] = None
    depot_id: Optional[int] = None
    manager_id: Optional[UUID] = None
    is_active: bool = True

class UserCreate(UserBase):
    user_id: UUID

class UserResponse(UserBase):
    user_id: UUID
    role_name: Optional[str] = None
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Representative Assignment Schema
class RepresentativeAssignmentBase(BaseModel):
    representative_user_id: UUID
    depot_id: int
    assigned_from: date
    assigned_to: Optional[date] = None
    is_active: bool = True

class RepresentativeAssignmentCreate(RepresentativeAssignmentBase):
    pass

class RepresentativeAssignmentResponse(RepresentativeAssignmentBase):
    assignment_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
