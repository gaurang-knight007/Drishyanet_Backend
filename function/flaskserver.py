from flask import Flask, request, jsonify, Response
from pymongo import MongoClient
import face_recognition
import cv2
import numpy as np
import os
import time
from datetime import datetime
from flask_cors import CORS
import base64
import jwt
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

SECRET = os.getenv("JWT_SECRET", "defaultsecretkey")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
FLASK_PORT = int(os.getenv("FLASK_PORT", 5000))


app = Flask(__name__)
CORS(app)

client = MongoClient(MONGO_URI)
db = client["AttendanceDB"]

known_face_encodings = []
known_face_names = []

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if "Authorization" in request.headers:
            token = request.headers["Authorization"].split(" ")[1]
        if not token:
            return jsonify({"message": "Token missing!"}), 401
        try:
            data = jwt.decode(token, SECRET, algorithms=["HS256"])
            request.user = data  # attach user info
        except Exception as e:
            return jsonify({"message": "Token invalid!", "error": str(e)}), 401
        return f(*args, **kwargs)
    return decorated

def load_encodings_from_db():
    """Reload encodings from DB into memory"""
    global known_face_encodings, known_face_names
    known_face_encodings = []
    known_face_names = []

    encodings = list(db["encodings"].find({}, {"_id": 0}))
    for enc in encodings:
        known_face_encodings.append(np.array(enc["encoding"]))
        known_face_names.append(enc["name"])


def save_default_images_to_db():
    """Run once to migrate existing images folder into DB"""
    CurrentFolder = os.getcwd()
    images_folder = os.path.join(CurrentFolder, "images")

    if not os.path.exists(images_folder):
        return

    for file in os.listdir(images_folder):
        if file.lower().endswith(('.png', '.jpg', '.jpeg')):
            name = os.path.splitext(file)[0]
            image_path = os.path.join(images_folder, file)
            try:
                img = face_recognition.load_image_file(image_path)
                encs = face_recognition.face_encodings(img)
                if encs:
                    encoding = encs[0].tolist()

                    if not db["encodings"].find_one({"name": name}):
                        db["encodings"].insert_one({"name": name, "encoding": encoding})

                    if not db["students"].find_one({"name": name}):
                        with open(image_path, "rb") as f:
                            img_b64 = base64.b64encode(f.read()).decode("utf-8")
                        db["students"].insert_one({
                            "name": name,
                            "roll": "",
                            "branch": "",
                            "phone": "",
                            "image": img_b64
                        })
            except:
                pass

save_default_images_to_db()
load_encodings_from_db()

streaming = False

def gen_frames(subject):
    global streaming
    attendance_collection = db[subject]
    already_attendance_taken = set()
    marking_cooldown = 10
    last_marked_time = 0

    cap = cv2.VideoCapture(0)
    while streaming:
        ret, frame = cap.read()
        if not ret:
            break

        rgb_small_frame = cv2.cvtColor(
            cv2.resize(frame, (0, 0), fx=0.25, fy=0.25), cv2.COLOR_BGR2RGB
        )
        face_locations = face_recognition.face_locations(rgb_small_frame)
        face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

        names = []
        for face_encoding in face_encodings:
            matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
            name = "Unknown"
            if matches:
                face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
                best_match_index = np.argmin(face_distances)
                if matches[best_match_index]:
                    name = known_face_names[best_match_index]
            names.append(name)

            current_time = time.time()
            if (
                name != "Unknown"
                and name not in already_attendance_taken
                and (current_time - last_marked_time > marking_cooldown)
            ):
                now = datetime.now()
                attendance_collection.insert_one({
                    "name": name,
                    "status": "Present",
                    "date": now.strftime("%Y-%m-%d"),
                    "time": now.strftime("%H:%M:%S"),
                })
                already_attendance_taken.add(name)
                last_marked_time = current_time

        # draw boxes
        for (top, right, bottom, left), name in zip(face_locations, names):
            top *= 4; right *= 4; bottom *= 4; left *= 4
            cv2.rectangle(frame, (left, top), (right, bottom), (0,0,255), 2)
            cv2.rectangle(frame, (left, bottom-35), (right, bottom), (0,0,255), cv2.FILLED)
            cv2.putText(frame, name, (left+6, bottom-6), cv2.FONT_HERSHEY_DUPLEX, 1.0, (255,255,255), 1)

        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    cap.release()


@app.route("/api/attendance/start")
def start_attendance():
    global streaming
    subject = request.args.get("subject")
    if not subject:
        return "Subject required in query param ?subject=xxx", 400
    streaming = True
    return Response(gen_frames(subject),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route("/api/attendance/stop", methods=["POST"])
@token_required
def stop_attendance():
    global streaming
    streaming = False
    return jsonify({"message": "Attendance stopped"})


@app.route("/api/view", methods=["GET"])
@token_required
def view_attendance():
    subject = request.args.get("subject")
    date_input = request.args.get("date")

    try:
        formatted_date = datetime.strptime(date_input, "%y%m%d").strftime("%Y-%m-%d")
    except:
        return jsonify({"error": "Invalid date format, use yymmdd"}), 400

    records = list(db[subject].find({"date": formatted_date}, {"_id": 0}))
    if not records:
        return jsonify({"message": f"No attendance present for the date {formatted_date}"})
    return jsonify({"subject": subject, "date": formatted_date, "records": records})


@app.route("/api/students/add", methods=["POST"])
@token_required
def add_student():
    name = request.form.get("name")
    roll = request.form.get("roll")
    branch = request.form.get("branch")
    phone = request.form.get("phone")
    file = request.files.get("file")

    if not all([name, roll, branch, phone, file]):
        return jsonify({"error": "All fields are required"}), 400

    img = face_recognition.load_image_file(file)
    encs = face_recognition.face_encodings(img)
    if not encs:
        return jsonify({"error": "No face found in image"}), 400

    encoding = encs[0].tolist()
    file.seek(0)
    img_b64 = base64.b64encode(file.read()).decode("utf-8")

    db["students"].insert_one({
        "name": name,
        "roll": roll,
        "branch": branch,
        "phone": phone,
        "image": img_b64
    })

    db["encodings"].insert_one({"name": name, "encoding": encoding})

    load_encodings_from_db()  # refresh memory

    return jsonify({"message": f"Student {name} added successfully"})


@app.route("/api/students/delete", methods=["POST"])
@token_required
def delete_student():
    name = request.json.get("name")
    if not name:
        return jsonify({"error": "Name required"}), 400

    db["students"].delete_one({"name": name})
    db["encodings"].delete_one({"name": name})

    load_encodings_from_db()  # refresh memory

    return jsonify({"message": f"Student {name} deleted successfully"})


@app.route("/api/students/list", methods=["GET"])
@token_required
def list_students():
    students = list(db["students"].find({}, {"_id": 0}))
    return jsonify(students)


@app.route("/api/attendance/update", methods=["POST"])
@token_required
def update_attendance():
    subject = request.json.get("subject")
    name = request.json.get("name")
    date = request.json.get("date")
    status = request.json.get("status")

    if not all([subject, name, date, status]):
        return jsonify({"error": "Missing fields"}), 400

    db[subject].update_one({"name": name, "date": date}, {"$set": {"status": status}})
    return jsonify({"message": f"Attendance updated to {status}"})


@app.route("/api/attendance/delete", methods=["POST"])
@token_required
def delete_attendance():
    subject = request.json.get("subject")
    name = request.json.get("name")
    date = request.json.get("date")

    if not all([subject, name, date]):
        return jsonify({"error": "Missing fields"}), 400

    db[subject].delete_one({"name": name, "date": date})
    return jsonify({"message": f"Attendance record deleted"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=FLASK_PORT)