from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    redirect,
    url_for,
    session
)

import sqlite3
import json
import os

from datetime import datetime, timezone, timedelta


# ================================================================
# CONFIGURACIÓN GENERAL
# ================================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "demo-change-this-secret-key"
)

DB = os.environ.get(
    "DB_PATH",
    os.path.join(
        os.path.dirname(__file__),
        "iot.db"
    )
)

DEMO_USER = os.environ.get(
    "DEMO_USER",
    "demo"
)

DEMO_PASSWORD = os.environ.get(
    "DEMO_PASSWORD",
    "demo123"
)


# ================================================================
# BASE DE DATOS
# ================================================================

def db():

    con = sqlite3.connect(DB)

    con.row_factory = sqlite3.Row

    return con


# ================================================================
# CREAR TABLA
# ================================================================

def init_db():

    con = db()

    con.execute("""
        CREATE TABLE IF NOT EXISTS readings (

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
        )
    """)

    con.commit()

    con.close()


# ================================================================
# GUARDAR PAYLOAD RECIBIDO DESDE CHIRPSTACK
# ================================================================

def insert_payload(payload):

    info = payload.get("deviceInfo") or {}

    obj = payload.get("object") or {}

    rx = (payload.get("rxInfo") or [{}])[0] or {}


    row = {

        "ts":
            payload.get("time")
            or datetime.now(timezone.utc).isoformat(),

        "application_name":
            info.get("applicationName"),

        "device_name":
            info.get("deviceName"),

        "dev_eui":
            info.get("devEui"),

        "device_profile_name":
            info.get("deviceProfileName"),

        "temperature":
            obj.get("temperature"),

        "humidity":
            obj.get("humidity"),

        "water":
            obj.get("water"),

        "pulse_conv":
            obj.get("pulse_conv"),

        "water_conv":
            obj.get("water_conv"),

        "battery":
            obj.get("battery"),

        "rssi":
            rx.get("rssi"),

        "snr":
            rx.get("snr"),

        "gateway_id":
            rx.get("gatewayId"),

        "raw_json":
            json.dumps(
                payload,
                ensure_ascii=False
            )
    }


    con = db()


    con.execute("""
        INSERT INTO readings (

            ts,

            application_name,

            device_name,

            dev_eui,

            device_profile_name,

            temperature,

            humidity,

            water,

            pulse_conv,

            water_conv,

            battery,

            rssi,

            snr,

            gateway_id,

            raw_json

        )

        VALUES (

            :ts,

            :application_name,

            :device_name,

            :dev_eui,

            :device_profile_name,

            :temperature,

            :humidity,

            :water,

            :pulse_conv,

            :water_conv,

            :battery,

            :rssi,

            :snr,

            :gateway_id,

            :raw_json
        )
    """, row)


    con.commit()

    con.close()


# ================================================================
# DATOS DEMO
#
# Sólo se crean si la base está completamente vacía.
# ================================================================

def seed_demo():

    con = db()

    row = con.execute(
        "SELECT COUNT(*) AS n FROM readings"
    ).fetchone()

    con.close()


    if row["n"] > 0:

        return


    # ------------------------------------------------------------
    # Lectura acumulada de agua
    # ------------------------------------------------------------

    insert_payload({

        "time":
            "2026-08-29T03:00:00+00:00",

        "deviceInfo": {

            "applicationName":
                "Prueba Pulso Milesight",

            "deviceProfileName":
                "Milesight Neering EM300-DI",

            "deviceName":
                "PUL 1",

            "devEui":
                "24e1241360605391"
        },

        "object": {

            "pulse_conv":
                1,

            "water_conv":
                100,

            "water":
                480700
        },

        "rxInfo": [{

            "gatewayId":
                "c0ba1ffffe003172",

            "rssi":
                -113,

            "snr":
                -13.8
        }]
    })


    # ------------------------------------------------------------
    # Temperatura / humedad / batería
    # ------------------------------------------------------------

    insert_payload({

        "time":
            "2026-08-29T03:01:16+00:00",

        "deviceInfo": {

            "applicationName":
                "Prueba Pulso Milesight",

            "deviceProfileName":
                "Milesight Neering EM300-DI",

            "deviceName":
                "PUL 1",

            "devEui":
                "24e1241360605391"
        },

        "object": {

            "battery":
                95,

            "temperature":
                16.3,

            "humidity":
                58.0
        },

        "rxInfo": [{

            "gatewayId":
                "c0ba1ffffe003172",

            "rssi":
                -108,

            "snr":
                -15.2
        }]
    })


# ================================================================
# WEBHOOK
#
# ChirpStack debe enviar los POST a:
#
# https://TU-DOMINIO.onrender.com/webhook
# ================================================================

@app.route(
    "/webhook",
    methods=["POST"]
)

def webhook():

    payload = request.get_json(
        silent=True
    )


    if not isinstance(payload, dict):

        return jsonify({

            "ok":
                False,

            "error":
                "JSON requerido"

        }), 400


    insert_payload(payload)


    return jsonify({
        "ok": True
    })


# ================================================================
# LOGIN
# ================================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)

def login():

    if request.method == "POST":

        username = request.form.get(
            "username"
        )

        password = request.form.get(
            "password"
        )


        if (
            username == DEMO_USER
            and
            password == DEMO_PASSWORD
        ):

            session["auth"] = True

            return redirect(
                url_for("home")
            )


        return render_template(

            "login.html",

            error=
            "Usuario o contraseña incorrectos."
        )


    return render_template(
        "login.html"
    )


# ================================================================
# CERRAR SESIÓN
# ================================================================

@app.route("/logout")

def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# ================================================================
# DASHBOARD
# ================================================================

@app.route("/")

def home():

    if session.get("auth") is not True:

        return redirect(
            url_for("login")
        )


    return render_template(
        "index.html"
    )


# ================================================================
# ÚLTIMO VALOR NO NULO
#
# Ejemplo:
# si un uplink trae sólo temperatura y otro trae agua,
# esta función permite conservar el último valor válido de cada uno.
# ================================================================

def latest_non_null(
    con,
    dev_eui,
    field
):

    row = con.execute(

        f"""
        SELECT
            {field} AS value,
            ts

        FROM readings

        WHERE
            dev_eui = ?
            AND {field} IS NOT NULL

        ORDER BY id DESC

        LIMIT 1
        """,

        (dev_eui,)

    ).fetchone()


    if not row:

        return None, None


    return (
        row["value"],
        row["ts"]
    )


# ================================================================
# CONVERSIÓN DE FECHA
# ================================================================

def parse_datetime(value):

    if not value:

        return None


    try:

        return datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00"
            )
        )

    except (ValueError, TypeError):

        return None


# ================================================================
# CONSUMO ÚLTIMAS 24 HORAS
#
# El EM300-DI entrega un valor acumulado de agua.
#
# Cálculo:
#
# lectura acumulada actual
# -
# lectura acumulada cercana a 24 horas antes
#
# Resultado:
# consumo de agua de las últimas 24 horas en m³
# ================================================================

def calculate_water_24h(
    con,
    dev_eui
):

    # ------------------------------------------------------------
    # Obtener última lectura válida de agua
    # ------------------------------------------------------------

    latest = con.execute("""

        SELECT
            water,
            ts

        FROM readings

        WHERE
            dev_eui = ?
            AND water IS NOT NULL

        ORDER BY id DESC

        LIMIT 1

    """, (

        dev_eui,

    )).fetchone()


    if not latest:

        return None


    latest_time = parse_datetime(
        latest["ts"]
    )


    if latest_time is None:

        return None


    # ------------------------------------------------------------
    # Momento objetivo:
    # 24 horas antes de la última lectura
    # ------------------------------------------------------------

    target_time = (
        latest_time
        - timedelta(hours=24)
    )


    # ------------------------------------------------------------
    # Recuperar lecturas anteriores
    # ------------------------------------------------------------

    rows = con.execute("""

        SELECT
            water,
            ts

        FROM readings

        WHERE
            dev_eui = ?
            AND water IS NOT NULL
            AND ts != ?

        ORDER BY id DESC

    """, (

        dev_eui,
        latest["ts"]

    )).fetchall()


    if not rows:

        return None


    # ------------------------------------------------------------
    # Buscar la lectura temporalmente más cercana
    # a exactamente 24 horas atrás.
    # ------------------------------------------------------------

    best_row = None

    best_difference = None


    for row in rows:

        row_time = parse_datetime(
            row["ts"]
        )


        if row_time is None:

            continue


        # Sólo consideramos lecturas anteriores
        # a la lectura actual.

        if row_time >= latest_time:

            continue


        difference = abs(

            (
                row_time
                - target_time
            ).total_seconds()

        )


        if (
            best_difference is None
            or
            difference < best_difference
        ):

            best_row = row

            best_difference = difference


    if best_row is None:

        return None


    previous_time = parse_datetime(
        best_row["ts"]
    )


    if previous_time is None:

        return None


    # ------------------------------------------------------------
    # Validar que realmente exista aproximadamente
    # un día de historial.
    #
    # Aceptamos una lectura ubicada entre
    # 20 y 28 horas antes de la lectura actual.
    # ------------------------------------------------------------

    elapsed_hours = (

        latest_time
        - previous_time

    ).total_seconds() / 3600


    if (
        elapsed_hours < 20
        or
        elapsed_hours > 28
    ):

        return None


    current_water = latest["water"]

    previous_water = best_row["water"]


    if (
        current_water is None
        or
        previous_water is None
    ):

        return None


    # ------------------------------------------------------------
    # Diferencia entre lecturas
    #
    # El valor water que estamos recibiendo está siendo interpretado
    # en litros. Por eso dividimos por 1000 para entregar m³.
    # ------------------------------------------------------------

    consumption_liters = (
        current_water
        - previous_water
    )


    # ------------------------------------------------------------
    # Protección frente a reinicios del contador
    # o valores inconsistentes.
    # ------------------------------------------------------------

    if consumption_liters < 0:

        return None


    consumption_m3 = (
        consumption_liters
        / 1000
    )


    return round(
        consumption_m3,
        3
    )


# ================================================================
# API DE DISPOSITIVOS
# ================================================================

@app.route("/api/devices")

def devices():

    if session.get("auth") is not True:

        return jsonify({

            "error":
                "unauthorized"

        }), 401


    con = db()


    # ------------------------------------------------------------
    # Obtener dispositivos conocidos
    # ------------------------------------------------------------

    devs = con.execute("""

        SELECT
            dev_eui,
            MAX(id) AS max_id

        FROM readings

        WHERE
            dev_eui IS NOT NULL

        GROUP BY
            dev_eui

    """).fetchall()


    # ------------------------------------------------------------
    # Campos cuyo último valor válido queremos conservar
    # ------------------------------------------------------------

    fields = [

        "temperature",

        "humidity",

        "water",

        "pulse_conv",

        "water_conv",

        "battery",

        "rssi",

        "snr",

        "gateway_id"
    ]


    out = []


    # ------------------------------------------------------------
    # Construir respuesta de cada dispositivo
    # ------------------------------------------------------------

    for d in devs:

        meta = con.execute("""

            SELECT *

            FROM readings

            WHERE id = ?

        """, (

            d["max_id"],

        )).fetchone()


        if not meta:

            continue


        item = {

            "dev_eui":
                d["dev_eui"],

            "device_name":
                meta["device_name"],

            "application_name":
                meta["application_name"],

            "device_profile_name":
                meta["device_profile_name"],

            "last_seen":
                meta["ts"]
        }


        # --------------------------------------------------------
        # Último valor válido de cada variable
        # --------------------------------------------------------

        for field in fields:

            value, value_ts = latest_non_null(

                con,

                d["dev_eui"],

                field
            )


            item[field] = value

            item[
                field + "_ts"
            ] = value_ts


        # --------------------------------------------------------
        # Lectura acumulada total en m³
        # --------------------------------------------------------

        if item["water"] is not None:

            item["water_m3"] = round(

                item["water"]
                / 1000,

                3
            )

        else:

            item["water_m3"] = None


        # --------------------------------------------------------
        # Consumo calculado últimas 24 horas
        # --------------------------------------------------------

        item["water_24h_m3"] = (

            calculate_water_24h(

                con,

                d["dev_eui"]
            )
        )


        out.append(item)


    con.close()


    return jsonify(out)


# ================================================================
# HEALTH CHECK
# ================================================================

@app.route("/api/health")

def health():

    return jsonify({

        "ok":
            True

    })


# ================================================================
# INICIALIZACIÓN
# ================================================================

init_db()

seed_demo()


# ================================================================
# EJECUCIÓN LOCAL
# ================================================================

if __name__ == "__main__":

    app.run(

        host=
            "0.0.0.0",

        port=
            int(
                os.environ.get(
                    "PORT",
                    5000
                )
            ),

        debug=
            True
    )
