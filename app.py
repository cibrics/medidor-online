from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import sqlite3
import json
import os
from datetime import datetime, timezone, timedelta


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "demo-change-this-secret-key"
)

DB = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(__file__), "iot.db")
)

DEMO_USER = os.environ.get("DEMO_USER", "demo")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "demo123")


# ================================================================
# CONEXIÓN A BASE DE DATOS
# ================================================================

def db():

    con = sqlite3.connect(DB)

    con.row_factory = sqlite3.Row

    return con



# ================================================================
# CREACIÓN DE TABLA
# ================================================================

def init_db():

    con = db()

    con.execute("""
    CREATE TABLE IF NOT EXISTS readings(

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
# GUARDAR DATOS RECIBIDOS DESDE CHIRPSTACK
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
            ),
    }


    con = db()


    con.execute("""
    INSERT INTO readings(

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

    VALUES(

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
# DATOS DEMOSTRATIVOS
#
# Sólo se crean si la base de datos está completamente vacía.
# ================================================================

def seed_demo():

    con = db()

    n = con.execute(
        "SELECT COUNT(*) n FROM readings"
    ).fetchone()["n"]

    con.close()


    if n:

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

            "pulse_conv": 1,

            "water_conv": 100,

            "water": 480700
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
#
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

        if (
            request.form.get("username")
            == DEMO_USER

            and

            request.form.get("password")
            == DEMO_PASSWORD
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
# PÁGINA PRINCIPAL
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
# Permite conservar, por ejemplo, la última temperatura aunque
# el siguiente uplink sólo contenga agua.
# ================================================================

def latest_non_null(
    con,
    dev_eui,
    field
):

    row = con.execute(

        f"""
        SELECT
            {field} value,
            ts

        FROM readings

        WHERE
            dev_eui=?
            AND {field} IS NOT NULL

        ORDER BY id DESC

        LIMIT 1
        """,

        (dev_eui,)

    ).fetchone()


    return (

        (row["value"], row["ts"])

        if row

        else (None, None)

    )



# ================================================================
# CONVERSIÓN SEGURA DE FECHA
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

    except Exception:

        return None



# ================================================================
# CONSUMO ÚLTIMAS 24 HORAS
#
# El sensor entrega un contador acumulado.
#
# Esta función calcula:
#
# lectura actual
# -
# lectura aproximadamente 24 horas atrás
#
# El resultado se entrega en m³.
# ================================================================

def calculate_water_24h(
    con,
    dev_eui
):

    # ------------------------------------------------------------
    # Última lectura válida de agua
    # ------------------------------------------------------------

    latest = con.execute("""

        SELECT
            water,
            ts

        FROM readings

        WHERE
            dev_eui=?
            AND water IS NOT NULL

        ORDER BY id DESC

        LIMIT 1

    """, (dev_eui,)).fetchone()


    if not latest:

        return None


    latest_time = parse_datetime(
        latest["ts"]
    )


    if not latest_time:

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
    # Buscamos todas las lecturas anteriores de agua.
    #
    # Elegimos la lectura temporalmente más cercana a 24 horas
    # antes de la lectura actual.
    # ------------------------------------------------------------

rows = con.execute("""

    SELECT
        water,
        ts

    FROM readings

    WHERE
        dev_eui=?
        AND water IS NOT NULL
        AND ts != ?

    ORDER BY id DESC

""", (

    dev_eui,
    latest["ts"]

)).fetchall()


    best_row = None

    best_difference = None


    for row in rows:

        row_time = parse_datetime(
            row["ts"]
        )


        if not row_time:

            continue


        difference = abs(
            (
                row_time
                - target_time
            ).total_seconds()
        )


        if (
            best_difference is None
            or difference < best_difference
        ):

            best_row = row

            best_difference = difference


    if not best_row:

        return None


    # ------------------------------------------------------------
    # Para evitar calcular "24 horas" con dos lecturas que sólo
    # están separadas por minutos u horas, exigimos que exista
    # suficiente historial.
    #
    # Aceptamos una lectura de referencia ubicada entre
    # 20 y 28 horas respecto de la lectura actual.
    # ------------------------------------------------------------

    previous_time = parse_datetime(
        best_row["ts"]
    )


    elapsed_hours = (

        latest_time
        - previous_time

    ).total_seconds() / 3600


    if (
        elapsed_hours < 20
        or elapsed_hours > 28
    ):

        return None


    current_water = latest["water"]

    previous_water = best_row["water"]


    if (
        current_water is None
        or previous_water is None
    ):

        return None


    consumption_liters = (
        current_water
        - previous_water
    )


    # Si el contador se reinició o llegó un dato inválido,
    # no mostramos consumo negativo.

    if consumption_liters < 0:

        return None


    consumption_m3 = (
        consumption_liters / 1000
    )


    return round(
        consumption_m3,
        3
    )



# ================================================================
# API DISPOSITIVOS
# ================================================================

@app.route("/api/devices")

def devices():

    if session.get("auth") is not True:

        return jsonify({
            "error":
                "unauthorized"
        }), 401


    con = db()


    devs = con.execute("""

        SELECT
            dev_eui,
            MAX(id) max_id

        FROM readings

        WHERE
            dev_eui IS NOT NULL

        GROUP BY
            dev_eui

    """).fetchall()


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


    for d in devs:


        meta = con.execute(

            """
            SELECT *

            FROM readings

            WHERE id=?
            """,

            (d["max_id"],)

        ).fetchone()


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

        for f in fields:

            (
                item[f],
                item[f + "_ts"]

            ) = latest_non_null(

                con,
                d["dev_eui"],
                f
            )


        # --------------------------------------------------------
        # Lectura acumulada en m³
        # --------------------------------------------------------

        if item["water"] is not None:

            item["water_m3"] = (
                item["water"] / 1000
            )


        # --------------------------------------------------------
        # NUEVO:
        # consumo real de las últimas 24 horas
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
        "ok": True
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

        host="0.0.0.0",

        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),

        debug=True

    )
