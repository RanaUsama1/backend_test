import os
import sys
from datetime import datetime

from Bio import SeqIO
from pymongo import MongoClient
from dotenv import load_dotenv


# ============================================================
# MongoDB
# ============================================================

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")

if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI is not set")

client = MongoClient(MONGODB_URI)

db = client.ncbi_cache
proteins = db.proteins


# ============================================================
# Indexes
# ============================================================

proteins.create_index("accession", unique=True)
proteins.create_index("gene.symbol")
proteins.create_index("gene.gene_id")
proteins.create_index("organism.tax_id")
proteins.create_index("organism.scientific_name")


# ============================================================
# Helper
# ============================================================

def get_qualifier(feature, name, default=None):

    value = feature.qualifiers.get(name)

    if not value:
        return default

    if isinstance(value, list):
        return value[0]

    return value


def get_dbxref(feature, prefix):

    for value in feature.qualifiers.get("db_xref", []):

        if value.startswith(prefix):

            return value.split(":", 1)[1]

    return None


# ============================================================
# Transform Protein
# ============================================================

def transform_protein(record):

    accession = record.id

    accession_version = (
        record.annotations.get(
            "accessions",
            [accession]
        )[0]
    )

    # --------------------------------------------------------
    # Basic information
    # --------------------------------------------------------

    title = record.description

    organism = record.annotations.get(
        "organism",
        "Unknown"
    )

    sequence_length = len(record.seq)

    # --------------------------------------------------------
    # Source information
    # --------------------------------------------------------

    source_feature = None

    for feature in record.features:

        if feature.type == "source":

            source_feature = feature
            break

    tax_id = None
    chromosome = None
    map_location = None

    if source_feature:

        tax_id = get_dbxref(
            source_feature,
            "taxon:"
        )

        chromosome = get_qualifier(
            source_feature,
            "chromosome"
        )

        map_location = get_qualifier(
            source_feature,
            "map"
        )

    # --------------------------------------------------------
    # Protein feature
    # --------------------------------------------------------

    protein_feature = None

    for feature in record.features:

        if feature.type == "Protein":

            protein_feature = feature
            break

    molecular_weight = None
    product = None

    if protein_feature:

        product = get_qualifier(
            protein_feature,
            "product"
        )

        weight = get_qualifier(
            protein_feature,
            "calculated_mol_wt"
        )

        if weight:

            try:
                molecular_weight = int(weight)

            except ValueError:
                molecular_weight = None

    # --------------------------------------------------------
    # Gene information
    # --------------------------------------------------------

    gene_symbol = None
    gene_id = None
    nucleotide_accession = None

    for feature in record.features:

        # Gene feature
        if feature.type == "gene":

            if not gene_symbol:

                gene_symbol = get_qualifier(
                    feature,
                    "gene"
                )

            if not gene_id:

                gene_id = get_dbxref(
                    feature,
                    "GeneID:"
                )

        # Coded-by information may be on CDS
        if feature.type == "CDS":

            if not gene_symbol:

                gene_symbol = get_qualifier(
                    feature,
                    "gene"
                )

            if not gene_id:

                gene_id = get_dbxref(
                    feature,
                    "GeneID:"
                )

            coded_by = get_qualifier(
                feature,
                "coded_by"
            )

            if coded_by:

                # Example:
                # NM_000546.6:143..1324

                nucleotide_accession = (
                    coded_by.split(":", 1)[0]
                )

    # --------------------------------------------------------
    # Fallback: DBSOURCE
    # --------------------------------------------------------

    if not nucleotide_accession:

        dbsource = record.annotations.get(
            "db_source",
            ""
        )

        if "accession" in dbsource:

            nucleotide_accession = (
                dbsource.split(
                    "accession ",
                    1
                )[-1]
            )

    # --------------------------------------------------------
    # References
    # --------------------------------------------------------

    references = []

    for ref in record.annotations.get(
        "references",
        []
    ):

        references.append({

            "authors": ref.authors,

            "title": ref.title,

            "journal": ref.journal,

            "pubmed_id": (
                ref.pubmed_id
                if hasattr(ref, "pubmed_id")
                else None
            )
        })

    # --------------------------------------------------------
    # Final MongoDB document
    # --------------------------------------------------------

    return {

        "accession": accession,

        "accession_version": accession,

        "title": title,

        "definition": title,

        "product": product,

        "organism": {

            "scientific_name": organism,

            "tax_id": str(tax_id)
            if tax_id
            else "Unknown"
        },

        "sequence": {

            "length": sequence_length,

            "molecular_weight": molecular_weight
        },

        "gene": {

            "symbol": gene_symbol,

            "gene_id": (
                str(gene_id)
                if gene_id
                else None
            )
        },

        "coding_sequence": {

            "nucleotide_accession":
                nucleotide_accession
        },

        "location": {

            "chromosome": chromosome,

            "map": map_location
        },

        "dates": {

            "create_date":
                record.annotations.get(
                    "date",
                    "Unknown"
                ),

            "update_date":
                record.annotations.get(
                    "date",
                    "Unknown"
                )
        },

        "references": references,

        "external_links": {

            "ncbi":
                f"https://www.ncbi.nlm.nih.gov/protein/{accession}",

            "gene_link":
                (
                    f"https://www.ncbi.nlm.nih.gov/gene/{gene_id}"
                    if gene_id
                    else None
                )
        },

        "source": "NCBI GenBank",

        "fetched_at":
            datetime.utcnow().isoformat(),

        "from_cache": True
    }


# ============================================================
# Import GenBank
# ============================================================

def import_genbank(filename):

    processed = 0

    for record in SeqIO.parse(
        filename,
        "genbank"
    ):

        processed += 1

        document = transform_protein(
            record
        )

        proteins.update_one(

            {
                "accession":
                    document["accession"]
            },

            {
                "$set":
                    document
            },

            upsert=True
        )

        print(
            f"Imported: "
            f"{document['accession']}"
        )

    print()
    print(
        "Processed:",
        processed
    )

    print(
        "MongoDB protein count:",
        proteins.count_documents({})
    )


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":

    if len(sys.argv) != 2:

        print(
            "Usage: python import_proteins.py FILE.gb"
        )

        sys.exit(1)

    import_genbank(
        sys.argv[1]
    )