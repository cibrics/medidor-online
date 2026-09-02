from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import sqlite3, json, os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "demo-change-this-secret-key")
DB = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "iot.db"))
DEMO_USER = os.environ.get("DEMO_USER", "demo")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "demo123")
CHILE_TZ = ZoneInfo("America/Santiago")


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
        if request.form.get("username") == DEMO_USER and request.form.get("password") == DEMO_PASSWORD:
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


def parse_datetime(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def calculate_water_24h(con, dev_eui):
    latest = con.execute("""SELECT water, ts FROM readings
        WHERE dev_eui=? AND water IS NOT NULL ORDER BY id DESC LIMIT 1""", (dev_eui,)).fetchone()
    if not latest:
        return None
    latest_time = parse_datetime(latest["ts"])
    if latest_time is None:
        return None
    target_time = latest_time - timedelta(hours=24)
    rows = con.execute("""SELECT water, ts FROM readings
        WHERE dev_eui=? AND water IS NOT NULL AND ts != ? ORDER BY id DESC""", (dev_eui, latest["ts"])).fetchall()
    best_row = None
    best_difference = None
    for row in rows:
        row_time = parse_datetime(row["ts"])
        if row_time is None or row_time >= latest_time:
            continue
        difference = abs((row_time-target_time).total_seconds())
        if best_difference is None or difference < best_difference:
            best_row = row
            best_difference = difference
    if best_row is None:
        return None
    previous_time = parse_datetime(best_row["ts"])
    elapsed_hours = (latest_time-previous_time).total_seconds()/3600
    if elapsed_hours < 20 or elapsed_hours > 28:
        return None
    consumption_liters = latest["water"] - best_row["water"]
    if consumption_liters < 0:
        return None
    return round(consumption_liters/1000, 3)


def add_months(year, month, delta):
    absolute = year * 12 + (month - 1) + delta
    return absolute // 12, absolute % 12 + 1


def analytics_for_device(con, dev_eui):
    rows = con.execute("""SELECT water, ts FROM readings
        WHERE dev_eui=? AND water IS NOT NULL ORDER BY id ASC""", (dev_eui,)).fetchall()

    parsed = []
    for row in rows:
        dt = parse_datetime(row["ts"])
        if dt is None:
            continue
        parsed.append({"water":row["water"], "dt_cl":dt.astimezone(CHILE_TZ)})

    now_cl = datetime.now(timezone.utc).astimezone(CHILE_TZ)
    next_y, next_m = add_months(now_cl.year, now_cl.month, 1)
    first_this = datetime(now_cl.year, now_cl.month, 1, tzinfo=CHILE_TZ)
    first_next = datetime(next_y, next_m, 1, tzinfo=CHILE_TZ)
    total_days = (first_next.date() - first_this.date()).days
    daily_map = {day:0.0 for day in range(1,total_days+1)}

    rolling = []
    for offset in range(-11,1):
        y,m = add_months(now_cl.year, now_cl.month, offset)
        rolling.append({"key":f"{y:04d}-{m:02d}","year":y,"month":m,"value":0.0,"has_data":False})
    rolling_map = {x["key"]:x for x in rolling}

    for previous,current in zip(parsed, parsed[1:]):
        delta_liters = current["water"] - previous["water"]
        if delta_liters < 0:
            continue
        delta_m3 = delta_liters/1000.0
        dt = current["dt_cl"]
        key = f"{dt.year:04d}-{dt.month:02d}"
        if key in rolling_map:
            rolling_map[key]["value"] += delta_m3
            rolling_map[key]["has_data"] = True
        if dt.year == now_cl.year and dt.month == now_cl.month:
            daily_map[dt.day] += delta_m3

    current_key = f"{now_cl.year:04d}-{now_cl.month:02d}"
    current = rolling_map[current_key]
    current_month_m3 = round(current["value"],3) if current["has_data"] else None
    daily = [{"day":day,"value":round(daily_map[day],3)} for day in range(1,total_days+1)]
    month_names = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
    monthly = [{"label":f"{month_names[x['month']-1]} {str(x['year'])[-2:]}","value":round(x["value"],3) if x["has_data"] else None} for x in rolling]
    return {"current_month_m3":current_month_m3,"daily_current_month":daily,"rolling_12_months":monthly}


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
        if not meta:
            continue
        item={"dev_eui":d["dev_eui"],"device_name":meta["device_name"],"application_name":meta["application_name"],
              "device_profile_name":meta["device_profile_name"],"last_seen":meta["ts"]}
        for f in fields:
            item[f], item[f+"_ts"] = latest_non_null(con,d["dev_eui"],f)
        item["water_m3"] = round(item["water"]/1000,3) if item["water"] is not None else None
        item["water_24h_m3"] = calculate_water_24h(con,d["dev_eui"])
        out.append(item)
    con.close()
    return jsonify(out)


@app.route("/api/analytics/<dev_eui>")
def analytics(dev_eui):
    if session.get("auth") is not True:
        return jsonify({"error":"unauthorized"}),401
    con = db()
    result = analytics_for_device(con, dev_eui)
    con.close()
    return jsonify(result)


@app.route("/api/health")
def health():
    return jsonify({"ok":True})


init_db()
seed_demo()

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)),debug=True)
