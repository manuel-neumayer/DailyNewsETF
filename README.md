# Daily News Vibe

A mobile-friendly news aggregation web app that fetches news from RSS feeds and APIs, categorizes them using Google Gemini AI, and displays a curated feed focused on Robotics, AI, and US Politics.

## Features

- 📰 Aggregates news from NYT HomePage RSS and Hacker News API
- 🤖 AI-powered categorization using Google Gemini Flash
- 📱 Mobile-friendly dark mode UI with TailwindCSS
- 🗄️ SQLite for local development, PostgreSQL for production
- 🚀 Ready for deployment on Render.com

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file in the project root:

```env
# Required: Google Gemini API Key
GEMINI_API_KEY=your_gemini_api_key_here

# Optional: Database URL (defaults to SQLite)
# For local: DATABASE_URL=sqlite:///./news.db
# For production: DATABASE_URL=postgresql://user:password@host:port/dbname
```

Get your Gemini API key from: https://makersuite.google.com/app/apikey

### 3. Run the Application

```bash
uvicorn main:app --reload
```

Then open your browser to `http://localhost:8000`

## Usage

1. **View News Feed**: The homepage displays articles grouped by category (Robotics, AI, US Politics)
2. **Refresh News**: Click the "Refresh News" button to fetch and categorize new articles
3. **API Endpoints**:
   - `GET /` - Main news feed page
   - `POST /api/refresh` - Trigger news refresh
   - `GET /api/articles?category=AI&limit=50` - Get articles via API

## Project Structure

```
DailyNewsETF/
├── main.py              # FastAPI application and routes
├── scraper.py           # News fetching and categorization logic
├── database.py          # SQLAlchemy database setup
├── models.py            # Database models
├── requirements.txt     # Python dependencies
├── render.yaml          # Render.com deployment config
├── templates/
│   └── index.html       # Frontend template
└── .env                 # Environment variables (create this)
```

## Deployment to Render.com

1. Push your code to a Git repository (GitHub, GitLab, etc.)
2. Connect your repository to Render.com
3. Create a new Web Service
4. Render will automatically detect the `render.yaml` configuration
5. Set the following environment variables in Render:
   - `GEMINI_API_KEY` - Your Google Gemini API key
   - `DATABASE_URL` - Your PostgreSQL connection string (Render provides this automatically if you create a PostgreSQL database)

## Tech Stack

- **Backend**: FastAPI (Python)
- **Database**: SQLAlchemy (SQLite/PostgreSQL)
- **AI**: Google Gemini Flash (via google-generativeai)
- **Frontend**: TailwindCSS (CDN)
- **News Sources**: NYT RSS, Hacker News API

