import time
import requests

INPUT_FILE = "accessions.txt"
OUTPUT_FILE = "nucleotide_large.gb"

BATCH_SIZE = 100

EFETCH_URL = (
    "https://eutils.ncbi.nlm.nih.gov/"
    "entrez/eutils/efetch.fcgi"
)


def read_accessions(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return list(dict.fromkeys(
            line.strip()
            for line in f
            if line.strip()
        ))


def fetch_batch(accessions):

    params = {
        "db": "nuccore",
        "id": ",".join(accessions),
        "rettype": "gb",
        "retmode": "text"
    }

    response = requests.get(
        EFETCH_URL,
        params=params,
        timeout=120
    )

    response.raise_for_status()

    return response.text


accessions = read_accessions(INPUT_FILE)

print("Total accessions:", len(accessions))

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as output:

    for start in range(
        0,
        len(accessions),
        BATCH_SIZE
    ):

        batch = accessions[
            start:start + BATCH_SIZE
        ]

        print(
            f"Fetching "
            f"{start + 1}-{start + len(batch)} "
            f"of {len(accessions)}"
        )

        try:

            data = fetch_batch(batch)

            output.write(data)
            output.write("\n")

        except Exception as e:

            print(
                "Batch failed:",
                e
            )

        time.sleep(0.5)

print("Download completed.")