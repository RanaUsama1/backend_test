def fetch_ena_assembly(accession):
    try:
        response = metadata_get(f'https://www.ebi.ac.uk/ena/browser/api/xml/{accession}', timeout=15)
        if not response.ok:
            return None
        return parse_ena_xml(response.content, accession)
    except Exception as exc:
        print(f'ENA fetch error: {type(exc).__name__}')
        return None
