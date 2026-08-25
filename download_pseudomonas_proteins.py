import os
import time
from Bio import Entrez, SeqIO
from dotenv import load_dotenv


# ============================================================
# Configuration
# ============================================================

load_dotenv()

NCBI_EMAIL = os.getenv("NCBI_EMAIL")

if not NCBI_EMAIL:
    raise RuntimeError(
        "NCBI_EMAIL is not set in your .env file"
    )

NCBI_API_KEY = os.getenv("NCBI_API_KEY")

Entrez.email = NCBI_EMAIL

if NCBI_API_KEY:
    Entrez.api_key = NCBI_API_KEY


BATCH_SIZE = 25
DELAY = 1.0
MAX_RECORDS = 1000

OUTPUT_FILE = "download_pseudomonas_proteins.gb"

SEARCH_TERM = '"Pseudomonas aeruginosa"[Organism]'


# ============================================================
# Search NCBI Protein
# ============================================================

def search_proteins():

    print("Searching NCBI Protein database...")
    print(f"Search: {SEARCH_TERM}")

    handle = Entrez.esearch(
        db="protein",
        term=SEARCH_TERM,
        retmax=0
    )

    result = Entrez.read(handle)
    handle.close()

    count = int(result["Count"])

    print(f"NCBI matching records: {count:,}")

    return count


# ============================================================
# Get protein IDs
# ============================================================

def get_protein_ids():

    handle = Entrez.esearch(
        db="protein",
        term=SEARCH_TERM,
        retstart=0,
        retmax=MAX_RECORDS
    )

    result = Entrez.read(handle)
    handle.close()

    ids = result["IdList"]

    print(f"Protein IDs retrieved: {len(ids)}")

    return ids


# ============================================================
# Fetch one batch
# ============================================================

def fetch_batch(ids, batch_number, total_batches):

    print(
        f"\n[Batch {batch_number}/{total_batches}] "
        f"Fetching {len(ids)} records..."
    )

    for attempt in range(1, 6):

        try:

            handle = Entrez.efetch(
                db="protein",
                id=ids,
                rettype="gb",
                retmode="text"
            )

            records = list(
                SeqIO.parse(handle, "genbank")
            )

            handle.close()

            if not records:

                raise RuntimeError(
                    "NCBI returned no GenBank records"
                )

            return records

        except Exception as e:

            print(
                f"Request error: {e}; "
                f"retry {attempt}/5"
            )

            if attempt < 5:
                time.sleep(3 * attempt)

            else:
                raise RuntimeError(
                    "NCBI request failed after 5 attempts"
                )


# ============================================================
# Main download
# ============================================================

def download_proteins():

    print("=" * 50)
    print("PSEUDOMONAS AERUGINOSA PROTEIN DOWNLOADER")
    print("=" * 50)

    print(f"Batch size: {BATCH_SIZE}")
    print(f"Delay: {DELAY} seconds")
    print(f"Maximum records: {MAX_RECORDS}")
    print(f"Output: {OUTPUT_FILE}")
    print()

    total_count = search_proteins()

    ids = get_protein_ids()

    if not ids:

        print("No protein records found.")
        return

    total_records = len(ids)

    batches = [
        ids[i:i + BATCH_SIZE]
        for i in range(
            0,
            total_records,
            BATCH_SIZE
        )
    ]

    total_batches = len(batches)

    downloaded = 0

    # Start a fresh output file
    open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ).close()

    for batch_number, batch_ids in enumerate(
        batches,
        1
    ):

        try:

            records = fetch_batch(
                batch_ids,
                batch_number,
                total_batches
            )

            with open(
                OUTPUT_FILE,
                "a",
                encoding="utf-8"
            ) as output:

                SeqIO.write(
                    records,
                    output,
                    "genbank"
                )

            downloaded += len(records)

            print(
                f"  Downloaded: "
                f"{downloaded}/{total_records}"
            )

        except Exception as e:

            print(
                f"Batch failed: {e}"
            )

        if batch_number < total_batches:

            time.sleep(DELAY)

    print()
    print("=" * 50)
    print("DOWNLOAD COMPLETE")
    print("=" * 50)

    print(
        f"NCBI matching records: "
        f"{total_count:,}"
    )

    print(
        f"Requested records: "
        f"{total_records}"
    )

    print(
        f"Successfully downloaded: "
        f"{downloaded}"
    )

    print(
        f"Output file: "
        f"{OUTPUT_FILE}"
    )


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    download_proteins()