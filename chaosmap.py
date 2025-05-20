from flask import Flask, render_template, Response, abort, request, send_file, jsonify
import requests
import gzip
import os
import time
import threading

PROXY_TARGETS = {
    "tiles": "https://tiles.openfreemap.org/",
    "maplibre-gl": "https://unpkg.com/maplibre-gl@5.1.0/",
    "spaceapi": "https://api.spaceapi.io/"
}

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "scripts")

# Cache-Variablen
_spaceapi_cache = {
    "timestamp": 0,
    "data": None
}
_cache_lock = threading.Lock()

PROXY_CACHE = {}
PROXY_CACHE_LOCK = threading.Lock()
PROXY_CACHE_DURATION = 24 * 60 * 60  # 24 Stunden in Sekunden

app = Flask(__name__)

@app.route("/")
def index():
    return render_template('index.html', person="")


@app.route("/scripts/<path:filename>")
def scripts_with_url(filename):
    file_path = os.path.join(SCRIPTS_DIR, filename)
    if not os.path.isfile(file_path):
        abort(404, description="Datei nicht gefunden")

    # Für json, js, css: [URL] ersetzen
    if filename.endswith(('.json', '.js', '.css')):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        host_url = request.host_url.rstrip('/')
        content = content.replace("[URL]", host_url)
        if filename.endswith('.json'):
            mimetype = "application/json"
        elif filename.endswith('.js'):
            mimetype = "application/javascript"
        elif filename.endswith('.css'):
            mimetype = "text/css"
        else:
            mimetype = "text/plain"
        return Response(content, mimetype=mimetype)
    else:
        # Alle anderen Dateitypen direkt ausliefern
        return send_file(file_path)
    
@app.route("/spaceapi")
def spaceapi_filtered():
    url = "https://api.spaceapi.io/"
    now = time.time()

    with _cache_lock:
        # Prüfen, ob Cache älter als 60 Sekunden ist
        if _spaceapi_cache["data"] is None or now - _spaceapi_cache["timestamp"] > 60:
            try:
                resp = requests.get(url, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                _spaceapi_cache["data"] = data
                _spaceapi_cache["timestamp"] = now
            except Exception as e:
                abort(502, description=f"Fehler beim Abrufen der Daten: {e}")
        else:
            data = _spaceapi_cache["data"]

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

    cache_key = f"{proxy}:{file}"
    now = time.time()

    if is_cacheable(file):
        with PROXY_CACHE_LOCK:
            cache_entry = PROXY_CACHE.get(cache_key)
            if cache_entry and now - cache_entry['timestamp'] < PROXY_CACHE_DURATION:
                # Aus Cache zurückgeben
                cached_resp = cache_entry['response']
                return Response(
                    cached_resp['body'],
                    status=cached_resp['status'],
                    headers=cached_resp['headers']
                )

    try:
        forward_headers = build_forward_headers()
        resp = requests.get(target_url, headers=forward_headers, stream=True)
        flask_resp = format_proxy_response(resp, proxy, proxy_base_url, base_url.rstrip('/'))

        if is_cacheable(file):
            # Antwort für 24h cachen
            with PROXY_CACHE_LOCK:
                PROXY_CACHE[cache_key] = {
                    'timestamp': now,
                    'response': {
                        'body': flask_resp.get_data(),
                        'status': flask_resp.status_code,
                        'headers': flask_resp.headers
                    }
                }
        return flask_resp
    except requests.RequestException as e:
        abort(502, description=f"Fehler beim Weiterleiten: {e}")