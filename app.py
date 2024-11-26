from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

NCBI_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

def fetch_species_list(term="Eukaryota", max_results=20):
    url = f"{NCBI_BASE_URL}esearch.fcgi"
    params = {
        "db": "taxonomy",
        "term": term,
        "retmode": "json",
        "retmax": max_results
    }
    response = requests.get(url, params=params)
    data = response.json()
    ids = data.get("esearchresult", {}).get("idlist", [])
    if ids:
        summary_url = f"{NCBI_BASE_URL}esummary.fcgi"
        summary_params = {
            "db": "taxonomy",
            "id": ",".join(ids),
            "retmode": "json"
        }
        summary_response = requests.get(summary_url, params=summary_params)
        summary_data = summary_response.json()
        species_list = [
            item["ScientificName"]
            for item in summary_data["result"].values()
            if isinstance(item, dict) and "ScientificName" in item
        ]
        return species_list
    return []

def search_species_data(species_name):
    url = f"{NCBI_BASE_URL}esearch.fcgi"
    params = {
        "db": "taxonomy",
        "term": species_name,
        "retmode": "json"
    }
    response = requests.get(url, params=params)
    data = response.json()
    taxonomy_ids = data.get("esearchresult", {}).get("idlist", [])
    if taxonomy_ids:
        fetch_url = f"{NCBI_BASE_URL}efetch.fcgi"
        fetch_params = {
            "db": "taxonomy",
            "id": taxonomy_ids[0],
            "retmode": "xml"
        }
        fetch_response = requests.get(fetch_url, params=fetch_params)
        return fetch_response.text
    return "No data found for the specified species."

@app.route('/species-list', methods=['GET'])
def species_list():
    species = fetch_species_list()
    return jsonify(species)

@app.route('/search', methods=['POST'])
def search():
    data = request.json
    species_name = data.get("query", "")
    metadata = search_species_data(species_name)
    return jsonify({"species_name": species_name, "metadata": metadata})

if __name__ == '__main__':
    app.run(debug=True)
