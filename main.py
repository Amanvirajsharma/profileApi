import os
from fastapi import FastAPI, Depends, HTTPException, status, Query
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, ForeignKey, TIMESTAMP, CheckConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.sql import func
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime

# ============= DATABASE SETUP =============

# Get DATABASE_URL from environment variable (for Render)
DATABASE_URL = os.getenv("DATABASE_URL")

# Fallback for local development
if not DATABASE_URL:
    DATABASE_URL = "postgresql://postgres:Aman2506@localhost:5433/profile_db"
    print("⚠️  Using local database")
else:
    print("✅ Using production database")

# Fix Render's postgres:// to postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Create engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
)

# Create session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


# ============= DATABASE MODELS (Tables) =============

class User(Base):
    """User table in database"""
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
    
    # Relationship with Education table
    education = relationship("Education", back_populates="user", cascade="all, delete-orphan")
    
    # Constraints
    __table_args__ = (
        CheckConstraint('score >= 0 AND score <= 100', name='check_score_range'),
        CheckConstraint('test_count >= 0', name='check_test_count'),
        CheckConstraint("user_type IN ('student', 'professor', 'teacher')", name='check_user_type'),
    )


class Education(Base):
    """Education table in database"""
    __tablename__ = "education"
    
    education_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    degree = Column(String(255), nullable=False)
    institution = Column(String(255), nullable=False)
    year = Column(Integer, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    # Relationship with User table
    user = relationship("User", back_populates="education")


# Create all tables in database
Base.metadata.create_all(bind=engine)


# ============= PYDANTIC SCHEMAS (API Models) =============

class UserType(str, Enum):
    """User type options"""
    STUDENT = "student"
    PROFESSOR = "professor"
    TEACHER = "teacher"


class EducationBase(BaseModel):
    """Education base schema"""
    degree: str = Field(..., example="Bachelor of Science", max_length=255)
    institution: str = Field(..., example="MIT", max_length=255)
    year: int = Field(..., example=2023, ge=1900, le=2100)


class EducationCreate(EducationBase):
    """Schema for creating education"""
    pass


class EducationResponse(EducationBase):
    """Schema for education response"""
    education_id: int
    user_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserProfileBase(BaseModel):
    """User profile base schema"""
    name: str = Field(..., min_length=2, max_length=100, example="John Doe")
    email: EmailStr = Field(..., example="john@example.com")
    bio: Optional[str] = Field(None, max_length=500, example="A passionate learner")
    location: Optional[str] = Field(None, max_length=255, example="New York, USA")
    score: float = Field(default=0.0, ge=0, le=100, example=85.5)
    test_count: int = Field(default=0, ge=0, example=5)
    phone_no: Optional[str] = Field(None, max_length=20, example="+1234567890")
    user_type: UserType = Field(..., example="student")


class UserProfileCreate(UserProfileBase):
    """Schema for creating user profile"""
    education: Optional[EducationCreate] = None


class UserProfileUpdate(BaseModel):
    """Schema for updating user profile"""
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    email: Optional[EmailStr] = None
    bio: Optional[str] = Field(None, max_length=500)
    location: Optional[str] = Field(None, max_length=255)
    score: Optional[float] = Field(None, ge=0, le=100)
    test_count: Optional[int] = Field(None, ge=0)
    phone_no: Optional[str] = Field(None, max_length=20)
    user_type: Optional[UserType] = None
    education: Optional[EducationCreate] = None


class UserProfileResponse(UserProfileBase):
    """Schema for user profile response"""
    user_id: int
    created_at: datetime
    updated_at: datetime
    education: List[EducationResponse] = []
    
    class Config:
        from_attributes = True


# ============= DATABASE DEPENDENCY =============

def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============= CRUD FUNCTIONS =============

def create_user_db(db: Session, user_data: UserProfileCreate):
    """Create new user in database"""
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
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
    """Get all users from database"""
    query = db.query(User)
    if user_type:
        query = query.filter(User.user_type == user_type)
    return query.offset(skip).limit(limit).all()


def get_user_db(db: Session, user_id: int):
    """Get single user by ID"""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    return user


def update_user_db(db: Session, user_id: int, user_data: UserProfileUpdate):
    """Update user in database"""
    db_user = get_user_db(db, user_id)
    
    # Update user fields
    update_data = user_data.model_dump(exclude_unset=True, exclude={'education'})
    
    for key, value in update_data.items():
        if key == 'user_type' and value:
            setattr(db_user, key, value.value)
        elif value is not None:
            setattr(db_user, key, value)
    
    # Update education if provided
    if user_data.education:
        # Delete old education records
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
    """Delete user from database"""
    db_user = get_user_db(db, user_id)
    db.delete(db_user)
    db.commit()
    return True


def increment_test_db(db: Session, user_id: int):
    """Increment test count for user"""
    db_user = get_user_db(db, user_id)
    db_user.test_count += 1
    db.commit()
    db.refresh(db_user)
    return db_user


def update_score_db(db: Session, user_id: int, new_score: float):
    """Update user score"""
    if new_score < 0 or new_score > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Score must be between 0 and 100"
        )
    
    db_user = get_user_db(db, user_id)
    db_user.score = new_score
    db.commit()
    db.refresh(db_user)
    return db_user


# ============= FASTAPI APPLICATION =============

app = FastAPI(
    title="Profile API",
    description="Complete User Profile Management System with PostgreSQL",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)


# ============= API ENDPOINTS =============

@app.get("/", tags=["Root"])
def root():
    """Root endpoint - API info"""
    return {
        "message": "✅ Profile API is running",
        "version": "2.0.0",
        "database": "PostgreSQL",
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.get("/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint"""
    try:
        # Test database connection
        db.query(User).first()
        return {
            "status": "healthy",
            "database": "connected"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection failed: {str(e)}"
        )


@app.post("/profiles/", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED, tags=["Profiles"])
def create_profile(user: UserProfileCreate, db: Session = Depends(get_db)):
    """
    Create a new user profile
    
    - **name**: User's full name (required)
    - **email**: Valid email address (required)
    - **user_type**: student, professor, or teacher (required)
    - **bio**: Short biography (optional)
    - **location**: User's location (optional)
    - **score**: Score between 0-100 (default: 0)
    - **test_count**: Number of tests taken (default: 0)
    - **phone_no**: Contact number (optional)
    - **education**: Education details (optional)
    """
    return create_user_db(db, user)


@app.get("/profiles/", response_model=List[UserProfileResponse], tags=["Profiles"])
def get_all_profiles(
    user_type: Optional[UserType] = None,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum records to return"),
    db: Session = Depends(get_db)
):
    """
    Get all user profiles
    
    - **user_type**: Filter by user type (optional)
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    """
    return get_users_db(
        db, 
        user_type=user_type.value if user_type else None, 
        skip=skip, 
        limit=limit
    )


@app.get("/profiles/{user_id}", response_model=UserProfileResponse, tags=["Profiles"])
def get_profile(user_id: int, db: Session = Depends(get_db)):
    """
    Get a specific user profile by ID
    
    - **user_id**: The ID of the user to retrieve
    """
    return get_user_db(db, user_id)


@app.put("/profiles/{user_id}", response_model=UserProfileResponse, tags=["Profiles"])
def update_profile(
    user_id: int, 
    user: UserProfileUpdate, 
    db: Session = Depends(get_db)
):
    """
    Update an existing user profile
    
    - **user_id**: The ID of the user to update
    - All fields are optional - only provided fields will be updated
    """
    return update_user_db(db, user_id, user)


@app.delete("/profiles/{user_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Profiles"])
def delete_profile(user_id: int, db: Session = Depends(get_db)):
    """
    Delete a user profile
    
    - **user_id**: The ID of the user to delete
    """
    delete_user_db(db, user_id)
    return None


@app.patch("/profiles/{user_id}/increment-test", response_model=UserProfileResponse, tags=["Actions"])
def increment_test_count(user_id: int, db: Session = Depends(get_db)):
    """
    Increment the test count for a user
    
    - **user_id**: The ID of the user
    """
    return increment_test_db(db, user_id)


@app.patch("/profiles/{user_id}/update-score", response_model=UserProfileResponse, tags=["Actions"])
def update_user_score(
    user_id: int,
    new_score: float = Query(..., ge=0, le=100, description="New score between 0 and 100"),
    db: Session = Depends(get_db)
):
    """
    Update a user's score
    
    - **user_id**: The ID of the user
    - **new_score**: New score value (0-100)
    """
    return update_score_db(db, user_id, new_score)


# ============= STARTUP EVENT =============

@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    print("=" * 50)
    print("🚀 Profile API Started Successfully!")
    print(f"📊 Database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'Local'}")
    print(f"📚 Docs: http://localhost:8000/docs")
    print("=" * 50)