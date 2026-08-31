
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import sqlite3, json, os
from datetime import datetime, timezone

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "demo-change-this-secret-key")
DB = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "iot.db"))
DEMO_USER = os.environ.get("DEMO_USER", "demo")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "demo123")

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db()
    con.execute("""CREATE TABLE IF NOT EXISTS readings(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        application_name TEXT,
        device_name TEXT,
        dev_eui TEXT,
        device_profile_name TEXT,
        temperature REAL,
        humidity REAL,
        water REAL,
        pulse_conv REAL,
        water_conv REAL,
        battery REAL,
        rssi REAL,
        snr REAL,
        gateway_id TEXT,
        raw_json TEXT
    )""")
    con.commit()
    con.close()

def insert_payload(payload):
    info = payload.get("deviceInfo") or {}
    obj = payload.get("object") or {}
    rx = (payload.get("rxInfo") or [{}])[0] or {}
    row = {
        "ts": payload.get("time") or datetime.now(timezone.utc).isoformat(),
        "application_name": info.get("applicationName"),
        "device_name": info.get("deviceName"),
        "dev_eui": info.get("devEui"),
        "device_profile_name": info.get("deviceProfileName"),
        "temperature": obj.get("temperature"),
        "humidity": obj.get("humidity"),
        "water": obj.get("water"),
        "pulse_conv": obj.get("pulse_conv"),
        "water_conv": obj.get("water_conv"),
        "battery": obj.get("battery"),
        "rssi": rx.get("rssi"),
        "snr": rx.get("snr"),
        "gateway_id": rx.get("gatewayId"),
        "raw_json": json.dumps(payload, ensure_ascii=False),
    }
    con = db()
    con.execute("""INSERT INTO readings(
        ts,application_name,device_name,dev_eui,device_profile_name,
        temperature,humidity,water,pulse_conv,water_conv,battery,rssi,snr,gateway_id,raw_json
    ) VALUES(
        :ts,:application_name,:device_name,:dev_eui,:device_profile_name,
        :temperature,:humidity,:water,:pulse_conv,:water_conv,:battery,:rssi,:snr,:gateway_id,:raw_json
    )""", row)
    con.commit()
    con.close()

def seed_demo():
    con = db()
    n = con.execute("SELECT COUNT(*) n FROM readings").fetchone()["n"]
    con.close()
    if n:
        return
    insert_payload({
        "time":"2026-08-29T03:00:00+00:00",
        "deviceInfo":{"applicationName":"Prueba Pulso Milesight","deviceProfileName":"Milesight Neering EM300-DI","deviceName":"PUL 1","devEui":"24e1241360605391"},
        "object":{"pulse_conv":1,"water_conv":100,"water":480700},
        "rxInfo":[{"gatewayId":"c0ba1ffffe003172","rssi":-113,"snr":-13.8}]
    })
    insert_payload({
        "time":"2026-08-29T03:01:16+00:00",
        "deviceInfo":{"applicationName":"Prueba Pulso Milesight","deviceProfileName":"Milesight Neering EM300-DI","deviceName":"PUL 1","devEui":"24e1241360605391"},
        "object":{"battery":95,"temperature":16.3,"humidity":58.0},
        "rxInfo":[{"gatewayId":"c0ba1ffffe003172","rssi":-108,"snr":-15.2}]
    })

@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok":False,"error":"JSON requerido"}),400
    insert_payload(payload)
    return jsonify({"ok":True})

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        if request.form.get("username")==DEMO_USER and request.form.get("password")==DEMO_PASSWORD:
            session["auth"] = True
            return redirect(url_for("home"))
        return render_template("login.html", error="Usuario o contraseña incorrectos.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
def home():
    if session.get("auth") is not True:
        return redirect(url_for("login"))
    return render_template("index.html")

def latest_non_null(con, dev_eui, field):
    row = con.execute(f"""SELECT {field} value, ts FROM readings
        WHERE dev_eui=? AND {field} IS NOT NULL ORDER BY id DESC LIMIT 1""",(dev_eui,)).fetchone()
    return (row["value"],row["ts"]) if row else (None,None)

@app.route("/api/devices")
def devices():
    if session.get("auth") is not True:
        return jsonify({"error":"unauthorized"}),401
    con = db()
    devs = con.execute("SELECT dev_eui, MAX(id) max_id FROM readings WHERE dev_eui IS NOT NULL GROUP BY dev_eui").fetchall()
    fields = ["temperature","humidity","water","pulse_conv","water_conv","battery","rssi","snr","gateway_id"]
    out=[]
    for d in devs:
        meta = con.execute("SELECT * FROM readings WHERE id=?",(d["max_id"],)).fetchone()
        item={"dev_eui":d["dev_eui"],"device_name":meta["device_name"],"application_name":meta["application_name"],
              "device_profile_name":meta["device_profile_name"],"last_seen":meta["ts"]}
        for f in fields:
            item[f], item[f+"_ts"] = latest_non_null(con,d["dev_eui"],f)
        if item["water"] is not None:
            item["water_m3"] = item["water"]/1000
        out.append(item)
    con.close()
    return jsonify(out)

@app.route("/api/health")
def health():
    return jsonify({"ok":True})

init_db()
seed_demo()

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)),debug=True)
