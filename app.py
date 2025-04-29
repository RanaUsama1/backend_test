from fastapi import FastAPI, HTTPException, Query
from typing import List, Optional
from Bio import Entrez
from Bio import SeqIO
from pymongo import MongoClient
from fastapi.middleware.cors import CORSMiddleware
import logging
import time
import uvicorn
import traceback
import httpx
from datetime import datetime
from Bio.Entrez import Parser
from Bio.Entrez.Parser import StringElement
import json
import asyncio

# Configure email for NCBI API
Entrez.email = "abdullah.1970333@studenti.uniroma1.it"
MONGO_URI = "mongodb+srv://admin2:Cloud786@clusterfull.tn88z.mongodb.net/taxonomy"

# Initialize the client and database
try:
    client = MongoClient(MONGO_URI)
    db = client.taxonomy
    print("Connected to MongoDB successfully!")
    print("Databases:", client.list_database_names())
except Exception as e:
    print("Error connecting to MongoDB:", e)
    raise HTTPException(status_code=500, detail="Failed to connect to MongoDB")

# Create FastAPI app
app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up logging
logging.basicConfig(level=logging.INFO)

async def check_cache(database: str, identifier: str):
    """Check MongoDB cache for existing metadata"""
    try:
        cached_data = db.metadata.find_one({"database": database, "accession": identifier})
        if cached_data:
            cached_data["_id"] = str(cached_data["_id"])
            logging.info(f"Cache hit for {database} {identifier}")
            return cached_data
        return None
    except Exception as e:
        logging.error(f"Error checking cache: {e}")
        return None

async def save_to_cache(metadata: dict):
    """Save metadata to MongoDB cache"""
    try:
        result = db.metadata.insert_one(metadata)
        metadata["_id"] = str(result.inserted_id)
        logging.info(f"Saved metadata for {metadata['database']} {metadata['accession']} to cache")
        return metadata
    except Exception as e:
        logging.error(f"Error saving to cache: {e}")
        return metadata  # Return metadata even if caching fails

async def fetch_nucleotide_metadata(uid: str):
    """Fetch metadata for nucleotide records with caching"""
    try:
        # Check cache first
        cached_data = await check_cache("nucleotide", uid)
        if cached_data:
            return cached_data

        logging.info(f"Fetching nucleotide data for UID: {uid}")
        await asyncio.sleep(1)  # Add a delay to avoid rate limits
        
        handle = Entrez.efetch(db="nucleotide", id=uid, rettype="gb", retmode="text")
        records = list(SeqIO.parse(handle, "genbank"))
        if not records:
            raise HTTPException(status_code=404, detail="No records found")
        record = records[0]
        handle.close()

        metadata = {
            "database": "nucleotide",
            "accession": record.id,
            "organism": record.annotations.get("organism", "Unknown"),
            "definition": record.description,
            "length": len(record.seq),
            "updated_date": record.annotations.get("date", "Unknown"),
            "genes": [
                feature.qualifiers.get("gene", ["Unknown"])[0]
                for feature in record.features if feature.type == "gene"
            ],
            "features": [
                {
                    "type": feature.type,
                    "location": str(feature.location),
                    "qualifiers": {key: ", ".join(val) if isinstance(val, list) else val for key, val in feature.qualifiers.items()}
                }
                for feature in record.features
            ],
            "references": [
                {
                    "title": reference.title,
                    "authors": ", ".join(reference.authors) if hasattr(reference, "authors") else "Unknown",
                    "journal": reference.journal
                }
                for reference in record.annotations.get("references", [])
            ],
            "source": record.annotations.get("source", "Unknown"),
        }

        # Save to cache
        return await save_to_cache(metadata)

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching nucleotide data for UID {uid}: {e}")
        return None

def format_assembly_metadata(api_data, accession):
    """Handle RefSeq and GenBank response formats from /genome/accession/ endpoint"""
    try:
        # Extract 'assembly' from the correct nested location
        if "assemblies" in api_data and api_data["assemblies"]:
            assembly = api_data["assemblies"][0].get("assembly", {})
            org = assembly.get("org", {})
            return {
                "database": "assembly",
                "accession": accession,
                "organism": {
                    "sci_name": org.get('sci_name', 'Unknown'),
                    "common_name": org.get('common_name', 'Unknown'),
                    "tax_id": org.get('tax_id')
                },
                "assembly_name": assembly.get('display_name', 'N/A'),
                "assembly_level": assembly.get('assembly_category', 'N/A'),
                "submission_date": assembly.get('submission_date', 'N/A'),
                "ftp_path": assembly.get('ftp_path', ''),
                "last_updated": datetime.utcnow().isoformat()
            }

        # fallback if somehow no assemblies were returned
        logging.warning(f"No valid 'assemblies' found in API data for {accession}")
        return {
            "database": "assembly",
            "accession": accession,
            "organism": {"sci_name": "Unknown"},
            "assembly_name": "N/A",
            "assembly_level": "N/A",
            "submission_date": "N/A",
            "ftp_path": "",
            "last_updated": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logging.error(f"Formatting error for {accession}: {str(e)}")
        return {
            "database": "assembly",
            "accession": accession,
            "organism": {"sci_name": "Unknown"},
            "assembly_name": "N/A",
            "assembly_level": "N/A",
            "submission_date": "N/A",
            "ftp_path": "",
            "last_updated": datetime.utcnow().isoformat()
        }

async def fetch_via_entrez(accession):
    """Entrez fallback for assembly data with better error handling"""
    try:
        handle = Entrez.esearch(db="assembly", term=f"{accession}[Accession]", retmax=1)
        search_results = Entrez.read(handle)
        handle.close()
        
        if not search_results["IdList"]:
            raise HTTPException(status_code=404, detail="Assembly not found in Entrez")
        
        handle = Entrez.esummary(db="assembly", id=search_results["IdList"][0])
        summary = Entrez.read(handle)
        handle.close()
        
        return {
            "database": "assembly",
            "accession": accession,
            "organism": {
                "sci_name": summary["DocumentSummarySet"]["DocumentSummary"][0]["SpeciesName"],
                "tax_id": int(summary["DocumentSummarySet"]["DocumentSummary"][0]["Taxid"])
            },
            "assembly_name": summary["DocumentSummarySet"]["DocumentSummary"][0]["AssemblyName"],
            "assembly_level": summary["DocumentSummarySet"]["DocumentSummary"][0]["AssemblyStatus"],
            "submission_date": summary["DocumentSummarySet"]["DocumentSummary"][0]["SubmissionDate"],
            "ftp_path": summary["DocumentSummarySet"]["DocumentSummary"][0]["FtpPath_Assembly_rpt"],
            "last_updated": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Entrez error: {str(e)}")

async def fetch_assembly_metadata(accession):
    """Main assembly metadata fetcher with enhanced GCA handling and caching"""
    try:
        # Check cache first
        cached_data = await check_cache("assembly", accession)
        if cached_data:
            return cached_data

        base_accession = accession.split('.')[0]
        url = f"https://api.ncbi.nlm.nih.gov/datasets/v1/genome/accession/{base_accession}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30.0)
            logging.info(f"API response for {accession}: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if not data:
                    raise HTTPException(status_code=404, detail="Empty API response")
                
                metadata = format_assembly_metadata(data, accession)
                return await save_to_cache(metadata)
            
            raise HTTPException(status_code=response.status_code, detail="API request failed")
            
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to fetch {accession}: {str(e)}")
        try:
            metadata = await fetch_via_entrez(accession)
            return await save_to_cache(metadata)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"All methods failed: {str(e)}")

@app.get("/search/")
async def search_ncbi(
    database: str = Query(..., description="NCBI database to search (e.g., nucleotide, assembly)"),
    query: Optional[str] = None,
    accession_ids: Optional[List[str]] = Query(None),
    taxid: Optional[int] = None,
    organism: Optional[str] = None,
    gene: Optional[str] = None,
    protein: Optional[str] = None,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
    molecule_type: Optional[str] = None,
    publication_date: Optional[str] = None,
    retmax: int = 10,
):
    """
    Unified endpoint to search NCBI databases (nucleotide and assembly) with caching.
    
    For assembly searches, provide accession_ids.
    For nucleotide searches, use any combination of filters.
    """
    try:
        # Handle assembly searches differently
        if database == "assembly":
            if not accession_ids:
                raise HTTPException(status_code=400, detail="Assembly searches require accession numbers")
            
            metadata = []
            failed_accessions = []
            
            for accession in accession_ids:
                try:
                    assembly_data = await fetch_assembly_metadata(accession)
                    metadata.append(assembly_data)
                except HTTPException as he:
                    logging.error(f"Failed to fetch assembly {accession}: {he.detail}")
                    failed_accessions.append(accession)
                except Exception as e:
                    logging.error(f"Unexpected error fetching assembly {accession}: {str(e)}")
                    failed_accessions.append(accession)
            
            return {
                "database": database,
                "query": f"Assembly accessions: {', '.join(accession_ids)}",
                "metadata": metadata,
                "failed_accessions": failed_accessions,
            }

        # For nucleotide and other standard databases
        search_terms = []
        if query:
            search_terms.append(query)
        
        if taxid and organism:
            logging.warning("Both taxid and organism provided. Using only organism.")
        
        if taxid and not organism:
            search_terms.append(f"txid{taxid}[Organism]")
        elif organism:
            search_terms.append(f'"{organism}"[Organism]')

        if accession_ids:
            search_terms.append(f"({' OR '.join(accession_ids)})[Accession]")

        if gene:
            search_terms.append(f'"{gene}"[Gene]')

        if protein:
            search_terms.append(f'"{protein}"[Protein]')    

        if min_length or max_length:
            length_query = f"{min_length or 0}:{max_length or 100000000}[SLEN]"
            search_terms.append(length_query)

        if molecule_type:
            search_terms.append(f'"{molecule_type}"[Molecule Type]')

        if publication_date:
            search_terms.append(f'"{publication_date}"[Publication Date]')

        # Construct final query string
        search_query = " AND ".join(search_terms).strip()

        if not search_query:
            raise HTTPException(status_code=400, detail="Search query is empty. Please provide valid filters.")

        logging.info(f"Constructed search query: {search_query}")

        # Perform NCBI search
        handle = Entrez.esearch(db=database, term=search_query, retmax=retmax, retmode="xml")
        search_results = Entrez.read(handle)
        handle.close()

        if not search_results["IdList"]:
            return {
                "database": database,
                "query": search_query,
                "metadata": [],
                "failed_uids": [],
            }

        # Fetch metadata for each UID
        metadata = []
        failed_uids = []
        for uid in search_results["IdList"]:
            try:
                if database == "nucleotide":
                    data = await fetch_nucleotide_metadata(uid)
                else:
                    # For other databases, we'd need to implement specific handlers
                    data = None
                
                if data:
                    metadata.append(data)
                else:
                    failed_uids.append(uid)
            except Exception as e:
                logging.error(f"Error fetching metadata for UID {uid}: {str(e)}")
                failed_uids.append(uid)

        return {
            "database": database,
            "query": search_query,
            "metadata": metadata,
            "failed_uids": failed_uids,
        }

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error in /search endpoint: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {"message": "Unified NCBI Metadata API is running"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)