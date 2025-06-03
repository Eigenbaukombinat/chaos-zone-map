# Nginx Deployment für Chaos Zone Map

## Installation und Setup

### 1. Nginx Konfiguration

1. Kopieren Sie die Nginx-Konfiguration:
```bash
sudo cp nginx.conf /etc/nginx/sites-available/chaosmap
sudo ln -s /etc/nginx/sites-available/chaosmap /etc/nginx/sites-enabled/
```

2. Passen Sie die Pfade in der Konfiguration an:
   - Ersetzen Sie `/path/to/your/chaos-zone-map` mit dem tatsächlichen Pfad zu Ihrer Anwendung
   - Ersetzen Sie `map.your.domain` mit Ihrer tatsächlichen Domain

3. Testen Sie die Nginx-Konfiguration:
```bash
sudo nginx -t
```

4. Laden Sie Nginx neu:
```bash
sudo systemctl reload nginx
```

### 2. Flask-Anwendung als Service

1. Kopieren Sie die Service-Datei:
```bash
sudo cp chaosmap.service /etc/systemd/system/
```

2. Passen Sie die Pfade in der Service-Datei an:
   - Ersetzen Sie `/path/to/your/chaos-zone-map` mit dem tatsächlichen Pfad
   - Stellen Sie sicher, dass User/Group korrekt sind

3. Aktivieren und starten Sie den Service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable chaosmap.service
sudo systemctl start chaosmap.service
```

4. Überprüfen Sie den Status:
```bash
sudo systemctl status chaosmap.service
```

### 3. SSL mit Certbot

Nach der Nginx-Einrichtung können Sie SSL mit Certbot hinzufügen:

```bash
sudo certbot --nginx -d map.your.domain
```

### 4. Firewall (optional)

Stellen Sie sicher, dass die Ports 80 und 443 geöffnet sind:
```bash
sudo ufw allow 'Nginx Full'
```

## Monitoring

- Nginx Logs: `/var/log/nginx/chaosmap_*.log`
- Service Logs: `sudo journalctl -u chaosmap.service -f`

## Wichtige Hinweise

- Die Flask-Anwendung läuft auf Port 5000 (nur lokal erreichbar)
- Nginx fungiert als Reverse Proxy auf Port 80/443
- Statische Dateien werden direkt von Nginx ausgeliefert
- API-Endpunkte haben unterschiedliche Cache-Zeiten
- Proxy-Requests werden für 24h gecacht
