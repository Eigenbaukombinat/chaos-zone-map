from flask import Flask, render_template, Response, abort, request, send_file, jsonify
from flask_caching import Cache
import requests
import gzip
import os
from scripts import MAP_JS, MAPSTYLE_JSON
PROXY_TARGETS = {
    "tiles": "https://tiles.openfreemap.org/",
    "maplibre-gl": "https://unpkg.com/maplibre-gl@5.1.0/",
}

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "scripts")

app = Flask(__name__)
app.config['CACHE_TYPE'] = 'simple'  # Für einfaches In-Memory-Caching
cache = Cache(app)

@app.route("/")
def index():
    return render_template('index.html', person="")


@app.route("/scripts/<path:filename>")
def scripts_with_url(filename):
    if filename == 'mapstyle.json':
        content = MAPSTYLE_JSON
        mimetype = "application/json"
    elif filename == 'map.js':
        content = MAP_JS
        mimetype = "application/javascript"
    else:
        abort(404, "Invalid filename")
    
    host_url = 'https://map.chaoszone.cz'
    content = content.replace("[URL]", host_url)
    return Response(content, mimetype=mimetype)


    
@app.route("/spaceapi")
@cache.cached(timeout=60)  # Cache für 60 Sekunden
def spaceapi_filtered():
    url = "https://api.spaceapi.io/"
    
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        abort(502, description=f"Fehler beim Abrufen der Daten: {e}")

    # Filter anwenden
    filtered = [
        entry for entry in data
        if (
            isinstance(entry, dict)
            and "data" in entry
            and isinstance(entry["data"], dict)
            and "ext_habitat" in entry["data"]
            and str(entry["data"]["ext_habitat"]).lower() == "chaoszone"
        )
    ]
    return jsonify(filtered)


@app.route("/proxy/<proxy>")
def proxy_index_route(proxy):
    return proxy_route(proxy, "")

def build_forward_headers():
    headers = {}
    protocol = "https" if request.environ.get('HTTPS', '').lower() == 'on' else "http"
    host = request.environ.get('HTTP_HOST', '')
    headers['Origin'] = f"{protocol}://{host}"
    header_map = {
        'HTTP_RANGE': 'Range',
        'HTTP_ACCEPT': 'Accept',
        'HTTP_ACCEPT_ENCODING': 'Accept-Encoding',
        'HTTP_X_PLAYBACK_SESSION_ID': 'X-Playback-Session-Id',
        'HTTP_IF_RANGE': 'If-Range'
    }
    for env_name, header_name in header_map.items():
        value = request.environ.get(env_name)
        if value:
            headers[header_name] = value
    return headers

def gunzip(data: bytes) -> bytes:
    # Entpackt gzip-komprimierte Daten
    return gzip.decompress(data)

def format_proxy_response(resp, proxy_name, proxy_base_url, destination_url):
    # Header kopieren
    headers = dict(resp.headers)
    content_type = headers.get('content-type', '')
    content_encoding = headers.get('content-encoding', '')
    body = resp.content

    # JSON-Antworten bearbeiten
    if content_type.startswith('application/json'):
        if content_encoding == 'gzip':
            body = gunzip(body)
            headers.pop('content-encoding', None)
        # URL im Body ersetzen
        body = body.replace(destination_url.encode(), f"{proxy_base_url}/{proxy_name}".encode())

    # Location-Header anpassen
    if 'location' in headers:
        location = headers['location']
        location = location.replace(destination_url, f"{proxy_base_url}/{proxy_name}")
        if location.startswith('/'):
            location = f"{proxy_base_url}/{proxy_name}{location}"
        headers['location'] = location

    # Nicht erlaubte Header entfernen
    excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
    response_headers = [(k, v) for k, v in headers.items() if k.lower() not in excluded_headers]

    return Response(body, status=resp.status_code, headers=response_headers)

def is_cacheable(file):
    return file.endswith(('.json', '.js', '.css'))

@app.route("/proxy/<proxy>/<path:file>")
def proxy_route(proxy, file):
    base_url = PROXY_TARGETS.get(proxy)
    if not base_url:
        abort(404, description="Proxy nicht gefunden")
    target_url = base_url + file
    proxy_base_url = request.url_root.rstrip('/')

    # Für cacheable Dateien, Cache prüfen
    if is_cacheable(file):
        cache_key = f"proxy_{proxy}_{file}"
        cached_response = cache.get(cache_key)
        if cached_response:
            return Response(
                cached_response['body'],
                status=cached_response['status'],
                headers=cached_response['headers']
            )

    try:
        forward_headers = build_forward_headers()
        resp = requests.get(target_url, headers=forward_headers, stream=True, timeout=10)
        flask_resp = format_proxy_response(resp, proxy, proxy_base_url, base_url.rstrip('/'))

        if is_cacheable(file):
            # Antwort für 24h cachen
            cache_key = f"proxy_{proxy}_{file}"
            cache.set(cache_key, {
                'body': flask_resp.get_data(),
                'status': flask_resp.status_code,
                'headers': dict(flask_resp.headers)
            }, timeout=24*60*60)  # 24 Stunden
            
        return flask_resp
    except requests.RequestException as e:
        abort(502, description=f"Fehler beim Weiterleiten: {e}")
