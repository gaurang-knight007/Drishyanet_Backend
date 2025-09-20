const express = require('express');
const { MongoClient } = require('mongodb');
const bodyParser = require('body-parser');
const multer = require('multer');
const cors = require('cors');
const os = require('os');
const jwt = require("jsonwebtoken");
const bcrypt = require("bcrypt");

require('dotenv').config();

const SECRET = process.env.JWT_SECRET;
const app = express();
const port = process.env.PORT;
const allowedOrigin = process.env.FRONTEND_URL;

const corsOptions = {
  origin: allowedOrigin,
  methods: "GET,POST,PUT,DELETE",
  allowedHeaders: ["Content-Type"],
  credentials: true
};

app.use(cors(corsOptions));

const storage = multer.memoryStorage();
const upload = multer({ storage });

const url = process.env.MONGO_URI;
if (!url) {
  console.error("MONGO_URI is not set in the environment variables.");
  process.exit(1);
}

const dbName = 'userdb';

let db;

function getLocalIP() {
  const interfaces = os.networkInterfaces();
  for (const interfaceName in interfaces) {
    for (const iface of interfaces[interfaceName]) {
      if (iface.family === 'IPv4' && !iface.internal) {
        return iface.address;
      }
    }
  }
  return 'localhost';
}

MongoClient.connect(url, { useNewUrlParser: true, useUnifiedTopology: true })
  .then((client) => {
    console.log('Connected to MongoDB');
    db = client.db(dbName);

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

app.get("/", (req, res) => {
  res.status(200).json({
    message: "Welcome to the Drishyanet API!",
    status: "success",
    date: new Date().toISOString(),
  });
});

app.get("/config", (req, res) => {
  res.json({ frontendUrl: process.env.FRONTEND_URL });
});

app.post('/signup', async (req, res) => {
  const { name, email, password } = req.body;
  if (!db) return res.status(500).send('Internal Server Error');

  const existingUser = await db.collection('users').findOne({ email });
  if (existingUser) return res.status(409).json({ success: false, message: 'Email already exists' });

  try
  {
  const hashedPassword = await bcrypt.hash(password, 10);
  await db.collection('users').insertOne({ name, email, password: hashedPassword });
  res.json({ success: true, message: 'Signup successful' });
  }
  catch (error)
  {
    return res.status(500).json({ success: false, error: 'Internal Server Error' });
  }
});

app.post('/signin', async (req, res) => {
  const { email, password } = req.body;
  if (!db)
  {
    return res.status(500).send('Internal Server Error');
  }

  const user = await db.collection('users').findOne({ email });
  if (!user) 
  {
    return res.status(401).json({ success: false, message: 'Invalid credentials' });
  }

  const isMatch = await bcrypt.compare(password, user.password);
  if (!isMatch) 
  {
    return res.status(401).json({ success: false, message: 'Invalid credentials' });
  }

  const token = jwt.sign({ email: user.email, name: user.name }, SECRET, { expiresIn: "1h" });
  res.json({ success: true, token });
});

app.post('/proceed', (req, res) => {
  res.json({ success: true, message: 'Proceeding to next step' });
});

app.post('/proceed1', (req, res) => {
  res.json({ success: true, message: 'Proceeding to next step' });
});