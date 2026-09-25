"""Local GUI server for dxftogcode: serves the frontend and a /convert API."""

import os
import tempfile

from flask import Flask, jsonify, request, send_from_directory

from converter import ConversionError, Settings, convert

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

app = Flask(__name__, static_folder=None)


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(FRONTEND_DIR, filename)


def _float(form, key, default):
    val = form.get(key)
    if val is None or val == "":
        return default
    return float(val)


@app.route("/convert", methods=["POST"])
def convert_route():
    if "dxf" not in request.files:
        return jsonify({"error": "No DXF file uploaded."}), 400

    file = request.files["dxf"]
    if not file.filename:
        return jsonify({"error": "No DXF file selected."}), 400

    settings = Settings(
        units=request.form.get("units", "mm"),
        kerf_width=_float(request.form, "kerf_width", 1.0),
        pierce_delay=_float(request.form, "pierce_delay", 0.4),
        lead_in_length=_float(request.form, "lead_in_length", 3.0),
        lead_out_length=_float(request.form, "lead_out_length", 3.0),
        segment_tolerance=_float(request.form, "segment_tolerance", 0.05),
        normalize_origin=request.form.get("normalize_origin", "true") == "true",
    )

    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        gcode = convert(tmp_path, settings)
    except ConversionError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {e}"}), 500
    finally:
        os.unlink(tmp_path)

    base_name = os.path.splitext(file.filename)[0]
    return jsonify({"gcode": gcode, "filename": f"{base_name}.nc"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
