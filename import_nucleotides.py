import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from Bio import SeqIO


# =========================
# MongoDB
# =========================

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")

if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI is not set")

client = MongoClient(MONGODB_URI)

db = client.ncbi_cache
nucleotides = db.nucleotides


# =========================
# Indexes
# =========================

nucleotides.create_index(
    "accession",
    unique=True
)

nucleotides.create_index(
    "accession_version"
)

nucleotides.create_index(
    "organism.tax_id"
)

nucleotides.create_index(
    "organism.scientific_name"
)

nucleotides.create_index(
    "gene.symbol"
)


# =========================
# Helpers
# =========================

def safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_qualifier(feature, name):
    values = feature.qualifiers.get(name, [])

    if not values:
        return None

    return values[0]


def get_qualifier_list(feature, name):
    return feature.qualifiers.get(name, [])


# =========================
# Transform GenBank record
# =========================

def transform_nucleotide(record):

    accession = record.annotations.get(
        "accessions",
        [record.id]
    )[0]

    version = record.id

    organism = record.annotations.get(
        "organism"
    )

    molecule_type = record.annotations.get(
        "molecule_type"
    )

    topology = record.annotations.get(
        "topology"
    )

    tax_id = None

    gene_data = {
        "symbol": None,
        "synonyms": [],
        "gene_id": None,
        "hgnc_id": None,
        "mim_id": None
    }

    location_data = {
        "chromosome": None,
        "map": None
    }

    features = []

    coding_sequence = None

    # =========================
    # Parse features
    # =========================

    for feature in record.features:

        feature_type = feature.type

        # Convert Biopython's 0-based coordinates
        # back to NCBI's 1-based coordinates

        start = None
        end = None

        try:
            start = int(feature.location.start) + 1
            end = int(feature.location.end)
        except Exception:
            pass

        # =========================
        # Source
        # =========================

        if feature_type == "source":

            organism = (
                get_qualifier(feature, "organism")
                or organism
            )

            molecule_type = (
                get_qualifier(feature, "mol_type")
                or molecule_type
            )

            taxon = get_qualifier(
                feature,
                "db_xref"
            )

            if taxon and taxon.startswith("taxon:"):
                tax_id = safe_int(
                    taxon.replace("taxon:", "")
                )

            location_data["chromosome"] = (
                get_qualifier(
                    feature,
                    "chromosome"
                )
            )

            location_data["map"] = (
                get_qualifier(
                    feature,
                    "map"
                )
            )

        # =========================
        # Gene
        # =========================

        elif feature_type == "gene":

            gene_data["symbol"] = (
                get_qualifier(feature, "gene")
            )

            gene_data["synonyms"] = (
                get_qualifier_list(
                    feature,
                    "gene_synonym"
                )
            )

            for ref in get_qualifier_list(
                feature,
                "db_xref"
            ):

                if ref.startswith("GeneID:"):
                    gene_data["gene_id"] = (
                        ref.replace("GeneID:", "")
                    )

                elif ref.startswith("HGNC:"):
                    gene_data["hgnc_id"] = ref

                elif ref.startswith("MIM:"):
                    gene_data["mim_id"] = (
                        ref.replace("MIM:", "")
                    )

        # =========================
        # CDS
        # =========================

        elif feature_type == "CDS":

            coding_sequence = {
                "start": start,
                "end": end,

                "codon_start": safe_int(
                    get_qualifier(
                        feature,
                        "codon_start"
                    )
                ),

                "product": get_qualifier(
                    feature,
                    "product"
                ),

                "protein_accession":
                    get_qualifier(
                        feature,
                        "protein_id"
                    )
            }

        # =========================
        # Other features
        # =========================

        if feature_type not in (
            "source",
            "gene",
            "CDS"
        ):

            features.append({
                "type": feature_type,
                "start": start,
                "end": end
            })

    # =========================
    # References
    # =========================

    references = []

    for reference in record.annotations.get(
        "references",
        []
    ):

        references.append({
            "authors": str(
                reference.authors or ""
            ),

            "title": str(
                reference.title or ""
            ),

            "journal": str(
                reference.journal or ""
            ),

            "pubmed_id": (
                str(reference.pubmed_id)
                if reference.pubmed_id
                else None
            )
        })

    # =========================
    # Final MongoDB document
    # =========================

    return {

        "accession": accession,

        "accession_version": version,

        "uid": None,

        "title": record.description,

        "definition": record.description,

        "organism": {
            "scientific_name": organism,
            "tax_id": tax_id
        },

        "sequence": {
            "length": len(record.seq),
            "molecule_type": molecule_type,
            "topology": topology
        },

        "gene": gene_data,

        "location": location_data,

        "features": features,

        "coding_sequence": coding_sequence,

        "dates": {
            "create_date":
                record.annotations.get(
                    "date"
                ),

            "update_date":
                record.annotations.get(
                    "date"
                )
        },

        "references": references,

        "fetched_at":
            datetime.utcnow().isoformat(),

        "source": "NCBI GenBank"
    }


# =========================
# Import GenBank file
# =========================

def import_genbank(filename):

    operations = []

    total = 0

    for record in SeqIO.parse(
        filename,
        "genbank"
    ):

        document = transform_nucleotide(
            record
        )

        operations.append(
            UpdateOne(
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
        )

        total += 1

    if operations:

        result = nucleotides.bulk_write(
            operations,
            ordered=False
        )

        print(
            f"Inserted: {result.upserted_count}"
        )

        print(
            f"Updated: {result.modified_count}"
        )

    print(
        f"Processed: {total}"
    )


# =========================
# Main
# =========================

if __name__ == "__main__":

    if len(sys.argv) != 2:

        print(
            "Usage: python import_nucleotides.py FILE.gb"
        )

        sys.exit(1)

    import_genbank(
        sys.argv[1]
    )