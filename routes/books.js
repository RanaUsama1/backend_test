// routes/books.js
const express = require("express");
const router = express.Router();
const Book = require("../model/model.js");

// Route to get all books
router.get("/getData", async (req, res) => {
  try {
    const data = await Book.find(); // Fetch all documents
    res.status(200).json(data);
  } catch (error) {
    console.error("Error fetching data:", error);
    res.status(500).json({ error: "Could not get documents", details: error });
  }
});

// Route to search by "Submitted GenBank assembly"
// router.post("/search", async (req, res) => {
//   const { query } = req.body;

//   try {
//     const result = await Book.findOne({ "Submitted GenBank assembly": query });
//     if (result) {
//       res.status(200).json(result);
//     } else {
//       res.status(404).json({ message: "No results found for your query." });
//     }
//   } catch (error) {
//     console.error("Error fetching data:", error);
//     res.status(500).json({ error: "Could not fetch document", details: error });
//   }
// });

// POST /search route to handle searches based on type
// router.post('/search', async (req, res) => {
//   const { query, type } = req.body;

//   try {
//     let result;

//     // Check the type and apply the corresponding search condition
//     if (type === "scientific_name") {
//       result = await Book.findOne({ "Taxon": query });
//     } else if (type === "id") {
//       result = await Book.findOne({ "Submitted GenBank assembly": query });
//     }

//     if (result) {
//       res.status(200).json(result);
//     } else {
//       res.status(404).json({ message: "No results found for your query." });
//     }
//   } catch (error) {
//     console.error("Error fetching data:", error);
//     res.status(500).json({ error: "Could not fetch document", details: error });
//   }
// });

// Route to fetch all taxons starting with a specific substring
router.post('/search-options', async (req, res) => {
  const { query } = req.body;

  try {
    // Use a regex to find all documents where `Taxon` starts with `query`
    const searchQuery = new RegExp(`^${query}`, 'i'); // '^' ensures it starts with the substring
    const results = await Book.find({ "Taxon": searchQuery }).select("Taxon");

    if (results.length > 0) {
      res.status(200).json(results);
    } else {
      res.status(404).json({ message: "No matching taxons found." });
    }
  } catch (error) {
    console.error("Error fetching data:", error);
    res.status(500).json({ error: "Could not fetch matching taxons", details: error });
  }
});

// Route to search a specific record by "Taxon" or "Submitted GenBank assembly"
router.post('/search', async (req, res) => {
  const { query, type } = req.body;

  try {
    let result;
    const searchQuery = new RegExp(`^${query}$`, 'i'); // Exact match

    if (type === "scientific_name") {
      result = await Book.findOne({ "Taxon": searchQuery });
    } else if (type === "id") {
      result = await Book.findOne({ "Submitted GenBank assembly": query });
    }

    if (result) {
      res.status(200).json(result);
    } else {
      res.status(404).json({ message: "No results found for your query." });
    }
  } catch (error) {
    console.error("Error fetching data:", error);
    res.status(500).json({ error: "Could not fetch document", details: error });
  }
});

module.exports = router;
