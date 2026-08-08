from typing import Optional, Union
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
    role_id: Union[str, UUID, int]
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Office Schema
class OfficeBase(BaseModel):
    office_code: Optional[str] = None
    office_name: Optional[str] = None
    name: Optional[str] = None
    state: Optional[str] = "Rajasthan"

class OfficeCreate(OfficeBase):
    pass

class OfficeResponse(OfficeBase):
    office_id: Union[str, UUID, int]
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Headquarters Schema
class HeadquartersBase(BaseModel):
    name: str
    is_active: bool = True

class HeadquartersCreate(HeadquartersBase):
    pass

class HeadquartersResponse(HeadquartersBase):
    headquarters_id: Union[str, UUID, int]
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Circle Schema
class CircleBase(BaseModel):
    circle_code: Optional[str] = None
    circle_name: Optional[str] = None
    name: Optional[str] = None
    office_id: Optional[Union[str, UUID, int]] = None
    headquarters_id: Optional[Union[str, UUID, int]] = None

class CircleCreate(CircleBase):
    pass

class CircleResponse(CircleBase):
    circle_id: Union[str, UUID, int]
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Depot Schema
class DepotBase(BaseModel):
    name: str
    headquarters_id: Optional[Union[str, UUID, int]] = None
    office_id: Optional[Union[str, UUID, int]] = None
    circle_id: Optional[Union[str, UUID, int]] = None
    is_active: bool = True

class DepotCreate(DepotBase):
    pass

class DepotUpdate(BaseModel):
    name: Optional[str] = None
    headquarters_id: Optional[Union[str, UUID, int]] = None
    is_active: Optional[bool] = None
    assigned_user_id: Optional[str] = None

class DepotResponse(DepotBase):
    depot_id: Union[str, UUID, int]
    headquarters_name: Optional[str] = "Unassigned"
    assigned_user_id: Optional[str] = None
    depot_user: Optional[str] = "Unassigned"
    depot_user_email: Optional[str] = None
    hq_user: Optional[str] = "Unassigned"
    hq_user_email: Optional[str] = None
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Licensee Schema
class LicenseeBase(BaseModel):
    license_number: Optional[str] = None
    licensee_name: str
    depot_id: Optional[Union[str, UUID, int]] = None
    status: str = "active"

class LicenseeCreate(LicenseeBase):
    pass

class LicenseeResponse(LicenseeBase):
    licensee_id: Union[str, UUID, int]
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Packaging Category Schema
class PackagingCategoryBase(BaseModel):
    category_name: str
    description: Optional[str] = None

class PackagingCategoryCreate(PackagingCategoryBase):
    pass

class PackagingCategoryResponse(PackagingCategoryBase):
    packaging_category_id: Union[str, UUID, int]
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Brand Schema
class BrandBase(BaseModel):
    brand_code: Optional[str] = None
    brand_name: str
    company_id: Optional[Union[str, UUID, int]] = None
    packaging_category_id: Optional[Union[str, UUID, int]] = None
    is_trade: bool = True
    manufacturer: Optional[str] = None
    headquarters_id: Optional[Union[str, UUID, int]] = None
    is_active: bool = True

class BrandCreate(BrandBase):
    pass

class BrandResponse(BrandBase):
    brand_id: Union[str, UUID, int]
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Packing Size Schema
class PackingSizeBase(BaseModel):
    packing_name: str
    volume_ml: Optional[int] = 0
    bottles_per_case: Optional[int] = 1
    packaging_category_id: Optional[Union[str, UUID, int]] = None
    qpn: Optional[float] = None

class PackingSizeCreate(PackingSizeBase):
    pass

class PackingSizeResponse(PackingSizeBase):
    packing_size_id: Union[str, UUID, int]
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# User Schema
class UserBase(BaseModel):
    email: str
    first_name: str
    last_name: Optional[str] = None
    phone: Optional[str] = None
    role_id: Optional[Union[str, UUID, int]] = None
    office_id: Optional[Union[str, UUID, int]] = None
    circle_id: Optional[Union[str, UUID, int]] = None
    depot_id: Optional[Union[str, UUID, int]] = None
    manager_id: Optional[Union[str, UUID, int]] = None
    is_active: bool = True

class UserCreate(UserBase):
    user_id: Union[str, UUID]

class UserResponse(UserBase):
    user_id: Union[str, UUID]
    role_name: Optional[str] = None
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Representative Assignment Schema
class RepresentativeAssignmentBase(BaseModel):
    representative_user_id: Union[str, UUID]
    depot_id: Union[str, UUID, int]
    assigned_from: date
    assigned_to: Optional[date] = None
    is_active: bool = True

class RepresentativeAssignmentCreate(RepresentativeAssignmentBase):
    pass

class RepresentativeAssignmentResponse(RepresentativeAssignmentBase):
    assignment_id: Union[str, UUID, int]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
