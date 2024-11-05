// require("dotenv").config(); // This loads variables from .env into process.env
// const express = require("express");
// // const { MongoClient } = require("mongodb");
// const mongoose = require("mongoose");
// const cors = require("cors");
// const app = express();
// const port = 3000;
// const Book = require("./model/model.js"); // Import the model

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


const express = require("express");
const mongoose = require("mongoose");
const cors = require("cors");
const app = express();
require("dotenv").config();
const port = process.env.PORT || 3000;
const bookRoutes = require("./routes/books.js");
// const { MongoClient } = require("mongodb");
// const Book = require("./model/model.js"); // Import the Book model // Import the model

// Middleware to parse JSON bodies
app.use(express.json());
app.use(cors());

// Connect to MongoDB
mongoose.connect(process.env.MONGO_URI, {
    useNewUrlParser: true,
    useUnifiedTopology: true
})
.then(() => console.log("Connected to MongoDB"))
.catch(err => console.error("MongoDB connection error:", err));

// Use the routes

app.use('/api/books', bookRoutes);



// MongoDB Atlas connection URI
// const mongoURI =
//   process.env.MONGO_URI ||
//   "mongodb+srv://admin:Sapienza786@cluster0.pvvuh.mongodb.net/ncbi?retryWrites=true&w=majority";
// let db;

// // Connect to MongoDB Atlas
// MongoClient.connect(mongoURI, {
//   useNewUrlParser: true,
//   useUnifiedTopology: true,
// })
//   .then((client) => {
//     db = client.db("ncbi"); // Use your desired database name
//     console.log("Connected to MongoDB Atlas");
//   })
//   .catch((err) => {
//     console.error("Failed to connect to MongoDB Atlas. Error:", err);
//     process.exit(1);
//   });

// Route to get data
// app.get("/search", async (req, res) => {
//   try {
//     const data = await db.collection("books").find().toArray();
//     res.status(200).json(data);
//   } catch (error) {
//     console.error("Error fetching data:", error);
//     res.status(500).json({ error: "Could not get documents", details: error });
//   }
// });

app.post("/search", async (req, res) => {
  const { query } = req.body;

  try {
    // Search the 'sample_data' collection where 'Submitted GenBank assembly' matches the query
    const result = await Book.findOne({ "Submitted GenBank assembly": query });

    if (result) {
      res.status(200).json(result); // Return the document as JSON if found
    } else {
      res.status(404).json({ message: "No results found for your query." });
    }
  } catch (error) {
    console.error("Error fetching data:", error);
    res.status(500).json({ error: "Could not fetch document", details: error });
  }
});



// Start the server
app.listen(port, () => {
  console.log(`Server running on port ${port}`);
});



