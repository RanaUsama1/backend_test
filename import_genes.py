import json
import os
import sys
from datetime import datetime, timezone

from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv


# =========================
# MongoDB connection
# =========================

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")

if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI is not set")

client = MongoClient(MONGODB_URI)

db = client.ncbi_cache
genes = db.genes


# =========================
# Indexes
# =========================

genes.create_index("gene_id", unique=True)
genes.create_index("symbol")
genes.create_index("organism.tax_id")
genes.create_index("organism.scientific_name")


# =========================
# Transform NCBI Gene record
# =========================

def transform_gene(raw):
    return {
        "gene_id": str(raw.get("geneId", "")),
        "symbol": raw.get("symbol"),
        "description": raw.get("description"),

        "organism": {
            "scientific_name": raw.get("taxname"),
            "common_name": raw.get("commonName"),
            "tax_id": str(raw.get("taxId", ""))
        },

        "gene_type": raw.get("type"),
        "orientation": raw.get("orientation"),

        "chromosomes": raw.get("chromosomes", []),

        "nomenclature_authority":
            raw.get("nomenclatureAuthority"),

        "swissprot_accessions":
            raw.get("swissProtAccessions", []),

        "ensembl_gene_ids":
            raw.get("ensemblGeneIds", []),

        "omim_ids":
            raw.get("omimIds", []),

        "synonyms":
            raw.get("synonyms", []),

        "reference_standards":
            raw.get("referenceStandards", []),

        "annotations":
            raw.get("annotations", []),

        "transcript_count":
            raw.get("transcriptCount", 0),

        "protein_count":
            raw.get("proteinCount", 0),

        "transcript_type_counts":
            raw.get("transcriptTypeCounts", []),

        "gene_groups":
            raw.get("geneGroups", []),

        "summary":
            raw.get("summary", []),

        "gene_ontology":
            raw.get("geneOntology"),

        "map_locations":
            raw.get("mapLocations", []),

        "alternate_names":
            raw.get("alternateNames", []),

        "source_database": "NCBI_GENE",

        "imported_at": datetime.now(timezone.utc).isoformat()
    }


def import_jsonl(filename, batch_size=500):
    operations = []

    total = 0
    skipped = 0
    inserted = 0
    updated = 0

    with open(filename, "r", encoding="utf-8") as f:

        for line_number, line in enumerate(f, 1):

            line = line.strip()

            if not line:
                continue

            try:
                raw = json.loads(line)

                gene_id = raw.get("geneId")

                if not gene_id:
                    skipped += 1
                    print(
                        f"Skipping line {line_number}: "
                        "missing geneId"
                    )
                    continue

                document = transform_gene(raw)

                operations.append(
                    UpdateOne(
                        {"gene_id": document["gene_id"]},
                        {"$set": document},
                        upsert=True
                    )
                )

                total += 1

                # =========================
                # Write batch
                # =========================

                if len(operations) >= batch_size:

                    result = genes.bulk_write(
                        operations,
                        ordered=False
                    )

                    inserted += result.upserted_count
                    updated += result.modified_count

                    print(
                        f"Processed {total} records..."
                    )

                    operations = []

            except Exception as e:
                skipped += 1

                print(
                    f"Error processing line {line_number}: {e}"
                )

    # =========================
    # Write remaining records
    # =========================

    if operations:

        result = genes.bulk_write(
            operations,
            ordered=False
        )

        inserted += result.upserted_count
        updated += result.modified_count

    print("\n===== IMPORT COMPLETE =====")
    print(f"Records processed: {total}")
    print(f"Records skipped:   {skipped}")
    print(f"Inserted:          {inserted}")
    print(f"Updated:           {updated}")



# =========================
# Main
# =========================

if __name__ == "__main__":

    if len(sys.argv) != 2:
        print(
            "Usage: python import_genes.py FILE.jsonl"
        )
        sys.exit(1)

    filename = sys.argv[1]

    if not os.path.exists(filename):
        raise FileNotFoundError(
            f"File not found: {filename}"
        )

    print(f"Importing Gene data from: {filename}")

    import_jsonl(filename)

    print(
        f"\nTotal records in MongoDB: "
        f"{genes.count_documents({})}"
    )