import os
from fastapi import FastAPI, Depends, HTTPException, status, Query
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, ForeignKey, TIMESTAMP, CheckConstraint, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.sql import func
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime

# ============= DATABASE CONFIGURATION =============

# YAHAN APNA DATABASE URL DAALO
# Format: postgresql://username:password@host:port/database_name

# LOCAL DEVELOPMENT (Tumhara PC)
LOCAL_DB_URL = "postgresql://postgres:Aman2506@localhost:5433/profile_db"
# ☝️ YAHAN PASSWORD CHANGE KARO if needed

# Get from environment (for Render production)
DATABASE_URL = os.environ.get("DATABASE_URL", LOCAL_DB_URL)

# Fix postgres:// to postgresql:// (Render compatibility)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Show connection info
print("\n" + "="*70)
if "localhost" in DATABASE_URL:
    print("🏠 LOCAL MODE - Using your PostgreSQL")
    print(f"📊 Database: localhost:5433/profile_db")
else:
    print("☁️  PRODUCTION MODE - Using Render PostgreSQL")
    db_host = DATABASE_URL.split("@")[1].split("/")[0] if "@" in DATABASE_URL else "cloud"
    print(f"📊 Database: {db_host}")
print("="*70 + "\n")

# Create engine
try:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=10,
        echo=False  # Set True for SQL debug
    )
    print("✅ Database engine created")
except Exception as e:
    print(f"❌ Engine creation failed: {e}")
    raise

# Session factory
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
    
    education = relationship("Education", back_populates="user", cascade="all, delete-orphan")


class Education(Base):
    __tablename__ = "education"
    
    education_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    degree = Column(String(255), nullable=False)
    institution = Column(String(255), nullable=False)
    year = Column(Integer, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    user = relationship("User", back_populates="education")


# Create tables
try:
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created/verified\n")
except Exception as e:
    print(f"❌ Table creation failed: {e}")
    print("⚠️  Check if PostgreSQL is running and database exists\n")


# ============= PYDANTIC MODELS =============

class UserType(str, Enum):
    STUDENT = "student"
    PROFESSOR = "professor"
    TEACHER = "teacher"


class EducationBase(BaseModel):
    degree: str = Field(..., example="Bachelor of Science")
    institution: str = Field(..., example="MIT")
    year: int = Field(..., example=2023, ge=1900, le=2100)


class EducationCreate(EducationBase):
    pass


class EducationResponse(EducationBase):
    education_id: int
    user_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserProfileBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, example="John Doe")
    email: EmailStr = Field(..., example="john@example.com")
    bio: Optional[str] = Field(None, max_length=500, example="A passionate learner")
    location: Optional[str] = Field(None, example="New York, USA")
    score: float = Field(default=0.0, ge=0, le=100, example=85.5)
    test_count: int = Field(default=0, ge=0, example=5)
    phone_no: Optional[str] = Field(None, max_length=20, example="+1234567890")
    user_type: UserType = Field(..., example="student")


class UserProfileCreate(UserProfileBase):
    education: Optional[EducationCreate] = None


class UserProfileUpdate(BaseModel):
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


# ============= CRUD FUNCTIONS =============

def create_user_db(db: Session, user_data: UserProfileCreate):
    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
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
    
    if user_data.education:
        edu = Education(
            user_id=db_user.user_id,
            degree=user_data.education.degree,
            institution=user_data.education.institution,
            year=user_data.education.year
        )
        db.add(edu)
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
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return user


def update_user_db(db: Session, user_id: int, user_data: UserProfileUpdate):
    db_user = get_user_db(db, user_id)
    
    update_data = user_data.model_dump(exclude_unset=True, exclude={'education'})
    
    for key, value in update_data.items():
        if key == 'user_type' and value:
            setattr(db_user, key, value.value)
        elif value is not None:
            setattr(db_user, key, value)
    
    if user_data.education:
        db.query(Education).filter(Education.user_id == user_id).delete()
        edu = Education(
            user_id=user_id,
            degree=user_data.education.degree,
            institution=user_data.education.institution,
            year=user_data.education.year
        )
        db.add(edu)
    
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
    if not 0 <= new_score <= 100:
        raise HTTPException(status_code=400, detail="Score must be 0-100")
    
    db_user = get_user_db(db, user_id)
    db_user.score = new_score
    db.commit()
    db.refresh(db_user)
    return db_user


# ============= FASTAPI APP =============

app = FastAPI(
    title="Profile API",
    description="User Profile Management System",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)


# ============= ENDPOINTS =============

@app.get("/", tags=["Root"])
def root():
    return {
        "status": "✅ Running",
        "message": "Profile API is live!",
        "version": "2.0.0",
        "docs": "/docs"
    }


@app.get("/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        user_count = db.query(User).count()
        return {
            "status": "healthy",
            "database": "connected",
            "total_users": user_count
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {str(e)}")


@app.post("/profiles/", response_model=UserProfileResponse, status_code=201, tags=["Profiles"])
def create_profile(user: UserProfileCreate, db: Session = Depends(get_db)):
    """Create new user profile"""
    return create_user_db(db, user)


@app.get("/profiles/", response_model=List[UserProfileResponse], tags=["Profiles"])
def get_all_profiles(
    user_type: Optional[UserType] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """Get all user profiles"""
    return get_users_db(db, user_type=user_type.value if user_type else None, skip=skip, limit=limit)


@app.get("/profiles/{user_id}", response_model=UserProfileResponse, tags=["Profiles"])
def get_profile(user_id: int, db: Session = Depends(get_db)):
    """Get specific user profile"""
    return get_user_db(db, user_id)


@app.put("/profiles/{user_id}", response_model=UserProfileResponse, tags=["Profiles"])
def update_profile(user_id: int, user: UserProfileUpdate, db: Session = Depends(get_db)):
    """Update user profile"""
    return update_user_db(db, user_id, user)


@app.delete("/profiles/{user_id}", status_code=204, tags=["Profiles"])
def delete_profile(user_id: int, db: Session = Depends(get_db)):
    """Delete user profile"""
    delete_user_db(db, user_id)
    return None


@app.patch("/profiles/{user_id}/increment-test", response_model=UserProfileResponse, tags=["Actions"])
def increment_test(user_id: int, db: Session = Depends(get_db)):
    """Increment test count"""
    return increment_test_db(db, user_id)


@app.patch("/profiles/{user_id}/update-score", response_model=UserProfileResponse, tags=["Actions"])
def update_score(
    user_id: int,
    new_score: float = Query(..., ge=0, le=100),
    db: Session = Depends(get_db)
):
    """Update user score"""
    return update_score_db(db, user_id, new_score)


@app.on_event("startup")
async def startup():
    print("🚀 FastAPI Server Started!")
    print("📚 Documentation: http://127.0.0.1:8000/docs\n")