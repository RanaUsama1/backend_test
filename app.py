# from flask import Flask, request, jsonify
# from flask_cors import CORS
# import xmltodict
# import requests

# app = Flask(__name__)
# CORS(app)

# NCBI_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

# def fetch_species_list(term="Eukaryota", max_results=20):
#     url = f"{NCBI_BASE_URL}esearch.fcgi"
#     params = {
#         "db": "taxonomy",
#         "term": term,
#         "retmode": "json",
#         "retmax": max_results
#     }
#     response = requests.get(url, params=params)
#     data = response.json()
#     ids = data.get("esearchresult", {}).get("idlist", [])
#     if ids:
#         summary_url = f"{NCBI_BASE_URL}esummary.fcgi"
#         summary_params = {
#             "db": "taxonomy",
#             "id": ",".join(ids),
#             "retmode": "json"
#         }
#         summary_response = requests.get(summary_url, params=summary_params)
#         summary_data = summary_response.json()
#         species_list = [
#             item["ScientificName"]
#             for item in summary_data["result"].values()
#             if isinstance(item, dict) and "ScientificName" in item
#         ]
#         return species_list
#     return []

# def search_species_data(species_name):
#     url = f"{NCBI_BASE_URL}esearch.fcgi"
#     params = {
#         "db": "taxonomy",
#         "term": species_name,
#         "retmode": "json"
#     }
#     response = requests.get(url, params=params)
#     data = response.json()
#     taxonomy_ids = data.get("esearchresult", {}).get("idlist", [])
#     if taxonomy_ids:
#         fetch_url = f"{NCBI_BASE_URL}efetch.fcgi"
#         fetch_params = {
#             "db": "taxonomy",
#             "id": taxonomy_ids[0],
#             "retmode": "xml"
#         }
#         fetch_response = requests.get(fetch_url, params=fetch_params)
#         return fetch_response.text
#     return "No data found for the specified species."

# @app.route('/species-list', methods=['GET'])
# def species_list():
#     species = fetch_species_list()
#     return jsonify(species)
#     pass

# @app.route('/search', methods=['POST'])
# def search():
#     data = request.json
#     species_name = data.get("query", "")
#     metadata = search_species_data(species_name)
#     return jsonify({"species_name": species_name, "metadata": metadata})
#     pass


# if __name__ == '__main__':
#     import os
#     port = int(os.environ.get('PORT', 5000))  # Default to 5000 if PORT is not set
#     app.run(host='0.0.0.0', port=port, debug=True)



from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import xmltodict
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

@app.route('/species-list', methods=['GET'])
def species_list():
    """
    Fetch a list of species or taxonomic groups.
    """
    term = "Eukaryota"  # Default term
    max_results = 20
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "taxonomy",
        "term": term,
        "retmode": "json",
        "retmax": max_results
    }
    response = requests.get(url, params=params)
    data = response.json()
    ids = data.get("esearchresult", {}).get("idlist", [])

    # Fetch scientific names for the IDs
    if ids:
        summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
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
        return jsonify(species_list)

    return jsonify([])

@app.route('/search', methods=['POST'])
def search():
    """
    Search for detailed metadata for a specific species.
    """
    data = request.json
    species_name = data.get("query", "")
    if not species_name:
        return jsonify({"error": "No query provided."})

    # Search for species by name
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    search_params = {
        "db": "taxonomy",
        "term": species_name,
        "retmode": "json"
    }
    search_response = requests.get(search_url, params=search_params)
    search_data = search_response.json()
    taxonomy_ids = search_data.get("esearchresult", {}).get("idlist", [])

    # Fetch details if a taxonomy ID is found
    if taxonomy_ids:
        fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        fetch_params = {
            "db": "taxonomy",
            "id": taxonomy_ids[0],
            "retmode": "xml"
        }
        fetch_response = requests.get(fetch_url, params=fetch_params)
        xml_data = fetch_response.text
        parsed_data = xmltodict.parse(xml_data)  # Parse XML to JSON
        return jsonify(parsed_data)

    return jsonify({"error": "No data found for the specified species."})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
