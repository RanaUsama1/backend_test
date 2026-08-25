import os
import xml.etree.ElementTree as ET
from datetime import datetime

from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv


# ============================================================
# MongoDB configuration
# ============================================================

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")

if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI is not set")

client = MongoClient(MONGODB_URI)

db = client.ncbi_cache
taxonomies = db.taxonomies


# ============================================================
# Indexes
# ============================================================

taxonomies.create_index(
    "tax_id",
    unique=True
)

taxonomies.create_index(
    "scientific_name"
)

taxonomies.create_index(
    "rank"
)


# ============================================================
# XML helpers
# ============================================================

def get_text(element, tag, default=None):

    value = element.findtext(tag)

    if value is None or value == "":
        return default

    return value


# ============================================================
# Transform one Taxon
# ============================================================

def transform_taxon(taxon):

    tax_id = get_text(
        taxon,
        "TaxId"
    )

    scientific_name = get_text(
        taxon,
        "ScientificName"
    )

    common_name = None

    other_names = taxon.find(
        "OtherNames"
    )

    synonyms = []

    if other_names is not None:

        for synonym in other_names.findall(
            "Synonym"
        ):

            if synonym.text:
                synonyms.append(
                    synonym.text
                )

        common_name_element = (
            other_names.find(
                "CommonName"
            )
        )

        if common_name_element is not None:

            common_name = (
                common_name_element.text
            )

    # --------------------------------------------------------
    # Basic information
    # --------------------------------------------------------

    rank = get_text(
        taxon,
        "Rank"
    )

    division = get_text(
        taxon,
        "Division"
    )

    parent_tax_id = get_text(
        taxon,
        "ParentTaxId"
    )

    # --------------------------------------------------------
    # Genetic code
    # --------------------------------------------------------

    genetic_code = {
        "id": 1,
        "name": "Unknown"
    }

    genetic_code_element = (
        taxon.find(
            "GeneticCode"
        )
    )

    if genetic_code_element is not None:

        gc_id = get_text(
            genetic_code_element,
            "GCId",
            "1"
        )

        gc_name = get_text(
            genetic_code_element,
            "GCName",
            "Unknown"
        )

        try:
            gc_id = int(gc_id)
        except (TypeError, ValueError):
            gc_id = 1

        genetic_code = {
            "id": gc_id,
            "name": gc_name
        }

    # --------------------------------------------------------
    # Mitochondrial genetic code
    # --------------------------------------------------------

    mitochondrial_genetic_code = None

    mito_element = (
        taxon.find(
            "MitoGeneticCode"
        )
    )

    if mito_element is not None:

        mgc_id = get_text(
            mito_element,
            "MGCId",
            "0"
        )

        mgc_name = get_text(
            mito_element,
            "MGCName",
            "Unknown"
        )

        try:
            mgc_id = int(mgc_id)
        except (TypeError, ValueError):
            mgc_id = 0

        mitochondrial_genetic_code = {
            "id": mgc_id,
            "name": mgc_name
        }

    # --------------------------------------------------------
    # Lineage
    # --------------------------------------------------------

    lineage = []

    lineage_ex = taxon.find(
        "LineageEx"
    )

    if lineage_ex is not None:

        for lineage_taxon in lineage_ex.findall(
            "Taxon"
        ):

            lineage_tax_id = get_text(
                lineage_taxon,
                "TaxId"
            )

            lineage_name = get_text(
                lineage_taxon,
                "ScientificName"
            )

            lineage_rank = get_text(
                lineage_taxon,
                "Rank"
            )

            lineage.append({

                "rank": lineage_rank,

                "name": lineage_name,

                "tax_id": lineage_tax_id
            })

    # --------------------------------------------------------
    # Full lineage string
    # --------------------------------------------------------

    lineage_string = get_text(
        taxon,
        "Lineage",
        ""
    )

    # --------------------------------------------------------
    # NCBI link
    # --------------------------------------------------------

    ncbi_link = (
        "https://www.ncbi.nlm.nih.gov/"
        "Taxonomy/Browser/"
        f"wwwtax.cgi?id={tax_id}"
    )

    # --------------------------------------------------------
    # Final document
    # --------------------------------------------------------

    return {

        "tax_id": str(tax_id),

        "query": str(tax_id),

        "scientific_name":
            scientific_name,

        "common_name":
            common_name,

        "rank":
            rank,

        "division":
            division,

        "parent_tax_id":
            parent_tax_id,

        "lineage":
            lineage,

        "lineage_string":
            lineage_string,

        "genetic_code":
            genetic_code,

        "mitochondrial_genetic_code":
            mitochondrial_genetic_code,

        "synonyms":
            synonyms,

        "external_links": {

            "ncbi":
                ncbi_link
        },

        "source":
            "NCBI Taxonomy",

        "fetched_at":
            datetime.utcnow().isoformat(),

        "from_cache":
            False
    }


# ============================================================
# Import XML
# ============================================================

def import_taxonomy(filename):

    print("=" * 55)
    print("IMPORTING NCBI TAXONOMY DATA")
    print("=" * 55)

    print(
        f"Input file: {filename}"
    )

    tree = ET.parse(
        filename
    )

    root = tree.getroot()

    taxon_elements = root.findall(
        "./Taxon"
    )

    print(
        f"Records found: "
        f"{len(taxon_elements)}"
    )

    operations = []

    processed = 0

    for taxon in taxon_elements:

        try:

            document = transform_taxon(
                taxon
            )

            operations.append(

                UpdateOne(

                    {
                        "tax_id":
                            document["tax_id"]
                    },

                    {
                        "$set":
                            document
                    },

                    upsert=True
                )
            )

            processed += 1

            # Execute in batches
            if len(operations) >= 100:

                taxonomies.bulk_write(
                    operations,
                    ordered=False
                )

                operations = []

                print(
                    f"Processed: "
                    f"{processed}"
                )

        except Exception as e:

            print(
                f"Error processing "
                f"record: {e}"
            )

    # Remaining records

    if operations:

        taxonomies.bulk_write(
            operations,
            ordered=False
        )

    print()
    print("=" * 55)
    print("IMPORT COMPLETE")
    print("=" * 55)

    print(
        f"Processed: {processed}"
    )

    print(
        f"MongoDB taxonomy count: "
        f"{taxonomies.count_documents({})}"
    )


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":

    import sys

    if len(sys.argv) != 2:

        print(
            "Usage:"
        )

        print(
            "python import_taxonomy.py "
            "download_taxonomy_large.xml"
        )

        sys.exit(1)

    import_taxonomy(
        sys.argv[1]
    )