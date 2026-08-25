import time
import requests

input_file = "accessions.txt"
output_file = "nucleotide_test.gb"

url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

with open(input_file, "r") as f:
    accessions = [
        line.strip()
        for line in f
        if line.strip()
    ]

with open(output_file, "w") as out:

    for accession in accessions:

        print(f"Fetching {accession}...")

        params = {
            "db": "nuccore",
            "id": accession,
            "rettype": "gb",
            "retmode": "text"
        }

        response = requests.get(
            url,
            params=params,
            timeout=60
        )

        response.raise_for_status()

        out.write(response.text)

        # Respect NCBI request rate
        time.sleep(0.4)

print(f"\nDownloaded {len(accessions)} records.")
print(f"Saved to: {output_file}")