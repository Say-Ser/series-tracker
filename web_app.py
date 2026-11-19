import os
import aiohttp
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for

# Берем ключи из настроек хостинга
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

app = Flask(__name__, template_folder="templates")

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

async def search_tmdb(query):
    url = f"https://api.themoviedb.org/3/search/tv?api_key={TMDB_API_KEY}&query={query}&language=ru-RU"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                return [{"name": s["name"], "tmdb_id": s["id"], "rating": s["vote_average"]} for s in data.get("results", [])[:5]]
    return []

async def get_next_episode_info(tmdb_id):
    url = f"https://api.themoviedb.org/3/tv/{tmdb_id}?api_key={TMDB_API_KEY}&language=ru-RU"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                next_ep = data.get("next_episode_to_air")
                if next_ep:
                    season = next_ep.get("season_number", "?")
                    episode = next_ep.get("episode_number", "?")
                    date = next_ep.get("air_date", "Дата неизвестна")
                    name = next_ep.get("name", "Без названия")
                    return {"date": date, "text": f"S{season}E{episode} • {name}"}
                else:
                    return {"date": None, "text": "Сериал завершен или дата не объявлена"}
    return {"date": None, "text": "Нет данных"}

def enrich_series_list(series_list):
    """Получает информацию о следующей серии для списка сериалов"""
    enriched = []
    for s in series_list:
        next_ep = asyncio.run(get_next_episode_info(s['tmdb_id']))
        enriched.append({
            "tmdb_id": s['tmdb_id'],
            "name": s['name'],
            "season": s['season'],
            "episode": s['episode'],
            "next_date": next_ep["date"],
            "next_info": next_ep["text"]
        })
    return enriched

@app.route('/')
def index():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM series WHERE user_id = %s ORDER BY name', ('web_user',))
    series_list = cur.fetchall()
    cur.close()
    conn.close()
    
    enriched_series = enrich_series_list(series_list)
    return render_template('index.html', my_series=enriched_series, search_results=None)

@app.route('/search')
def search():
    query = request.args.get('query', '')
    if not query:
        return redirect(url_for('index'))
    
    results = asyncio.run(search_tmdb(query))
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM series WHERE user_id = %s ORDER BY name', ('web_user',))
    series_list = cur.fetchall()
    cur.close()
    conn.close()
    
    enriched_series = enrich_series_list(series_list)
    return render_template('index.html', my_series=enriched_series, search_results=results)

@app.route('/add', methods=['POST'])
def add():
    tmdb_id = request.form.get('tmdb_id')
    name = request.form.get('name')
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO series (tmdb_id, name, user_id) VALUES (%s, %s, %s)",
            (tmdb_id, name, 'web_user')
        )
        conn.commit()
    except psycopg2.IntegrityError:
        conn.rollback()
    cur.close()
    conn.close()
    return redirect(url_for('index'))

@app.route('/update_progress', methods=['POST'])
def update_progress():
    data = request.json
    tmdb_id = data.get('tmdb_id')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE series SET episode = episode + 1 WHERE tmdb_id = %s AND user_id = %s",
        (tmdb_id, 'web_user')
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "success"}

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
