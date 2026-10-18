from flask import Flask, request, jsonify
import time
import random
import os

app = Flask(__name__)

REQUEST_COUNT = 0


@app.route("/api/send-sms", methods=["POST"])
def send_sms():
    global REQUEST_COUNT
    REQUEST_COUNT += 1

    data = request.get_json()
    phone = data.get("phone", "")

    if not phone or len(phone) < 10:
        return jsonify({"status": "error", "message": "Invalid phone"}), 400

    print(f"[{time.strftime('%H:%M:%S')}] SMS to {phone} | Request #{REQUEST_COUNT}")
    time.sleep(random.uniform(0.1, 0.5))

    return jsonify({
        "status": "ok",
        "phone": phone,
        "request_id": REQUEST_COUNT,
        "timestamp": time.time()
    })


@app.route("/api/stats", methods=["GET"])
def stats():
    return jsonify({"total_requests": REQUEST_COUNT})


@app.route("/")
def index():
    return "Bomber test server is running"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)