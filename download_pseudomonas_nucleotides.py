import os
import time
import requests
from Bio import Entrez
from dotenv import load_dotenv

# ============================================================
# CONFIGURATION
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

TOOL_NAME = "genomic_metadata_search"

QUERY = '"Pseudomonas aeruginosa"[Organism]'

OUTPUT_FILE = "download_pseudomonas_nucleotides.gb"

# Start with 1,000 records.
# We can increase this after successful testing.
MAX_RECORDS = 1000

# NCBI recommends batching large requests.
BATCH_SIZE = 25

# Without API key, stay comfortably below
# the 3 requests/second limit.
REQUEST_DELAY = 1.0


# ============================================================
# NCBI REQUEST HELPER
# ============================================================

def ncbi_request(method, url, **kwargs):

    params = kwargs.pop("params", {})

    params["tool"] = TOOL_NAME
    params["email"] = NCBI_EMAIL

    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY

    for attempt in range(1, 6):

        try:

            response = requests.request(
                method,
                url,
                params=params,
                timeout=120,
                **kwargs
            )

            if response.status_code == 200:
                return response

            print(
                f"NCBI HTTP {response.status_code}; "
                f"retry {attempt}/5"
            )

        except requests.RequestException as e:

            print(
                f"Request error: {e}; "
                f"retry {attempt}/5"
            )

        time.sleep(2 ** attempt)

    raise RuntimeError(
        "NCBI request failed after 5 attempts"
    )


# ============================================================
# STEP 1 — SEARCH NCBI NUCLEOTIDE
# ============================================================

def search_ncbi():

    print()
    print("==========================================")
    print("Searching NCBI Nucleotide")
    print("==========================================")
    print()
    print("Query:", QUERY)

    url = (
        "https://eutils.ncbi.nlm.nih.gov/"
        "entrez/eutils/esearch.fcgi"
    )

    params = {
        "db": "nuccore",
        "term": QUERY,
        "retstart": 0,
        "retmax": MAX_RECORDS,
        "retmode": "json"
    }

    response = ncbi_request(
        "GET",
        url,
        params=params
    )

    data = response.json()

    result = data.get(
        "esearchresult",
        {}
    )

    count = int(
        result.get("count", 0)
    )

    ids = result.get(
        "idlist",
        []
    )

    print()
    print("Total matching NCBI records:", count)
    print("IDs retrieved:", len(ids))

    return ids, count


# ============================================================
# STEP 2 — FETCH GENBANK RECORDS
# ============================================================

def fetch_batch(ids):

    url = (
        "https://eutils.ncbi.nlm.nih.gov/"
        "entrez/eutils/efetch.fcgi"
    )

    params = {
        "db": "nuccore",
        "rettype": "gb",
        "retmode": "text"
    }

    max_attempts = 8

    for attempt in range(1, max_attempts + 1):

        try:

            response = ncbi_request(
                "POST",
                url,
                params=params,
                data={
                    "id": ",".join(ids)
                }
            )

            # Make sure NCBI actually returned GenBank records
            if "LOCUS" not in response.text:
                raise RuntimeError(
                    "NCBI response does not contain GenBank records"
                )

            return response.text

        except Exception as e:

            print(
                f"  Batch request failed: {e}"
            )

            if attempt < max_attempts:

                wait_time = min(
                    5 * attempt,
                    30
                )

                print(
                    f"  Waiting {wait_time}s "
                    f"before retry "
                    f"{attempt + 1}/{max_attempts}..."
                )

                time.sleep(wait_time)

            else:

                raise RuntimeError(
                    f"Batch failed after "
                    f"{max_attempts} attempts"
                )

# ============================================================
# MAIN DOWNLOAD
# ============================================================

def main():

    ids, total_count = search_ncbi()

    if not ids:

        print()
        print(
            "No Nucleotide records found."
        )

        return

    print()
    print(
        f"Downloading {len(ids)} records..."
    )
    print(
        f"Batch size: {BATCH_SIZE}"
    )
    print(
        f"Output: {OUTPUT_FILE}"
    )
    print()

    downloaded = 0

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as output:

        for start in range(
            0,
            len(ids),
            BATCH_SIZE
        ):

            batch = ids[
                start:start + BATCH_SIZE
            ]

            batch_number = (
                start // BATCH_SIZE
            ) + 1

            total_batches = (
                len(ids) + BATCH_SIZE - 1
            ) // BATCH_SIZE

            print(
                f"[Batch {batch_number}/"
                f"{total_batches}] "
                f"Fetching {len(batch)} records..."
            )

            gb_data = fetch_batch(batch)
        
            output.write(gb_data)

            if not gb_data.endswith("\n"):
                output.write("\n")

            downloaded += len(batch)

            print(
                f"  Downloaded: "
                f"{downloaded}/{len(ids)}"
            )
            time.sleep(
                REQUEST_DELAY
            )

    print()
    print("==========================================")
    print("DOWNLOAD COMPLETE")
    print("==========================================")
    print()
    print(
        "NCBI matching records:",
        total_count
    )
    print(
        "Requested records:",
        len(ids)
    )
    print(
        "Successfully requested:",
        downloaded
    )
    print(
        "Output file:",
        OUTPUT_FILE
    )
    print()


if __name__ == "__main__":
    main()
