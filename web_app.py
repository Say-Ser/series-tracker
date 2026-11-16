import os
import sqlite3
import aiohttp
import asyncio
from flask import Flask, render_template, request, redirect, url_for

# Берем ключ из настроек хостинга (Render)
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")

app = Flask(__name__, template_folder="templates")

def get_db_connection():
    conn = sqlite3.connect("series_tracker.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute("""CREATE TABLE IF NOT EXISTS series (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tmdb_id INTEGER NOT NULL UNIQUE,
        name TEXT NOT NULL,
        season INTEGER DEFAULT 1,
        episode INTEGER DEFAULT 1
    )""")
    conn.commit()
    conn.close()

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

@app.route('/')
def index():
    conn = get_db_connection()
    series_list = conn.execute('SELECT * FROM series').fetchall()
    conn.close()
    
    enriched_series = []
    for s in series_list:
        next_ep = asyncio.run(get_next_episode_info(s['tmdb_id']))
        enriched_series.append({
            "tmdb_id": s['tmdb_id'],
            "name": s['name'],
            "season": s['season'],
            "episode": s['episode'],
            "next_date": next_ep["date"],
            "next_info": next_ep["text"]
        })
    return render_template('index.html', my_series=enriched_series, search_results=None)

@app.route('/search')
def search():
    query = request.args.get('query', '')
    if not query:
        return redirect(url_for('index'))
    
    results = asyncio.run(search_tmdb(query))
    conn = get_db_connection()
    series_list = conn.execute('SELECT * FROM series').fetchall()
    conn.close()
    
    enriched_series = []
    for s in series_list:
        next_ep = asyncio.run(get_next_episode_info(s['tmdb_id']))
        enriched_series.append({
            "tmdb_id": s['tmdb_id'],
            "name": s['name'],
            "season": s['season'],
            "episode": s['episode'],
            "next_date": next_ep["date"],
            "next_info": next_ep["text"]
        })
    return render_template('index.html', my_series=enriched_series, search_results=results)

@app.route('/add', methods=['POST'])
def add():
    tmdb_id = request.form.get('tmdb_id')
    name = request.form.get('name')
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO series (tmdb_id, name) VALUES (?, ?)", (tmdb_id, name))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    return redirect(url_for('index'))

@app.route('/update_progress', methods=['POST'])
def update_progress():
    data = request.json
    tmdb_id = data.get('tmdb_id')
    conn = get_db_connection()
    conn.execute("UPDATE series SET episode = episode + 1 WHERE tmdb_id = ?", (tmdb_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}

if __name__ == '__main__':
    init_db()
    # Render автоматически назначает порт через переменную окружения PORT
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False)