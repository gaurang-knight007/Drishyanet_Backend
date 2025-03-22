import face_recognition
import cv2
import numpy as np
import os
import sys
import json
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# Get subject name and image file path from command line arguments
image_path = sys.argv[1]  # Path to the image passed from the server
subject_name = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2].strip() else 'Default_Subject'

# Connect to MongoDB
mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
if not mongo_uri:
    raise ValueError("MONGO_URI is not set in the environment variables.")
client = MongoClient(mongo_uri)
db = client["userdb3"]  # Attendance database
collection = db[subject_name]  # Subject-specific collection

# Load known face encodings from images stored on the server
script_dir = os.path.dirname(os.path.realpath(__file__))
image_dir = os.path.join(script_dir, "images")  # Point to "function/images"

known_face_encodings = []
known_face_names = []

for file in os.listdir(image_dir):
    if file.endswith(".png") or file.endswith(".jpg"):
        name = os.path.splitext(file)[0]
        image_path = os.path.join(image_dir, file)
        image = face_recognition.load_image_file(image_path)
        encoding = face_recognition.face_encodings(image)[0]
        known_face_encodings.append(encoding)
        known_face_names.append(name)

# Process the received image from the backend
image = face_recognition.load_image_file(image_path)
face_locations = face_recognition.face_locations(image)
face_encodings = face_recognition.face_encodings(image, face_locations)

attendance_results = []

# Mark attendance based on face recognition
for face_encoding, face_location in zip(face_encodings, face_locations):
    matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
    name = "Unknown"

    face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
    best_match_index = np.argmin(face_distances)
    if matches[best_match_index]:
        name = known_face_names[best_match_index]

    if name != "Unknown":
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        today_date = datetime.now().strftime('%Y-%m-%d')
        
        # Check if the student is already marked today
        existing_entry = collection.find_one({"name": name, "date": today_date})

        if not existing_entry:
            collection.insert_one({"name": name, "status": "Present", "time": timestamp, "date": today_date})
            attendance_results.append({
                "name": name,
                "status": "Present",
                "face_position": face_location,
                "timestamp": timestamp
            })

# Output the result in JSON format
print(json.dumps(attendance_results))

