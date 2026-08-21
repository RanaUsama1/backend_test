import json
import os
import sys
from datetime import datetime

from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv


# ==========================================
# Configuration
# ==========================================

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")

if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI is not set")


client = MongoClient(MONGODB_URI)

db = client.ncbi_cache

assemblies = db.assemblies


# ==========================================
# Helper functions
# ==========================================

def to_int(value):
    if value is None or value == "":
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_float(value):
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ==========================================
# Transform NCBI record
# ==========================================

def transform(record):
    assembly_info = record.get("assembly_info", {})
    paired = assembly_info.get("paired_assembly", {})
    ani = record.get(
        "average_nucleotide_identity", {}
    )
    
    best_ani = ani.get(
        "best_ani_match", {}
    )
    wgs = record.get("wgs_info", {})
    assembly_stats = record.get("assembly_stats", {})
    organism = record.get("organism", {})

    annotation = record.get("annotation_info", {})

    gene_counts = (
        annotation
        .get("stats", {})
        .get("gene_counts", {})
    )

    checkm = record.get("checkm_info", {})

    biosample = assembly_info.get("biosample", {})

    infraspecific = organism.get(
        "infraspecific_names", {}
    )

    accession = record.get("accession")

    if not accession:
        return None

    genome_size = to_int(
        assembly_stats.get("total_sequence_length")
    )

    ungapped_size = to_int(
        assembly_stats.get("total_ungapped_length")
    )

    document = {

        # -------------------------
        # Identity
        # -------------------------

        "accession": accession,

        "current_accession":
            record.get("current_accession"),

        "paired_accession":
            record.get("paired_accession"),

        "paired_annotation_name":
            paired.get("annotation_name"),

        "paired_status":
            paired.get("status"),
               
        "paired_accession":
            record.get("paired_accession"),

        "source_database":
            record.get("source_database"),

        # -------------------------
        # Organism
        # -------------------------

        "organism_name":
            organism.get("organism_name"),

        "common_name":
            organism.get("common_name"),

        "tax_id":
            organism.get("tax_id"),

        "strain":
            infraspecific.get("strain"),

        # -------------------------
        # Assembly
        # -------------------------

        "assembly_name":
            assembly_info.get("assembly_name"),

        "assembly_level":
            assembly_info.get("assembly_level"),

        "assembly_status":
            assembly_info.get("assembly_status"),

        "assembly_type":
            assembly_info.get("assembly_type"),

        "assembly_method":
            assembly_info.get("assembly_method"),

        "sequencing_technology":
            assembly_info.get("sequencing_tech"),

        "submitter":
            assembly_info.get("submitter"),

        "release_date":
            assembly_info.get("release_date"),

        "submission_date":
            biosample.get("submission_date"),

        "bioproject_accession":
            assembly_info.get(
                "bioproject_accession"
            ),
        "biosample_attributes":
            biosample.get("attributes", []),

        "biosample_attributes": [
            {
                "name": "host",
                "value": "Homo sapiens"
            },
            {
                "name": "isolation_source",
                "value": "gastrointestinal tract"
            },
        ],

        "biosample_accession":
            biosample.get("accession"),

        "biosample_collection_date":
            biosample.get("collection_date"),

        "biosample_last_updated":
            biosample.get("last_updated"),

        "biosample_publication_date":
            biosample.get("publication_date"),

        "biosample_geo_loc_name":
            biosample.get("geo_loc_name"),

        "host":
            biosample.get("host"),

        "isolation_source":
            biosample.get("isolation_source"),

        "biosample_package":
            biosample.get("package"),

        "biosample_project_name":
            biosample.get("project_name"),

        "biosample_description":
            biosample.get("description", {}).get("title")
            if isinstance(biosample.get("description"), dict)
            else biosample.get("description"),

        "biosample_submitter":
            biosample.get("owner", {}).get("name")
            if isinstance(biosample.get("owner"), dict)
            else None,
        # -------------------------
        # Genome statistics
        # -------------------------

        "genome_size_bp":
            genome_size,

        "genome_size_mb":
            round(genome_size / 1_000_000, 2)
            if genome_size else None,

        "genome_size_ungapped_bp":
            ungapped_size,

        "genome_size_ungapped_mb":
            round(ungapped_size / 1_000_000, 2)
            if ungapped_size else None,

        "gc_content":
            to_float(
                assembly_stats.get("gc_percent")
            ),

        "gc_count":
            to_int(
                assembly_stats.get("gc_count")
            ),

        "atgc_count":
            to_int(
                assembly_stats.get("atgc_count")
            ),

        "genome_coverage":
            assembly_stats.get(
                "genome_coverage"
            ),

        # -------------------------
        # Assembly statistics
        # -------------------------

        "number_of_chromosomes":
            to_int(
                assembly_stats.get(
                    "number_of_chromosomes"
                )
            ),

        "number_of_contigs":
            to_int(
                assembly_stats.get(
                    "number_of_contigs"
                )
            ),

        "number_of_scaffolds":
            to_int(
                assembly_stats.get(
                    "number_of_scaffolds"
                )
            ),

        "contig_n50":
            to_int(
                assembly_stats.get("contig_n50")
            ),

        "contig_l50":
            to_int(
                assembly_stats.get("contig_l50")
            ),

        "scaffold_n50":
            to_int(
                assembly_stats.get("scaffold_n50")
            ),

        "scaffold_l50":
            to_int(
                assembly_stats.get("scaffold_l50")
            ),

        "number_of_component_sequences":
            to_int(
                assembly_stats.get(
                    "number_of_component_sequences"
                )
            ),

        # -------------------------
        # Annotation
        # -------------------------

        "annotation_provider":
            annotation.get("provider"),

        "annotation_date":
            annotation.get("release_date"),

        "annotation_name":
            annotation.get("name"),

        "annotation_method":
            annotation.get("method"),

        "annotation_pipeline":
            annotation.get("pipeline"),

        "annotation_software_version":
            annotation.get("software_version"),

        # -------------------------
        # Gene counts
        # -------------------------

        "total_genes":
            to_int(
                gene_counts.get("total")
            ),

        "protein_coding_genes":
            to_int(
                gene_counts.get("protein_coding")
            ),

        "non_coding_genes":
            to_int(
                gene_counts.get("non_coding")
            ),

        "pseudogenes":
            to_int(
                gene_counts.get("pseudogene")
            ),

        # -------------------------
        # Quality
        # -------------------------

        "completeness":
            to_float(
                checkm.get("completeness")
            ),
        "checkm_marker_set":
            checkm.get("checkm_marker_set"),

        "checkm_marker_set_rank":
            checkm.get("checkm_marker_set_rank"),

        "checkm_species_tax_id":
            checkm.get("checkm_species_tax_id"),

        "checkm_version":
            checkm.get("checkm_version"),

        "completeness_percentile":
            to_float(
                checkm.get("completeness_percentile")
            ),

        "contamination":
            to_float(
                checkm.get("contamination")
            ),

        "ani_best_match":
            to_float(best_ani.get("ani")),

        "ani_best_assembly":
            best_ani.get("assembly"),

        "ani_best_assembly_coverage":
            to_float(
                best_ani.get("assembly_coverage")
            ),

        "ani_best_match_organism":
            best_ani.get("organism_name"),

        "ani_match_status":
            ani.get("match_status"),

        "ani_taxonomy_check_status":
            ani.get("taxonomy_check_status"),

        "wgs_project_accession":
            wgs.get("wgs_project_accession"),

        "wgs_master_url":
            wgs.get("master_wgs_url"),

        "wgs_contigs_url":
            wgs.get("wgs_contigs_url"),

        # -------------------------
        # NCBI URL
        # -------------------------

        "ncbi_url":
            f"https://www.ncbi.nlm.nih.gov/"
            f"datasets/genome/{accession}/",

        # -------------------------
        # Import information
        # -------------------------

        "data_source":
            "NCBI Datasets",

        "imported_at":
            datetime.utcnow().isoformat(),

        "from_cache":
            True
    }

    return document


assemblies.create_index("accession", unique=True)
assemblies.create_index("organism_name")

# ==========================================
# Import JSONL into MongoDB
# ==========================================

# def import_jsonl(filename):

#     operations = []

#     total = 0
#     skipped = 0

#     with open(
#         filename,
#         "r",
#         encoding="utf-8"
#     ) as f:

#         for line in f:

#             line = line.strip()

#             if not line:
#                 continue

#             total += 1

#             try:

#                 record = json.loads(line)

#                 document = transform(record)

#                 if not document:
#                     skipped += 1
#                     continue

#                 operations.append(
#                     UpdateOne(
#                         {
#                             "accession":
#                                 document["accession"]
#                         },
#                         {
#                             "$set": document
#                         },
#                         upsert=True
#                     )
#                 )

#             except Exception as e:

#                 print(
#                     f"Error processing record "
#                     f"{total}: {e}"
#                 )

#                 skipped += 1

#     if operations:

#         result = assemblies.bulk_write(
#             operations,
#             ordered=False
#         )

#         print()
#         print("Import completed")
#         print("----------------")
#         print(
#             f"Records read: "
#             f"{total}"
#         )

#         print(
#             f"Skipped: "
#             f"{skipped}"
#         )

#         print(
#             f"Inserted: "
#             f"{result.upserted_count}"
#         )

#         print(
#             f"Updated: "
#             f"{result.modified_count}"
#         )

#         print(
#             f"Matched: "
#             f"{result.matched_count}"
#         )


def import_jsonl(filename, batch_size=500):
    operations = []
    total = 0
    skipped = 0

    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            try:
                raw = json.loads(line)
                record = transform(raw)

                if not record.get("accession"):
                    skipped += 1
                    continue

                operations.append(
                    UpdateOne(
                        {"accession": record["accession"]},
                        {"$set": record},
                        upsert=True
                    )
                )

                total += 1

                if len(operations) >= batch_size:
                    result = assemblies.bulk_write(
                        operations,
                        ordered=False
                    )

                    print(
                        f"Processed: {total:,} | "
                        f"Skipped: {skipped:,}"
                    )

                    operations = []

            except Exception as e:
                skipped += 1
                print(f"Skipped record: {e}")

    if operations:
        assemblies.bulk_write(
            operations,
            ordered=False
        )

    print("\nImport complete")
    print(f"Processed: {total:,}")
    print(f"Skipped: {skipped:,}")

# ==========================================
# Main
# ==========================================

if __name__ == "__main__":

    if len(sys.argv) != 2:

        print(
            "Usage: "
            "python import_assemblies.py "
            "FILE.jsonl"
        )

        sys.exit(1)

    filename = sys.argv[1]

    print(
        f"Importing: {filename}"
    )

    import_jsonl(filename)