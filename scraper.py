import feedparser
import httpx
import requests
import google.generativeai as genai
import os
import re
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from models import NewsArticle, Category, Source
from datetime import datetime

load_dotenv()

# Initialize Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
else:
    model = None

def extract_score_from_text(text: str) -> int:
    """
    Extract score/karma from Reddit or Hacker News feed descriptions.
    Looks for patterns like "Points: 150", "Score: 50", "karma: 200", etc.
    Returns 0 if no score found.
    """
    if not text:
        return 0
    
    # Common patterns: "Points: 150", "Score: 50", "karma: 200", "upvotes: 100"
    patterns = [
        r'(?:points?|score|karma|upvotes?)[:\s]+(\d+)',
        r'(\d+)\s*(?:points?|score|karma|upvotes?)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue
    
    return 0

def map_category_hint_to_category(category_hint: str, db: Session) -> str | None:
    """
    Map a source's category_hint to an actual Category name.
    Returns the category name if there's a clear match, None otherwise.
    """
    if not category_hint:
        return None
    
    # Get all categories from database
    categories = db.query(Category).all()
    category_names = [cat.name for cat in categories]
    
    # Normalize category_hint for matching
    hint_lower = category_hint.lower()
    
    # Direct mappings
    if 'robotics' in hint_lower:
        if 'Robotics' in category_names:
            return 'Robotics'
    elif 'ai' in hint_lower or 'artificial' in hint_lower or 'machine learning' in hint_lower:
        if 'AI' in category_names:
            return 'AI'
    elif 'politics' in hint_lower and ('us' in hint_lower or 'united states' in hint_lower):
        if 'US Politics' in category_names:
            return 'US Politics'
    
    # If hint is too generic (news, tech, science) or doesn't match, return None
    # This will trigger Gemini categorization
    generic_hints = ['news', 'tech', 'science', 'math']
    if any(gh in hint_lower for gh in generic_hints):
        return None
    
    return None

def strip_html_tags(text: str) -> str:
    """
    Strip HTML tags from text using regex.
    """
    if not text:
        return ""
    return re.sub(r'<[^<]+?>', '', text).strip()

def parse_rss_entry(entry, source: Source) -> dict:
    """
    Parse an RSS feed entry and extract title, url, summary, and published date.
    Implements source-specific parsing logic for different feed formats.
    """
    result = {
        "title": "",
        "url": "",
        "summary": "",
        "published": ""
    }
    
    # Extract title (common for all sources)
    title = entry.get("title", "").strip()
    
    # Source-specific parsing
    source_url_lower = source.url.lower()
    
    # A. ArXiv Feeds
    if "arxiv.org" in source_url_lower:
        # Strip "arXiv:XXXX.XXXX" prefix if present
        title = re.sub(r'^arXiv:\s*\d{4}\.\d{4,5}\s*', '', title)
        # Clean up newlines
        title = re.sub(r'\s+', ' ', title).strip()
        result["title"] = title
        result["url"] = entry.get("link", "")
        result["summary"] = entry.get("summary", "") or entry.get("description", "")
        result["published"] = entry.get("published", "")
    
    # B. Hacker News (hnrss.org)
    elif "hnrss.org" in source_url_lower:
        result["title"] = title
        # Use entry.comments if it exists (this is the external link), otherwise use entry.link
        result["url"] = entry.get("comments", "") or entry.get("link", "")
        # Extract points and comments from description
        description = entry.get("description", "") or entry.get("summary", "")
        points_match = re.search(r'Points:\s*(\d+)', description, re.IGNORECASE)
        comments_match = re.search(r'#?\s*Comments?:\s*(\d+)', description, re.IGNORECASE)
        
        points = points_match.group(1) if points_match else "0"
        comments = comments_match.group(1) if comments_match else "0"
        result["summary"] = f"Points: {points} | Comments: {comments}"
        result["published"] = entry.get("published", "")
    
    # C. Google News
    elif "news.google.com" in source_url_lower:
        result["title"] = title
        result["url"] = entry.get("link", "")
        description = entry.get("description", "") or entry.get("summary", "")
        
        # Check if description looks like HTML code
        if description and ("<" in description and ">" in description):
            # Strip HTML tags
            description = strip_html_tags(description)
            # If still messy or empty, use publication date
            if not description or len(description) < 10:
                result["summary"] = entry.get("published", "") or entry.get("pubDate", "")
            else:
                result["summary"] = description
        else:
            result["summary"] = description
        result["published"] = entry.get("published", "") or entry.get("pubDate", "")
    
    # D. Default / General Fallback
    else:
        result["title"] = title
        result["url"] = entry.get("link", "")
        
        # Try multiple fields for summary: summary -> description -> content[0].value
        summary = ""
        if entry.get("summary"):
            summary = entry.get("summary")
        elif entry.get("description"):
            summary = entry.get("description")
        elif entry.get("content") and len(entry.get("content", [])) > 0:
            summary = entry.get("content")[0].get("value", "")
        
        # Strip HTML tags if present
        summary = strip_html_tags(summary)
        
        # Truncate to 500 characters
        if len(summary) > 500:
            summary = summary[:500] + "..."
        
        result["summary"] = summary
        result["published"] = entry.get("published", "") or entry.get("pubDate", "")
    
    return result

def categorize_headline(headline: str, db: Session) -> str | None:
    """
    Use Gemini to categorize a headline.
    Returns the category if it matches our interests, None otherwise.
    """
    if not model:
        print("Warning: GEMINI_API_KEY not set. Skipping categorization.")
        return None
    
    # Fetch categories from database
    categories = db.query(Category).order_by(Category.name).all()
    if not categories:
        print("Warning: No categories found in database. Skipping categorization.")
        return None
    
    category_names = [cat.name for cat in categories]
    category_list = ', '.join(category_names)
    
    prompt = f"""Categorize this news headline into ONE of the following: {category_list}. If it doesn't fit, respond 'OTHER'.

Headline: {headline}

Respond with ONLY the category name ({category_list}) or 'OTHER'."""

    try:
        response = model.generate_content(prompt)
        category = response.text.strip()
        
        # Clean up the response
        category = category.replace("*", "").strip()
        
        # Check if the category matches any in the database
        if category in category_names:
            return category
        return None
    except Exception as e:
        print(f"Error categorizing headline '{headline}': {e}")
        return None

def fetch_feed_articles(source: Source) -> list[dict]:
    """
    Fetch articles from an RSS feed or Reddit JSON source.
    Returns a list of article dictionaries with score extracted if applicable.
    """
    articles = []
    
    # Check if this is a Reddit source
    if "reddit.com" in source.url.lower():
        # Case A: Reddit JSON API
        try:
            # Convert RSS URL to JSON URL
            json_url = source.url.replace(".rss", "").replace("/.rss", "")
            if not json_url.endswith(".json"):
                if json_url.endswith("/"):
                    json_url = json_url + ".json"
                else:
                    json_url = json_url + "/.json"
            
            # Fetch Reddit JSON with proper headers
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            response = requests.get(json_url, headers=headers, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            
            # Parse Reddit JSON structure
            if "data" in data and "children" in data["data"]:
                for child in data["data"]["children"]:
                    post = child.get("data", {})
                    title = post.get("title", "").strip()
                    if not title:
                        continue
                    
                    # Get the actual URL (permalink for self-posts, url for links)
                    permalink = post.get("permalink", "")
                    url = post.get("url", "")
                    if permalink and not url.startswith("http"):
                        url = f"https://www.reddit.com{permalink}"
                    
                    # Get score (ups is the upvotes count)
                    score = post.get("ups", 0)
                    
                    # Filter by min_score if applicable
                    if source.min_score > 0 and score < source.min_score:
                        continue
                    
                    # Convert created_utc to datetime
                    created_utc = post.get("created_utc", 0)
                    published = None
                    if created_utc:
                        try:
                            published = datetime.fromtimestamp(created_utc).isoformat()
                        except (ValueError, OSError):
                            published = None
                    
                    # Get selftext as summary
                    summary = post.get("selftext", "") or ""
                    
                    articles.append({
                        "title": title,
                        "url": url,
                        "summary": summary,
                        "published": published,
                        "score": score,
                        "source_id": source.id
                    })
        except requests.exceptions.RequestException as e:
            print(f"  Error fetching Reddit JSON from {source.name}: {e}")
            return articles
        except (KeyError, ValueError, TypeError) as e:
            print(f"  Error parsing Reddit JSON from {source.name}: {e}")
            return articles
        except Exception as e:
            print(f"  Unexpected error fetching Reddit from {source.name}: {e}")
            return articles
    else:
        # Case B: Standard RSS (XML)
        try:
            # Custom User-Agent to avoid being blocked
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            
            # Parse RSS feed with custom User-Agent
            feed = feedparser.parse(source.url, agent=user_agent)
            
            if feed.bozo and feed.bozo_exception:
                print(f"  Warning: Feed parsing error for {source.name}: {feed.bozo_exception}")
                return articles
            
            for entry in feed.entries:
                # Use the new parse_rss_entry helper
                parsed = parse_rss_entry(entry, source)
                
                title = parsed["title"]
                if not title:
                    continue
                
                # Extract score from summary/description for HN feeds
                summary_text = parsed["summary"] or entry.get("description", "") or entry.get("summary", "")
                score = extract_score_from_text(summary_text)
                
                # Filter by min_score if applicable
                if source.min_score > 0 and score < source.min_score:
                    continue
                
                articles.append({
                    "title": title,
                    "url": parsed["url"],
                    "summary": parsed["summary"],
                    "published": parsed["published"],
                    "score": score,
                    "source_id": source.id
                })
        except Exception as e:
            print(f"  Error fetching RSS feed from {source.name} ({source.url}): {e}")
            return articles
    
    return articles

def scrape_and_save(db: Session):
    """
    Main scraping function: fetches from all sources in the database,
    categorizes articles, and saves relevant ones.
    """
    print("Starting news scrape...")
    
    # Get all active sources from database
    sources = db.query(Source).all()
    print(f"Found {len(sources)} sources to process")
    
    all_articles = []
    source_stats = {}
    
    # Fetch articles from each source
    for source in sources:
        try:
            print(f"Fetching from: {source.name}...")
            articles = fetch_feed_articles(source)
            all_articles.extend(articles)
            source_stats[source.name] = len(articles)
            print(f"  Fetched {len(articles)} articles from {source.name}")
        except Exception as e:
            print(f"  Error processing {source.name}: {e}")
            source_stats[source.name] = 0
            continue  # Continue to next source even if one fails
    
    print(f"\nTotal articles fetched: {len(all_articles)}")
    
    # Categorize and save
    saved_count = 0
    skipped_count = 0
    categorized_count = 0
    gemini_calls = 0
    
    # Get all categories for hint mapping
    categories = db.query(Category).all()
    
    for article in all_articles:
        # Early validation: check title and URL first (before any expensive operations)
        title = article.get("title", "").strip()
        url = article.get("url", "").strip()
        
        if not title:
            print(f"  Skipping article with empty title: {url[:50]}...")
            continue
        
        if not url:
            print(f"  Skipping article with empty URL: {title[:50]}...")
            skipped_count += 1
            continue
        
        # Check for duplicates BEFORE any expensive operations (categorization, etc.)
        existing = db.query(NewsArticle).filter(
            NewsArticle.url == url
        ).first()
        
        if existing:
            skipped_count += 1
            # print(f"  Skipping duplicate: {url[:80]}...")
            continue
        
        # Get source object
        source = db.query(Source).filter(Source.id == article.get("source_id")).first()
        if not source:
            print(f"  Skipping article: source_id {article.get('source_id')} not found")
            skipped_count += 1
            continue
        
        # Now do categorization (only for new articles)
        # Smart categorization: try category_hint first
        category = None
        if source.category_hint:
            category = map_category_hint_to_category(source.category_hint, db)
            if category:
                categorized_count += 1
        
        # If hint didn't match, use Gemini
        if not category:
            category = categorize_headline(title, db)
            if category:
                gemini_calls += 1
        
        # Only save if we got a category
        if category:
            try:
                # Double-check for duplicates right before adding (handles race conditions)
                existing_check = db.query(NewsArticle).filter(
                    NewsArticle.url == url
                ).first()
                
                if existing_check:
                    skipped_count += 1
                    print(f"  Skipping duplicate (race condition): {url[:80]}...")
                    continue
                
                # Save to database
                news_article = NewsArticle(
                    title=title,
                    url=url,
                    source=source.name,  # Legacy field
                    source_id=source.id,
                    category=category,
                    summary=article.get("summary", ""),
                    published_at=datetime.now()
                )
                db.add(news_article)
                db.flush()  # Flush to check for immediate errors without committing
                saved_count += 1
            except IntegrityError as e:
                # Handle duplicate constraint errors specifically
                db.rollback()
                skipped_count += 1
                print(f"  Skipping duplicate (constraint): {url[:80]}...")
                continue
            except Exception as e:
                # Handle any other database errors gracefully
                db.rollback()
                skipped_count += 1
                print(f"  Error saving article {url[:80]}...: {e}")
                continue
    
    db.commit()
    
    print(f"\nScrape complete!")
    print(f"  Saved: {saved_count} new articles")
    print(f"  Skipped: {skipped_count} duplicates")
    print(f"  Categorized via hint: {categorized_count}")
    print(f"  Categorized via Gemini: {gemini_calls}")
    print(f"  Total fetched: {len(all_articles)}")
    
    return {
        "saved": saved_count,
        "skipped": skipped_count,
        "total_fetched": len(all_articles),
        "source_stats": source_stats,
        "gemini_calls": gemini_calls
    }
