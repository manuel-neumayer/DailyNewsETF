from fastapi import FastAPI, Request, Depends, BackgroundTasks, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session, joinedload
from database import get_db, engine, Base, SessionLocal
from models import NewsArticle, Category, Source
from scraper import scrape_and_save
from datetime import datetime
import os
import json
from pydantic import BaseModel

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Daily News Vibe")

# Seed default categories if table is empty
def seed_categories():
    db = SessionLocal()
    try:
        category_count = db.query(Category).count()
        if category_count == 0:
            default_categories = [
                Category(name="Robotics", description="News about robotics and automation"),
                Category(name="AI", description="Artificial intelligence and machine learning"),
                Category(name="US Politics", description="United States political news")
            ]
            for cat in default_categories:
                db.add(cat)
            db.commit()
            print("Seeded default categories: Robotics, AI, US Politics")
    finally:
        db.close()

# Seed default sources if table is empty
def seed_sources():
    db = SessionLocal()
    try:
        source_count = db.query(Source).count()
        if source_count == 0:
            sources_data = [
                {
                    "name": "Hacker News - Frontpage (HN RSS)",
                    "url": "https://hnrss.org/frontpage",
                    "category_hint": "tech",
                    "weight": 1.0,
                    "min_score": 100
                },
                {
                    "name": "Hacker News - Newest (HN RSS)",
                    "url": "https://hnrss.org/newest",
                    "category_hint": "tech",
                    "weight": 0.5,
                    "min_score": 200
                },
                {
                    "name": "Reddit r/MachineLearning",
                    "url": "https://www.reddit.com/r/MachineLearning/.rss",
                    "category_hint": "tech/ai",
                    "weight": 0.8,
                    "min_score": 50
                },
                {
                    "name": "Reddit r/artificial",
                    "url": "https://www.reddit.com/r/artificial/.rss",
                    "category_hint": "tech/ai",
                    "weight": 0.8,
                    "min_score": 50
                },
                {
                    "name": "Reddit r/robotics",
                    "url": "https://www.reddit.com/r/robotics/.rss",
                    "category_hint": "tech/robotics",
                    "weight": 0.8,
                    "min_score": 30
                },
                {
                    "name": "Reddit r/Singularity",
                    "url": "https://www.reddit.com/r/Singularity/.rss",
                    "category_hint": "tech/ai/futures",
                    "weight": 0.6,
                    "min_score": 30
                },
                {
                    "name": "Reddit r/math",
                    "url": "https://www.reddit.com/r/math/.rss",
                    "category_hint": "math",
                    "weight": 0.5,
                    "min_score": 30
                },
                {
                    "name": "Reddit r/science",
                    "url": "https://www.reddit.com/r/science/.rss",
                    "category_hint": "science",
                    "weight": 0.6,
                    "min_score": 100
                },
                {
                    "name": "arXiv CS.AI (Artificial Intelligence)",
                    "url": "https://export.arxiv.org/rss/cs.AI",
                    "category_hint": "research/ai",
                    "weight": 0.9,
                    "min_score": 0
                },
                {
                    "name": "arXiv CS.RO (Robotics)",
                    "url": "https://export.arxiv.org/rss/cs.RO",
                    "category_hint": "research/robotics",
                    "weight": 0.9,
                    "min_score": 0
                },
                {
                    "name": "New York Times - HomePage",
                    "url": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
                    "category_hint": "news",
                    "weight": 1.0,
                    "min_score": 0
                },
                {
                    "name": "New York Times - Technology",
                    "url": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
                    "category_hint": "tech",
                    "weight": 0.9,
                    "min_score": 0
                },
                {
                    "name": "Reuters Politics (via Google News)",
                    "url": "https://news.google.com/rss/search?q=site:reuters.com+section:politics&ceid=US:en&hl=en-US&gl=US",
                    "category_hint": "us politics",
                    "weight": 1.0,
                    "min_score": 0
                },
                {
                    "name": "Reuters Technology (via Google News)",
                    "url": "https://news.google.com/rss/search?q=site:reuters.com+section:technology&ceid=US:en&hl=en-US&gl=US",
                    "category_hint": "tech",
                    "weight": 1.0,
                    "min_score": 0
                },
                {
                    "name": "Politico - US Politics (RSS)",
                    "url": "http://www.politico.com/rss/politicopicks.xml",
                    "category_hint": "us politics",
                    "weight": 0.9,
                    "min_score": 0
                },
                {
                    "name": "Axios - Politics",
                    "url": "https://api.axios.com/feed/",
                    "category_hint": "us politics",
                    "weight": 0.8,
                    "min_score": 0
                }
            ]
            
            for source_data in sources_data:
                source = Source(**source_data)
                db.add(source)
            db.commit()
            print(f"Seeded {len(sources_data)} default sources")
    finally:
        db.close()

# Seed on startup
seed_categories()
seed_sources()

# Templates
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db)):
    """Render the main news feed page"""
    # Get all articles (we'll filter client-side)
    articles = db.query(NewsArticle).options(
        joinedload(NewsArticle.source_obj)
    ).order_by(
        NewsArticle.created_at.desc()
    ).limit(200).all()
    
    # Get all categories
    categories = db.query(Category).order_by(Category.name).all()
    
    # Serialize articles to JSON for JavaScript
    articles_json = json.dumps([
        {
            "id": a.id,
            "title": a.title,
            "url": a.url,
            "source": a.source_obj.name if a.source_obj else (a.source or "Unknown"),
            "category": a.category,
            "summary": a.summary or "",
            "is_saved": a.is_saved or False,
            "published_at": a.published_at.isoformat() if a.published_at else None,
            "created_at": a.created_at.isoformat() if a.created_at else None
        }
        for a in articles
    ])
    
    # Serialize categories to JSON
    categories_json = json.dumps([
        {
            "id": c.id,
            "name": c.name,
            "description": c.description or ""
        }
        for c in categories
    ])
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "articles_json": articles_json,
        "categories_json": categories_json
    })

@app.post("/api/refresh")
async def refresh_news(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Trigger a news refresh in the background"""
    def run_scrape():
        with SessionLocal() as session:
            scrape_and_save(session)
    
    background_tasks.add_task(run_scrape)
    return {"status": "refresh_started", "message": "News refresh started in background"}

@app.get("/api/articles")
async def get_articles(
    category: str = None,
    saved_only: bool = False,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """API endpoint to get articles (optional filtering by category and saved status)"""
    query = db.query(NewsArticle)
    
    if category:
        query = query.filter(NewsArticle.category == category)
    
    if saved_only:
        query = query.filter(NewsArticle.is_saved == True)
    
    articles = query.options(
        joinedload(NewsArticle.source_obj)
    ).order_by(NewsArticle.created_at.desc()).limit(limit).all()
    
    return {
        "articles": [
            {
                "id": a.id,
                "title": a.title,
                "url": a.url,
                "source": a.source_obj.name if a.source_obj else (a.source or "Unknown"),
                "category": a.category,
                "summary": a.summary,
                "is_saved": a.is_saved,
                "published_at": a.published_at.isoformat() if a.published_at else None,
                "created_at": a.created_at.isoformat() if a.created_at else None
            }
            for a in articles
        ],
        "count": len(articles)
    }

@app.post("/api/articles/{article_id}/toggle-saved")
async def toggle_saved(article_id: int, db: Session = Depends(get_db)):
    """Toggle the is_saved status of an article"""
    article = db.query(NewsArticle).filter(NewsArticle.id == article_id).first()
    
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    article.is_saved = not article.is_saved
    db.commit()
    
    return {
        "id": article.id,
        "is_saved": article.is_saved
    }

# Category Management API Endpoints
class CategoryCreate(BaseModel):
    name: str
    description: str = ""

class CategoryResponse(BaseModel):
    id: int
    name: str
    description: str

@app.get("/api/categories")
async def get_categories(db: Session = Depends(get_db)):
    """Get all categories"""
    categories = db.query(Category).order_by(Category.name).all()
    return {
        "categories": [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description or ""
            }
            for c in categories
        ]
    }

@app.post("/api/categories")
async def create_category(category: CategoryCreate, db: Session = Depends(get_db)):
    """Create a new category"""
    # Check if category already exists
    existing = db.query(Category).filter(Category.name == category.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Category with this name already exists")
    
    new_category = Category(name=category.name, description=category.description)
    db.add(new_category)
    db.commit()
    db.refresh(new_category)
    
    return {
        "id": new_category.id,
        "name": new_category.name,
        "description": new_category.description or ""
    }

@app.delete("/api/categories/{category_id}")
async def delete_category(category_id: int, db: Session = Depends(get_db)):
    """Delete a category"""
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    # Check if any articles use this category
    # Commented out for now: At the moment, we expect that if the user wants to delete a category, they are willing to lose the articles in that category.
    #article_count = db.query(NewsArticle).filter(NewsArticle.category == category.name).count()
    #if article_count > 0:
    #    raise HTTPException(
    #        status_code=400, 
    #        detail=f"Cannot delete category. {article_count} article(s) are using it. Please update or delete those articles first."
    #    )
    
    db.delete(category)
    db.commit()
    
    return {"message": "Category deleted successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

