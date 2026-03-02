from flask import Flask, render_template, request, jsonify
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import db
import os
import re
import time
import yaml

app = Flask(__name__)

# Cache-bust static assets on every deploy (timestamp set at startup)
_STATIC_VERSION = str(int(time.time()))

@app.context_processor
def inject_static_version():
    return {'static_v': _STATIC_VERSION}

# Cache autocomplete lists at startup (they don't change often)
_autocomplete_cache = {}

# Load fighter blurbs from YAML (keyed by lowercase name for case-insensitive lookup)
# Loaded per request so edits to fighters.yaml are reflected without restarting
_YAML_PATH = os.path.join(os.path.dirname(__file__), 'fighters.yaml')

def get_fighter_blurb(name):
    try:
        with open(_YAML_PATH, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        # Try exact match first, then case-insensitive, then period-normalized
        # (DB names never have periods, but YAML keys use proper names like "Dr. Mario")
        blurb = data.get(name)
        if blurb is None:
            lower = name.lower()
            blurb = next((v for k, v in data.items() if k.lower() == lower), None)
        if blurb is None:
            normalized = name.lower().replace('.', '')
            blurb = next((v for k, v in data.items() if k.lower().replace('.', '') == normalized), None)
        return blurb or {}
    except Exception:
        return {}


def get_autocomplete_data(category):
    if category not in _autocomplete_cache:
        loaders = {
            'fighters': db.get_all_fighters,
            'locations': db.get_all_locations,
            'fight_types': db.get_all_fight_types,
            'ppvs': db.get_all_ppvs,
            'championships': db.get_all_championships,
            'brands': db.get_all_brands,
        }
        if category in loaders:
            try:
                _autocomplete_cache[category] = loaders[category]()
            except Exception:
                _autocomplete_cache[category] = []
    return _autocomplete_cache.get(category, [])


def fighter_to_filename(name):
    """Convert fighter name to asset filename (same logic as PyQt5 app)."""
    # Check for known edge cases where DB name doesn't match file on disk
    overrides = {
        'banjo & kazooie': 'banjoandkazooie',
        'banjo and kazooie': 'banjoandkazooie',
    }
    lower = name.lower()
    if lower in overrides:
        return overrides[lower]
    return lower.replace(' ', '').replace('.', '').replace('&', 'and')


def stage_to_filename(name):
    """Convert stage name to asset filename."""
    return name.lower().replace(' ', '').replace(',', '').replace("'", '').replace('(', '').replace(')', '').replace('-', '')


def normalize_champ_name(s):
    """Normalize championship display names."""
    if s is None:
        return s
    return str(s).replace('Unified Tag 1', 'Unified Tag')


# ---------- Page Routes ----------

@app.route('/')
def index():
    fighters = get_autocomplete_data('fighters')
    current_champs = db.get_current_champions()
    fighter_cards = [
        {
            'name': f,
            'filename': fighter_to_filename(f),
            'titles': [normalize_champ_name(t) for t in current_champs.get(f, [])]
        }
        for f in fighters
    ]
    return render_template('index.html', fighters=fighter_cards)


@app.route('/head2head')
def head2head():
    return render_template('head2head.html')


@app.route('/fighter/<name>')
def fighter_profile(name):
    blurb = get_fighter_blurb(name)
    return render_template('fighter.html', fighter_name=name, filename=fighter_to_filename(name), blurb=blurb)


@app.route('/leaderboard')
def leaderboard():
    return render_template('leaderboard.html')


@app.route('/seasons')
def seasons():
    all_seasons = db.get_all_seasons()
    return render_template('seasons.html', seasons=all_seasons)


@app.route('/championships')
def championships():
    return render_template('championships.html')


@app.route('/graphs')
def graphs():
    fighters = get_autocomplete_data('fighters')
    return render_template('graphs.html', fighters=fighters)


@app.route('/fights')
def fights():
    seasons = db.get_all_seasons()
    fight_types  = get_autocomplete_data('fight_types')
    locations    = get_autocomplete_data('locations')
    ppvs         = get_autocomplete_data('ppvs')
    championships = get_autocomplete_data('championships')
    brands       = get_autocomplete_data('brands')
    fighters     = get_autocomplete_data('fighters')
    return render_template(
        'fightlog.html',
        seasons=seasons,
        fight_types=fight_types,
        locations=locations,
        ppvs=ppvs,
        championships=championships,
        brands=brands,
        fighters=fighters,
    )


# ---------- API Routes ----------

@app.route('/api/autocomplete/<category>')
def api_autocomplete(category):
    data = get_autocomplete_data(category)
    q = request.args.get('q', '').lower()
    if q:
        data = [item for item in data if q in item.lower()]
    return jsonify(data)


@app.route('/api/head2head', methods=['POST'])
def api_head2head():
    data = request.get_json()
    fighter1 = data.get('fighter1', '')
    fighter2 = data.get('fighter2', '')

    if not fighter1 or not fighter2:
        return jsonify({'error': 'Both fighters are required'}), 400

    filters = {
        'map': data.get('map', ''),
        'matchType': data.get('matchType', ''),
        'season': data.get('season', ''),
        'month': data.get('month', ''),
        'ppv': data.get('ppv', ''),
        'championship': data.get('championship', ''),
        'contender': data.get('contender', ''),
        'brand': data.get('brand', ''),
    }

    try:
        results = db.get_h2h_data(fighter1, fighter2, filters)
        # Add image filenames
        results['fighter1']['image'] = fighter_to_filename(fighter1) + '.png'
        results['fighter2']['image'] = fighter_to_filename(fighter2) + '.png'
        if filters['map']:
            results['stage_image'] = stage_to_filename(filters['map']) + '.png'
        else:
            results['stage_image'] = ''
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _serialize(val):
    """Convert DB values to JSON-safe types."""
    if isinstance(val, Decimal):
        return float(val)
    if hasattr(val, 'isoformat'):
        return val.isoformat()
    return val


@app.route('/api/fighter/<name>')
def api_fighter(name):
    try:
        # Run career stats and accolades queries in parallel
        with ThreadPoolExecutor(max_workers=2) as pool:
            career_future = pool.submit(db.get_fighter_career_stats, name)
            accolades_future = pool.submit(db.get_fighter_accolades, name)
            stats = career_future.result()
            accolades_raw = accolades_future.result()

        # Format for JSON
        result = {'name': name, 'image': fighter_to_filename(name) + '.png'}

        # Career overview
        if stats.get('career') and len(stats['career']) > 0:
            row = stats['career'][0]
            result['career'] = {'wins': row[1] if len(row) > 1 else 0, 'losses': row[2] if len(row) > 2 else 0, 'win_pct': str(row[3]) if len(row) > 3 else '0.00%'}
        else:
            result['career'] = {'wins': 0, 'losses': 0, 'win_pct': '0.00%'}

        # By season (for charts)
        result['by_season'] = []
        for row in stats.get('by_season', []):
            result['by_season'].append({'season': str(row[1]) if len(row) > 1 else '', 'wins': row[2] if len(row) > 2 else 0, 'losses': row[3] if len(row) > 3 else 0, 'win_pct': str(row[4]) if len(row) > 4 else '0.00%'})

        # By location
        result['by_location'] = []
        for row in stats.get('by_location', []):
            result['by_location'].append({'location': str(row[1]) if len(row) > 1 else '', 'wins': row[2] if len(row) > 2 else 0, 'losses': row[3] if len(row) > 3 else 0, 'win_pct': str(row[4]) if len(row) > 4 else '0.00%'})

        # By fight type
        result['by_fight_type'] = []
        for row in stats.get('by_fight_type', []):
            result['by_fight_type'].append({'type': str(row[1]) if len(row) > 1 else '', 'wins': row[2] if len(row) > 2 else 0, 'losses': row[3] if len(row) > 3 else 0, 'win_pct': str(row[4]) if len(row) > 4 else '0.00%'})

        # By brand
        result['by_brand'] = []
        for row in stats.get('by_brand', []):
            result['by_brand'].append({'brand': str(row[1]) if len(row) > 1 else '', 'wins': row[2] if len(row) > 2 else 0, 'losses': row[3] if len(row) > 3 else 0, 'win_pct': str(row[4]) if len(row) > 4 else '0.00%'})

        # By PPV
        result['by_ppv'] = []
        for row in stats.get('by_ppv', []):
            result['by_ppv'].append({'ppv': str(row[1]) if len(row) > 1 else '', 'wins': row[2] if len(row) > 2 else 0, 'losses': row[3] if len(row) > 3 else 0, 'win_pct': str(row[4]) if len(row) > 4 else '0.00%'})

        # Championship
        result['championship'] = []
        for row in stats.get('championship', []):
            result['championship'].append({'wins': row[-3] if len(row) >= 3 else 0, 'losses': row[-2] if len(row) >= 2 else 0, 'win_pct': str(row[-1]) if len(row) >= 1 else '0.00%'})

        # Defending title
        result['defending_title'] = []
        for row in stats.get('defending_title', []):
            result['defending_title'].append({'wins': row[-3] if len(row) >= 3 else 0, 'losses': row[-2] if len(row) >= 2 else 0, 'win_pct': str(row[-1]) if len(row) >= 1 else '0.00%'})

        # Current champion titles
        result['current_titles'] = [
            normalize_champ_name(row['Championship_Name'])
            for row in accolades_raw.get('current_titles', [])
        ]

        # Accolades — dicts with real column names so JS can display dynamically
        result['accolades'] = {
            key: [{k: _serialize(v) for k, v in row.items()} for row in rows]
            for key, rows in accolades_raw.items()
        }

        # Normalize championship names throughout accolades
        for row in result['accolades'].get('champ_reigns', []):
            row['Championship_Name'] = normalize_champ_name(row.get('Championship_Name'))
        for row in result['accolades'].get('champ_by_champ', []):
            row['Championship_Name'] = normalize_champ_name(row.get('Championship_Name'))
        for row in result['accolades'].get('holistic', []):
            if row.get('Titles_Held'):
                row['Titles_Held'] = normalize_champ_name(row['Titles_Held'])

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/leaderboard')
def api_leaderboard():
    season = request.args.get('season', '')
    try:
        if season:
            fighters = db.get_leaderboard_by_season(int(season))
        else:
            fighters = db.get_leaderboard()
        current_champs = db.get_current_champions()
        for f in fighters:
            f['titles'] = [normalize_champ_name(t) for t in current_champs.get(f['name'], [])]
        return jsonify(fighters)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/seasons')
def api_seasons():
    try:
        return jsonify(db.get_all_seasons())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/season/<int:season_id>')
def api_season(season_id):
    try:
        data = db.get_season_summary(season_id)
        # Sort rankings by win_pct descending
        rankings = data.get('rankings', [])
        def parse_pct(row):
            val = next((row[k] for k in row if 'pct' in k.lower() or '%' in k.lower() or 'percentage' in k.lower()), 0)
            try:
                return float(str(val).replace('%', ''))
            except (ValueError, TypeError):
                return 0.0
        rankings.sort(key=parse_pct, reverse=True)
        data['rankings'] = rankings
        # Normalize championship names in holistic and champ_history
        for row in data.get('holistic', []):
            if row.get('Titles_Held'):
                row['Titles_Held'] = normalize_champ_name(row['Titles_Held'])
        for row in data.get('champ_history', []):
            if row.get('Championship_Name'):
                row['Championship_Name'] = normalize_champ_name(row['Championship_Name'])
        # Serialize all values
        serialized = {}
        for key, rows in data.items():
            serialized[key] = [{k: _serialize(v) for k, v in row.items()} for row in rows]
        return jsonify(serialized)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/fights')
def api_fights():
    try:
        filters = {
            'season':       request.args.get('season', ''),
            'month':        request.args.get('month', ''),
            'fight_type':   request.args.get('fight_type', ''),
            'location':     request.args.get('location', ''),
            'ppv':          request.args.get('ppv', ''),
            'championship': request.args.get('championship', ''),
            'fighter':      request.args.get('fighter', ''),
            'brand':        request.args.get('brand', ''),
        }
        page = int(request.args.get('page', 1))
        fights_data = db.get_fight_log(filters, page=page)
        result = []
        for f in fights_data:
            rf = {k: _serialize(v) for k, v in f.items() if k != 'fighters'}
            rf['fighters'] = [{k: _serialize(v) for k, v in fi.items()} for fi in f['fighters']]
            result.append(rf)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/championships')
def api_championships():
    try:
        rows = db.get_championship_history_alltime()
        for row in rows:
            if row.get('Championship_Name'):
                row['Championship_Name'] = normalize_champ_name(row['Championship_Name'])
        return jsonify([{k: _serialize(v) for k, v in row.items()} for row in rows])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
