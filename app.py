from flask import Flask, render_template, request, jsonify
import db
import os
import re

app = Flask(__name__)

# Cache autocomplete lists at startup (they don't change often)
_autocomplete_cache = {}


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


# ---------- Page Routes ----------

@app.route('/')
def index():
    fighters = get_autocomplete_data('fighters')
    fighter_cards = [{'name': f, 'filename': fighter_to_filename(f)} for f in fighters]
    return render_template('index.html', fighters=fighter_cards)


@app.route('/head2head')
def head2head():
    return render_template('head2head.html')


@app.route('/fighter/<name>')
def fighter_profile(name):
    return render_template('fighter.html', fighter_name=name, filename=fighter_to_filename(name))


@app.route('/leaderboard')
def leaderboard():
    return render_template('leaderboard.html')


@app.route('/graphs')
def graphs():
    fighters = get_autocomplete_data('fighters')
    return render_template('graphs.html', fighters=fighters)


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


@app.route('/api/fighter/<name>')
def api_fighter(name):
    try:
        stats = db.get_fighter_career_stats(name)
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

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/leaderboard')
def api_leaderboard():
    try:
        fighters = db.get_leaderboard()
        return jsonify(fighters)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
