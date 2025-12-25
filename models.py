from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Float, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)

class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    url = Column(String, unique=True, index=True, nullable=False)
    category_hint = Column(String, nullable=True)  # e.g., "tech/robotics", "us politics"
    weight = Column(Float, default=1.0)
    min_score = Column(Integer, default=0)

class NewsArticle(Base):
    __tablename__ = "news_articles"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    url = Column(String, unique=True, index=True)
    source = Column(String)  # Legacy field, kept for backward compatibility
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=True, index=True)
    category = Column(String, index=True)  # References Category.name
    summary = Column(Text, nullable=True)
    is_saved = Column(Boolean, default=False, index=True)
    published_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationship
    source_obj = relationship("Source", backref="articles")

