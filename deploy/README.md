# Deploy

Target: `/opt/report-check-bot` on the app server.

```bash
# sync code, then:
python3 -m venv /opt/report-check-bot/.venv
/opt/report-check-bot/.venv/bin/pip install -r requirements.txt
# put secrets into /opt/report-check-bot/.env and secrets/bp-sheets-sa.json
cp deploy/report-check-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now report-check-bot.service
systemctl status report-check-bot.service
journalctl -u report-check-bot.service -f
```
