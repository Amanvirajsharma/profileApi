from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, ForeignKey, TIMESTAMP, CheckConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.sql import func
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime
import os

# ============= DATABASE SETUP =============

# Database URL - CHANGE THESE VALUES
DATABASE_URL = "postgresql://postgres:Aman2506@localhost:5433/profile_db"
# Format: postgresql://username:password@host:port/database_name

# Create engine
engine = create_engine(DATABASE_URL)

# Create session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class
Base = declarative_base()


# ============= DATABASE MODELS =============

class User(Base):
    __tablename__ = "users"
    
    user_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    bio = Column(Text, nullable=True)
    location = Column(String(255), nullable=True)
    score = Column(Float, default=0.0)
    test_count = Column(Integer, default=0)
    phone_no = Column(String(20), nullable=True)
    user_type = Column(String(20), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    # Relationship
    education = relationship("Education", back_populates="user", cascade="all, delete-orphan")
    
    __table_args__ = (
        CheckConstraint('score >= 0 AND score <= 100', name='check_score_range'),
        CheckConstraint('test_count >= 0', name='check_test_count'),
        CheckConstraint("user_type IN ('student', 'professor', 'teacher')", name='check_user_type'),
    )


class Education(Base):
    __tablename__ = "education"
    
    education_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"))
    degree = Column(String(255), nullable=False)
    institution = Column(String(255), nullable=False)
    year = Column(Integer, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    # Relationship
    user = relationship("User", back_populates="education")


# Create tables
Base.metadata.create_all(bind=engine)


# ============= PYDANTIC SCHEMAS =============

# Enums
class UserType(str, Enum):
    STUDENT = "student"
    PROFESSOR = "professor"
    TEACHER = "teacher"


# Education Schemas
class EducationBase(BaseModel):
    degree: str = Field(..., example="Bachelor of Science")
    institution: str = Field(..., example="MIT")
    year: int = Field(..., example=2023)


class EducationCreate(EducationBase):
    pass


class EducationResponse(EducationBase):
    education_id: int
    user_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


# User Schemas
class UserProfileBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, example="John Doe")
    email: EmailStr = Field(..., example="john@example.com")
    bio: Optional[str] = Field(None, max_length=500, example="A passionate learner")
    location: Optional[str] = Field(None, example="New York, USA")
    score: float = Field(default=0.0, ge=0, le=100, example=85.5)
    test_count: int = Field(default=0, ge=0, example=5)
    phone_no: Optional[str] = Field(None, example="+1234567890")
    user_type: UserType = Field(..., example="student")


class UserProfileCreate(UserProfileBase):
    education: Optional[EducationCreate] = None


class UserProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    email: Optional[EmailStr] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    score: Optional[float] = Field(None, ge=0, le=100)
    test_count: Optional[int] = Field(None, ge=0)
    phone_no: Optional[str] = None
    user_type: Optional[UserType] = None
    education: Optional[EducationCreate] = None


class UserProfileResponse(UserProfileBase):
    user_id: int
    created_at: datetime
    updated_at: datetime
    education: List[EducationResponse] = []
    
    class Config:
        from_attributes = True


# ============= DATABASE DEPENDENCY =============

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============= CRUD OPERATIONS =============

def create_user_db(db: Session, user_data: UserProfileCreate):
    # Check if email exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create user
    db_user = User(
        name=user_data.name,
        email=user_data.email,
        bio=user_data.bio,
        location=user_data.location,
        score=user_data.score,
        test_count=user_data.test_count,
        phone_no=user_data.phone_no,
        user_type=user_data.user_type.value
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # Add education if provided
    if user_data.education:
        db_education = Education(
            user_id=db_user.user_id,
            degree=user_data.education.degree,
            institution=user_data.education.institution,
            year=user_data.education.year
        )
        db.add(db_education)
        db.commit()
        db.refresh(db_user)
    
    return db_user


def get_users_db(db: Session, user_type: str = None, skip: int = 0, limit: int = 100):
    query = db.query(User)
    if user_type:
        query = query.filter(User.user_type == user_type)
    return query.offset(skip).limit(limit).all()


def get_user_db(db: Session, user_id: int):
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def update_user_db(db: Session, user_id: int, user_data: UserProfileUpdate):
    db_user = get_user_db(db, user_id)
    
    update_data = user_data.model_dump(exclude_unset=True, exclude={'education'})
    
    for key, value in update_data.items():
        if key == 'user_type' and value:
            setattr(db_user, key, value.value)
        else:
            setattr(db_user, key, value)
    
    # Update education
    if user_data.education:
        # Delete old education
        db.query(Education).filter(Education.user_id == user_id).delete()
        # Add new education
        db_education = Education(
            user_id=user_id,
            degree=user_data.education.degree,
            institution=user_data.education.institution,
            year=user_data.education.year
        )
        db.add(db_education)
    
    db.commit()
    db.refresh(db_user)
    return db_user


def delete_user_db(db: Session, user_id: int):
    db_user = get_user_db(db, user_id)
    db.delete(db_user)
    db.commit()


def increment_test_db(db: Session, user_id: int):
    db_user = get_user_db(db, user_id)
    db_user.test_count += 1
    db.commit()
    db.refresh(db_user)
    return db_user


def update_score_db(db: Session, user_id: int, new_score: float):
    if new_score < 0 or new_score > 100:
        raise HTTPException(status_code=400, detail="Score must be between 0 and 100")
    
    db_user = get_user_db(db, user_id)
    db_user.score = new_score
    db.commit()
    db.refresh(db_user)
    return db_user


# ============= FASTAPI APP =============

app = FastAPI(
    title="Profile API with PostgreSQL",
    description="Complete profile management system",
    version="2.0.0"
)


# ============= API ENDPOINTS =============

@app.get("/")
def root():
    return {
        "message": "Welcome to Profile API with PostgreSQL",
        "docs": "/docs",
        "database": "PostgreSQL"
    }


@app.post("/profiles/", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED)
def create_profile(user: UserProfileCreate, db: Session = Depends(get_db)):
    """Create a new user profile"""
    return create_user_db(db, user)


@app.get("/profiles/", response_model=List[UserProfileResponse])
def get_all_profiles(
    user_type: UserType = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get all profiles with optional filtering"""
    return get_users_db(db, user_type=user_type.value if user_type else None, skip=skip, limit=limit)


@app.get("/profiles/{user_id}", response_model=UserProfileResponse)
def get_profile(user_id: int, db: Session = Depends(get_db)):
    """Get a specific profile"""
    return get_user_db(db, user_id)


@app.put("/profiles/{user_id}", response_model=UserProfileResponse)
def update_profile(user_id: int, user: UserProfileUpdate, db: Session = Depends(get_db)):
    """Update a profile"""
    return update_user_db(db, user_id, user)


@app.delete("/profiles/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(user_id: int, db: Session = Depends(get_db)):
    """Delete a profile"""
    delete_user_db(db, user_id)
    return None


@app.patch("/profiles/{user_id}/increment-test", response_model=UserProfileResponse)
def increment_test_count(user_id: int, db: Session = Depends(get_db)):
    """Increment test count"""
    return increment_test_db(db, user_id)


@app.patch("/profiles/{user_id}/update-score", response_model=UserProfileResponse)
def update_user_score(user_id: int, new_score: float, db: Session = Depends(get_db)):
    """Update user score"""
    return update_score_db(db, user_id, new_score)