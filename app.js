require("dotenv").config(); // This loads variables from .env into process.env
const express = require("express");
// const { MongoClient } = require("mongodb");
const mongoose = require("mongoose");
const cors = require("cors");
const app = express();
const port = 3000;
const Book = require("./model/model.js"); // Import the model

// Middleware to parse JSON bodies
app.use(express.json());
app.use(cors());

// MongoDB connection URL and database name
const url = "mongodb+srv://admin:Sapienza786@cluster0.pvvuh.mongodb.net/";
// const dbName = "ncbi";
// let db;

mongoose
  .connect(url, { useNewUrlParser: true, useUnifiedTopology: true })
  .then(() => {
    console.log("Connected to MongoDB Atlas");
  })
  .catch((err) => {
    console.error("Failed to connect to MongoDB Atlas. Error:", err);
    process.exit(1);
  });

// Route to get data
app.get("/getData", async (req, res) => {
  try {
    const data = await Book.find(); // Assuming 'Book' is a Mongoose model
    res.status(200).json(data);
  } catch (error) {
    console.error("Error fetching data:", error);
    res.status(500).json({ error: "Could not get documents", details: error });
  }
});

app.listen(port, () => {
  console.log(`Server running at http://localhost:${port}`);
});

// // Connect to MongoDB
// MongoClient.connect(url, { useNewUrlParser: true, useUnifiedTopology: true })
//   .then((client) => {
//     db = client.db(dbName);
//     console.log("Connected to MongoDB");
//   })
//   .catch((err) => {
//     console.error("Failed to connect to the database. Error:", err);
//     process.exit(1);
//   });

// Route to get data
// app.get("/getData", async (req, res) => {
//   try {
//     const data = await db.collection("sample_data").find().toArray();
//     res.status(200).json(data);
//   } catch (error) {
//     console.error("Error fetching data:", error);
//     res.status(500).json({ error: "Could not get documents", details: error });
//   }
// });
