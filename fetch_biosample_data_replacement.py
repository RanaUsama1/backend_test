def fetch_biosample_data(biosample_accession):
    """Fetch BioSample metadata from NCBI"""
    if not biosample_accession:
        return None

    try:
        # Search for BioSample UID
        search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=biosample&term={biosample_accession}&retmode=json"
        search_resp = rate_limited_request(search_url)
        search_data = search_resp.json()

        if not search_data.get('esearchresult', {}).get('idlist'):
            return None

        uid = search_data['esearchresult']['idlist'][0]

        # Fetch summary
        summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=biosample&id={uid}&retmode=json"
        summary_resp = rate_limited_request(summary_url)
        summary_data = summary_resp.json().get('result', {}).get(str(uid), {})

        # Parse sampledata XML if present
        biosample_info = {
            'accession': biosample_accession,
            'uid': uid,
            'title': summary_data.get('title'),
            'organism': summary_data.get('organism'),
            'tax_id': summary_data.get('taxonomy'),
            'submitter': summary_data.get('organization'),
            'submission_date': summary_data.get('date'),
            'publication_date': summary_data.get('publicationdate'),
            'modification_date': summary_data.get('modificationdate'),
            'package': summary_data.get('package'),
            'attributes': {},
            'description': None,
            'links': {}
        }

        # Parse the sampledata XML for detailed info
        sample_data_xml = summary_data.get('sampledata', '')
        if sample_data_xml:
            try:
                root = ET.fromstring(sample_data_xml)

                for elem in root.iter():
                    tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag

                    if tag == 'Title':
                        if not biosample_info['title']:
                            biosample_info['title'] = elem.text
                    elif tag == 'Description':
                        # Look for Paragraph inside Description
                        for child in elem.iter():
                            child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                            if child_tag == 'Paragraph' and child.text:
                                biosample_info['description'] = child.text
                    elif tag == 'Attribute':
                        attr_name = elem.get('attribute_name') or elem.get('harmonized_name')
                        if attr_name:
                            biosample_info['attributes'][attr_name] = elem.text
                    elif tag == 'Link':
                        link_type = elem.get('type')
                        link_target = elem.get('target')
                        link_label = elem.get('label')
                        if link_target:
                            biosample_info['links'][link_target] = {
                                'type': link_type,
                                'label': link_label,
                                'value': elem.text
                            }
            except Exception as e:
                print(f"BioSample XML parse error: {e}")

        # Also check infraspecies field
        infraspecies = summary_data.get('infraspecies', '')
        if infraspecies and ':' in infraspecies:
            for item in infraspecies.split(';'):
                key, separator, value = item.partition(':')
                if separator and key.strip():
                    biosample_info['attributes'].setdefault(key.strip(), value.strip())

        return biosample_info

    except Exception as e:
        print(f"BioSample fetch error: {e}")
        return None
