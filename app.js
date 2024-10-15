// require("dotenv").config(); // This loads variables from .env into process.env
// const express = require("express");
// // const { MongoClient } = require("mongodb");
// const mongoose = require("mongoose");
// const cors = require("cors");
// const app = express();
// const port = 3000;
// const Book = require("./model/model.js"); // Import the model

// // Middleware to parse JSON bodies
// app.use(express.json());
// app.use(cors());

// // MongoDB connection URL and database name
// const url = "mongodb+srv://admin:Sapienza786@cluster0.pvvuh.mongodb.net/";
// // const dbName = "ncbi";
// // let db;

// mongoose
//   .connect(url, { useNewUrlParser: true, useUnifiedTopology: true })
//   .then(() => {
//     console.log("Connected to MongoDB Atlas");
//   })
//   .catch((err) => {
//     console.error("Failed to connect to MongoDB Atlas. Error:", err);
//     process.exit(1);
//   });

// // Route to get data
// app.get("/getData", async (req, res) => {
//   try {
//     const data = await Book.find(); // Assuming 'Book' is a Mongoose model
//     res.status(200).json(data);
//   } catch (error) {
//     console.error("Error fetching data:", error);
//     res.status(500).json({ error: "Could not get documents", details: error });
//   }
// });

// app.listen(port, () => {
//   console.log(`Server running at http://localhost:${port}`);
// });

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



const express = require("express");
const mongoose = require("mongoose");
const app = express();
require("dotenv").config(); // Load environment variables
const Book = require("./model/model.js"); // Import the Book model
const port = process.env.PORT || 3000;

// Middleware to parse incoming JSON requests
app.use(express.json());

// MongoDB connection using environment variable or hardcoded URI
const mongoURI =
  process.env.MONGO_URI ||
  "mongodb+srv://mongodb+srv://admin:Sapienza786@cluster0.pvvuh.mongodb.net/ncbi?retryWrites=true&w=majority";

mongoose
  .connect(mongoURI, { useNewUrlParser: true, useUnifiedTopology: true })
  .then(() => console.log("Connected to MongoDB"))
  .catch((err) => console.log("Error connecting to MongoDB:", err));

// POST endpoint to handle search requests from the frontend
app.post("/search", async (req, res) => {
  const { query, type } = req.body; // Get query and type from the request body

  try {
    let results;

    if (type === "scientific_name") {
      // Search by scientific name using the `Taxon` field (case-insensitive)
      results = await Book.find({ Taxon: new RegExp(query, "i") });
    } else if (type === "id") {
      // Search by `id` field for exact matches
      results = await Book.find({ id: query });
    }

    if (results.length > 0) {
      res.status(200).json(results); // Return the matching results
    } else {
      res.status(404).json({ message: "No results found for your query." });
    }
  } catch (error) {
    console.error("Error fetching data:", error);
    res.status(500).json({ error: "Could not get documents", details: error });
  }
});

// Start the server
app.listen(port, () => {
  console.log(`Server is running on port ${port}`);
});
