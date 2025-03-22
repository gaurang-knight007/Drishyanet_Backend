const express = require('express');
const { MongoClient } = require('mongodb');
const bodyParser = require('body-parser');
const path = require('path');
const multer = require('multer');
const cors = require('cors');
const { exec } = require('child_process');
const os = require('os');
const fs = require('fs');
const canvas = require('canvas'); 
require('dotenv').config();

const app = express();
const port = process.env.PORT || 5000; 

// Enable CORS for Vercel frontend
const corsOptions = {
  origin: process.env.FRONTEND_URL,
  methods: "GET,POST,PUT,DELETE",
  credentials: true
};
app.use(cors(corsOptions));

// Multer configuration for handling file uploads
const storage = multer.memoryStorage();
const upload = multer({ storage });

const url = process.env.MONGO_URI;
if (!url) {
  console.error("MONGO_URI is not set in the environment variables.");
  process.exit(1);
}
const dbName = 'userdb';
const dbName2 = 'userdb2';
const dbName3 = 'userdb3'; // New DB for attendance

let db, db2, db3;

function getLocalIP() {
  const interfaces = os.networkInterfaces();
  for (const interfaceName in interfaces) {
      for (const iface of interfaces[interfaceName]) {
          if (iface.family === 'IPv4' && !iface.internal) {
              return iface.address; // Return the first found IPv4 address
          }
      }
  }
  return 'localhost'; // Fallback to localhost if no external IP is found
}

MongoClient.connect(url, { useNewUrlParser: true, useUnifiedTopology: true })
  .then((client) => {
    console.log('Connected to MongoDB');
    db = client.db(dbName);
    db2 = client.db(dbName2);
    db3 = client.db(dbName3); // Initialize the attendance DB

    //app.listen(port, () => {
    //  console.log(`Server running at http://localhost:${port}`);
    //});
    app.listen(port, '0.0.0.0', () => {
      const localIP = getLocalIP();
      console.log(`Server running at:`);
      console.log(`  Local:            http://localhost:${port}`);
      console.log(`  On Your Network:  http://${localIP}:${port}`);
    });
  })
  .catch((err) => {
    console.error('Error connecting to MongoDB:', err);
    process.exit(1);
  });


app.use(bodyParser.urlencoded({ extended: true }));
app.use(express.json());

app.use(upload.single('image'));


// API Routes

app.get("/", (req, res) => {
  res.status(200).json({
    message: "Welcome to the Drishyanet API!",
    status: "success",
    date: new Date().toISOString(),
  });
});

//to check
app.get("/config", (req, res) => {
    res.json({ frontendUrl: process.env.FRONTEND_URL });
});

app.post('/signup', async (req, res) => {
  const { name, email, password } = req.body;
  if (!db) return res.status(500).send('Internal Server Error');

  const existingUser = await db.collection('users').findOne({ email });
  if (existingUser) return res.status(409).json({ success: false, message: 'Email already exists' });

  try {
    await db.collection('users').insertOne({ name, email, password });
    res.json({ success: true });
  } catch (error) {
    res.status(500).json({ success: false, error: 'Internal Server Error' });
  }
});

app.post('/signin', async (req, res) => {
  const { email, password } = req.body;
  if (!db) return res.status(500).send('Internal Server Error');

  const user = await db.collection('users').findOne({ email, password });
  if (user) {
    res.json({ success: true, message: 'Login successful' });
  } else {
    res.status(401).json({ success: false, message: 'Invalid email or password' });
  }
});

app.post('/proceed', (req, res) => {
  res.json({ success: true, message: 'Proceeding to next step' });
});

app.post('/proceed1', (req, res) => {
  res.json({ success: true, message: 'Proceeding to next step' });
});


app.post('/recognize-face', async (req, res) => {
  const { frame, subject_name } = req.body;

  if (!frame) {
    return res.status(400).json({ error: 'No image provided' });
  }

  // Decode the base64 image
  const base64Data = frame.replace(/^data:image\/jpeg;base64,/, "");

  // Save the base64 image as a temporary file for face recognition
  const tempImagePath = path.join(__dirname, 'temp_image.jpg');
  fs.writeFileSync(tempImagePath, Buffer.from(base64Data, 'base64'));

  // Run Python face recognition script (assuming face recognition code is in 'face_recognition_code.py')
  const pythonCommand = process.platform === 'win32' ? 'python' : 'python3';
  const scriptPath = path.join(__dirname, 'function', 'face_recognition_code.py');

  exec(`${pythonCommand} "${scriptPath}" "${tempImagePath}" "${subject_name}"`, (err, stdout, stderr) => {
    if (err) {
      console.error('Error in Python script:', stderr);
      return res.status(500).json({ error: 'Error in face recognition process' });
    }

    // Parse the result from the Python script (e.g., face name and face coordinates)
    const result = JSON.parse(stdout); // Assuming the Python script outputs JSON with name and coordinates
    if (result && result.name && result.facePosition) {
      res.json({
        name: result.name,
        facePosition: result.facePosition // { top, right, bottom, left }
      });
    } else {
      res.json({ name: 'Unknown', facePosition: null });
    }
  });
});


// Run Python script for attendance
app.post('/run-python', (req, res) => {
  const subjectName = req.body.subject_name;

  const pythonCommand = process.platform === 'win32' ? 'python' : 'python3';
  const scriptPath = path.join(__dirname, 'function', 'face_recognition_code.py');

  exec(`${pythonCommand} "${scriptPath}" "${subjectName}"`, (err, stdout, stderr) => {
    if (err) {
      console.error('Error:', err);
      return res.send('An error occurred while starting attendance.');
    }
    return res.send('Attendance started. Data saved.');
  });
});

// View attendance from MongoDB
app.get('/view-attendance', async (req, res) => {
  const subjectName = req.query.subject_name;
  if (!subjectName) return res.status(400).json({ error: 'Subject name required' });

  try {
    const attendanceRecords = await db3.collection(subjectName).find().toArray();
    res.json(attendanceRecords);
  } catch (error) {
    res.status(500).json({ error: 'Failed to retrieve attendance data' });
  }
});

// API for student registration with image upload
app.post('/api/register', async (req, res) => {
  const { name, rollNo, phone } = req.body;
  if (!db2) return res.status(500).send('Internal Server Error');

  try {
    const image = req.file ? req.file.buffer : null;
    await db2.collection('users').insertOne({ name, rollNo, phone, image });
    res.json({ success: true });
  } catch (error) {
    res.status(500).json({ success: false, error: 'Internal Server Error' });
  }
});

