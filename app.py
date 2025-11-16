from fastapi import FastAPI, HTTPException, Query, Request
from typing import List, Optional
from Bio import Entrez
from Bio import SeqIO
from pymongo import MongoClient
from fastapi.middleware.cors import CORSMiddleware
import time
import uvicorn
import traceback
from datetime import datetime
from dotenv import load_dotenv
import asyncio
import logging
import os
from slowapi import Limiter
from slowapi.util import get_remote_address
from pymongo.errors import ConnectionFailure
import requests
import xml.etree.ElementTree as ET
os.environ['https'] = 'https://eutils.ncbi.nlm.nih.gov'
os.environ['http'] = 'https://eutils.ncbi.nlm.nih.gov'

# Load environment variables
load_dotenv()

# Configure email for NCBI API
Entrez.email = os.getenv("NCBI_EMAIL", "abdullah.1970333@studenti.uniroma1.it")
Entrez.api_key = os.getenv("NCBI_API_KEY")

# MongoDB configuration from environment
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://admin2:Cloud786@clusterfull.tn88z.mongodb.net/taxonomy")

# Initialize the client and database
try:
    client = MongoClient(MONGO_URI, maxPoolSize=50, connectTimeoutMS=30000)
    client.admin.command('ping')
    db = client.taxonomy
    print("✅ Connected to MongoDB successfully!")
except Exception as e:
    print(f"❌ Error connecting to MongoDB: {e}")
    db = None  # Continue without MongoDB

# Create FastAPI app
limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
     allow_origins=[
         "http://localhost:8080",
         "http://localhost:8000", 
         "http://localhost:4173",
         "http://localhost:5173",
         "https://ranausama1.github.io",
         "https://ranausama1.github.io/database_test",
         "https://backend-test-g0wm.onrender.com"
     ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Simple rate limiting
last_request_time = 0

# def rate_limit():
#     """Simple rate limiting for NCBI"""
#     global last_request_time
#     current_time = time.time()
#     if current_time - last_request_time < 0.34:
#         time.sleep(0.34 - (current_time - last_request_time))
#     last_request_time = time.time()

def rate_limit():
    """NCBI-compliant rate limiting"""
    global last_request_time
    current_time = time.time()
    min_interval = 0.1  # 10 requests per second with API key
    if current_time - last_request_time < min_interval:
        time.sleep(min_interval - (current_time - last_request_time))
    last_request_time = time.time()

# ========== CACHE FUNCTIONS ==========
async def check_cache(database: str, identifier: str):
    """Check MongoDB cache for existing metadata"""
    if db is None:
        return None
    try:
        cached_data = db.metadata.find_one({"database": database, "accession": identifier})
        if cached_data:
            cached_data["_id"] = str(cached_data["_id"])
            logger.info(f"Cache hit for {database} {identifier}")
            return cached_data
        return None
    except Exception as e:
        logger.error(f"Error checking cache: {e}")
        return None

async def save_to_cache(metadata: dict):
    """Save metadata to MongoDB cache"""
    if db is None:
        return metadata
    try:
        result = db.metadata.insert_one(metadata)
        metadata["_id"] = str(result.inserted_id)
        logger.info(f"Saved metadata for {metadata['database']} {metadata['accession']} to cache")
        return metadata
    except Exception as e:
        logger.error(f"Error saving to cache: {e}")
        return metadata

# ========== ASSEMBLY METADATA FETCHING ==========
# async def fetch_assembly_metadata(accession: str):
#     """Main assembly metadata fetcher - FIXED UID HANDLING"""
#     try:
#         # Check cache first
#         cached_data = await check_cache("assembly", accession)
#         if cached_data:
#             return cached_data

#         logger.info(f"Fetching assembly metadata for: {accession}")
        
#         # Handle UIDs differently - extract numeric part only
#         if accession.startswith('UID_'):
#             uid_number = accession.replace('UID_', '')
#             return await fetch_assembly_by_uid(uid_number)
#         else:
#             # It's a regular accession like GCF_000005845.2
#             return await fetch_assembly_by_accession(accession)
        
#     except Exception as e:
#         logger.error(f"Error fetching assembly metadata for {accession}: {str(e)}")
#         return create_minimal_metadata(accession, f"Error: {str(e)}")

# async def fetch_assembly_metadata(accession: str):
#     """Main assembly metadata fetcher - PREFER ENA when NCBI is down"""
#     try:
#         # Check cache first
#         cached_data = await check_cache("assembly", accession)
#         if cached_data:
#             return cached_data

#         logger.info(f"Fetching assembly metadata for: {accession}")
        
#         # TRY ENA FIRST (more reliable when NCBI is down)
#         logger.info("Trying ENA first due to NCBI issues...")
#         ena_data = await fetch_ena_metadata(accession)
#         if ena_data and ena_data.get("organism", {}).get("sci_name") != "Unknown":
#             logger.info(f"✅ ENA success for {accession}")
#             return await save_to_cache(ena_data)
        
#         # Fallback to NCBI if ENA fails
#         if accession.startswith('UID_'):
#             uid_number = accession.replace('UID_', '')
#             ncbi_data = await fetch_assembly_by_uid(uid_number)
#         else:
#             ncbi_data = await fetch_assembly_by_accession(accession)
            
#         if ncbi_data:
#             return await save_to_cache(ncbi_data)
        
#         return create_minimal_metadata(accession, "All sources failed")
        
#     except Exception as e:
#         logger.error(f"Error fetching assembly metadata for {accession}: {str(e)}")
#         return create_minimal_metadata(accession, f"Error: {str(e)}")

async def fetch_assembly_metadata(accession: str):
    """Main assembly metadata fetcher with enhanced fallback"""
    try:
        # Check cache first
        cached_data = await check_cache("assembly", accession)
        if cached_data:
            return cached_data

        logger.info(f"Fetching assembly metadata for: {accession}")
        
        approaches = [
            {"name": "ENA", "func": fetch_ena_metadata},
            {"name": "NCBI Assembly", "func": fetch_assembly_by_accession},
            {"name": "NCBI Datasets", "func": fetch_ncbi_datasets_direct},
        ]
        
        for approach in approaches:
            try:
                logger.info(f"Trying {approach['name']} for {accession}")
                data = await approach['func'](accession)
                
                if data and is_valid_assembly_data(data):
                    logger.info(f"✅ {approach['name']} success for {accession}")
                    
                    # Enhance with additional statistics if missing
                    if missing_stats(data):
                        enhanced_stats = await fetch_enhanced_assembly_stats(accession)
                        if enhanced_stats:
                            data.update(enhanced_stats)
                            data['additional_info'] = f"Data from {approach['name']} with enhanced statistics"
                    
                    return await save_to_cache(data)
                    
            except Exception as e:
                logger.warning(f"{approach['name']} failed for {accession}: {str(e)}")
                continue
        
        # All approaches failed
        logger.error(f"All approaches failed for {accession}")
        return create_minimal_metadata(accession, "All data sources failed")
        
    except Exception as e:
        logger.error(f"Error fetching assembly metadata for {accession}: {str(e)}")
        return create_minimal_metadata(accession, f"Error: {str(e)}")

def is_valid_assembly_data(data: dict) -> bool:
    """Check if assembly data is valid and has basic information"""
    if not data or data.get("database") == "minimal":
        return False
    
    organism = data.get("organism", {})
    sci_name = organism.get("sci_name", "")
    
    # Consider data valid if it has a scientific name or assembly name
    return (
        sci_name not in ["Unknown", None, ""] or
        data.get("assembly_name") not in ["Unknown", None, ""]
    )

def missing_stats(data: dict) -> bool:
    """Check if critical statistics are missing"""
    return (
        data.get("genome_size") in ["N/A", None, ""] or
        data.get("contig_n50") in ["N/A", None, ""] or
        data.get("gc_percent") in ["N/A", None, ""]
    )

async def fetch_ncbi_datasets_direct(accession: str):
    """Direct NCBI Datasets API fetch"""
    try:
        url = f"https://api.ncbi.nlm.nih.gov/datasets/v2alpha/assembly/{accession}"
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; ResearchApp/1.0)"
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            return parse_ncbi_datasets_response(data, accession)
        return None
    except Exception as e:
        logger.debug(f"NCBI Datasets direct fetch failed: {str(e)}")
        return None

def parse_ncbi_datasets_response(data: dict, accession: str):
    """Parse NCBI Datasets API response"""
    try:
        if 'assembly' not in data:
            return None
            
        assembly_data = data['assembly']
        org_info = assembly_data.get('org', {})
        
        return {
            "database": "assembly",
            "accession": accession,
            "organism": {
                "sci_name": org_info.get('sci_name', 'Unknown'),
                "common_name": org_info.get('common_name', 'Unknown'),
                "tax_id": str(org_info.get('tax_id', 'N/A'))
            },
            "assembly_name": assembly_data.get('assembly_name', f'Assembly {accession}'),
            "assembly_level": assembly_data.get('assembly_level', 'N/A'),
            "submission_date": assembly_data.get('submit_date', 'N/A'),
            # Add other fields as needed
            "ftp_path": f"https://www.ncbi.nlm.nih.gov/datasets/genome/{accession}/",
            "additional_info": "Data from NCBI Datasets API",
            "last_updated": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.debug(f"Error parsing NCBI Datasets response: {str(e)}")
        return None


async def fetch_assembly_by_uid(uid: str):
    """Fetch assembly metadata using UID - ENHANCED VERSION"""
    try:
        logger.info(f"Fetching assembly by UID: {uid}")
        rate_limit()
        
        # Directly get summary using the UID
        handle = Entrez.esummary(db="assembly", id=uid, retmode="xml")
        summary_data = Entrez.read(handle, validate=False)
        handle.close()
        
        result = parse_assembly_summary(summary_data, f"UID_{uid}")
        
        # ENHANCEMENT: If we're missing critical statistics, try to fetch them
        if result and (result.get('genome_size') == 'N/A' or result.get('contig_n50') == 'N/A'):
            logger.info(f"Fetching enhanced stats for UID_{uid}")
            enhanced_stats = await fetch_enhanced_assembly_stats(f"UID_{uid}")
            if enhanced_stats:
                # Merge the enhanced statistics
                result.update(enhanced_stats)
                result['additional_info'] = "Data from NCBI Assembly with enhanced statistics"
        
        if result:
            return await save_to_cache(result)
        else:
            return create_minimal_metadata(f"UID_{uid}", "No data found in NCBI")
        
    except Exception as e:
        logger.error(f"Error fetching assembly by UID {uid}: {str(e)}")
        return create_minimal_metadata(f"UID_{uid}", f"UID fetch failed: {str(e)}")

async def fetch_assembly_by_accession(accession: str):
    """Fetch assembly metadata using accession number - ENHANCED VERSION"""
    try:
        base_accession = accession.split('.')[0]
        
        # Search for assembly
        rate_limit()
        handle = Entrez.esearch(
            db="assembly", 
            term=f"{base_accession}[Accession]",
            retmax=1
        )
        search_result = Entrez.read(handle)
        handle.close()
        
        if not search_result.get("IdList"):
            logger.warning(f"No assembly found in NCBI for {accession}")
            # Try ENA as fallback
            ena_data = await fetch_ena_metadata(accession)
            if ena_data:
                return await save_to_cache(ena_data)
            return create_minimal_metadata(accession, "No assembly found")
            
        assembly_id = search_result["IdList"][0]
        
        # Get summary
        rate_limit()
        handle = Entrez.esummary(db="assembly", id=assembly_id, retmode="xml")
        summary_data = Entrez.read(handle, validate=False)
        handle.close()
        
        result = parse_assembly_summary(summary_data, accession)
        
        # ENHANCEMENT: If we're missing critical statistics, try to fetch them
        if result and (result.get('genome_size') == 'N/A' or result.get('contig_n50') == 'N/A'):
            logger.info(f"Fetching enhanced stats for {accession}")
            enhanced_stats = await fetch_enhanced_assembly_stats(accession)
            if enhanced_stats:
                # Merge the enhanced statistics
                result.update(enhanced_stats)
                result['additional_info'] = "Data from NCBI Assembly with enhanced statistics"
        
        if result:
            return await save_to_cache(result)
        else:
            # Try ENA if NCBI parsing failed
            ena_data = await fetch_ena_metadata(accession)
            if ena_data:
                return await save_to_cache(ena_data)
            return create_minimal_metadata(accession, "NCBI data parsing failed")
        
    except Exception as e:
        logger.error(f"Error fetching assembly by accession {accession}: {str(e)}")
        ena_data = await fetch_ena_metadata(accession)
        if ena_data:
            return await save_to_cache(ena_data)
        return create_minimal_metadata(accession, f"Fetch error: {str(e)}")
    
def parse_assembly_summary(summary_data, accession: str):
    """Parse assembly summary data from NCBI"""
    try:
        if "DocumentSummarySet" not in summary_data:
            return None
            
        doc_summary = summary_data["DocumentSummarySet"].get("DocumentSummary", [])
        if not doc_summary:
            return None
            
        summary = doc_summary[0]
        
        # Convert to dictionary to handle both types of objects
        if hasattr(summary, 'items'):
            summary_dict = dict(summary.items())
        else:
            summary_dict = {}
            for attr in dir(summary):
                if not attr.startswith('_') and not callable(getattr(summary, attr)):
                    try:
                        summary_dict[attr] = getattr(summary, attr)
                    except:
                        pass
        
        # Extract fields with fallbacks
        sci_name = summary_dict.get("SpeciesName", "Unknown")
        tax_id = str(summary_dict.get("Taxid", "N/A"))
        common_name = summary_dict.get("CommonName", "Unknown")
        assembly_name = summary_dict.get("AssemblyName", f"Assembly {accession}")
        
        # Get FTP path
        ftp_path = summary_dict.get("FtpPath_GenBank", "")
        if not ftp_path:
            ftp_path = summary_dict.get("FtpPath_RefSeq", "")
        if not ftp_path:
            ftp_path = f"https://www.ncbi.nlm.nih.gov/datasets/genome/{accession}/"
        
        # Try to extract metadata from Meta field if available
        meta_data = {}
        if "Meta" in summary_dict:
            try:
                meta_xml = f"<root>{summary_dict['Meta']}</root>"
                meta_root = ET.fromstring(meta_xml)
                meta_data = {child.tag: child.text for child in meta_root}
            except:
                pass
        
        return {
            "database": "assembly",
            "accession": summary_dict.get("AssemblyAccession", accession),
            "organism": {
                "sci_name": sci_name,
                "common_name": common_name,
                "tax_id": tax_id
            },
            "assembly_name": assembly_name,
            "assembly_level": summary_dict.get("AssemblyStatus", "N/A"),
            "submission_date": summary_dict.get("SubmissionDate", "N/A"),
            "update_date": summary_dict.get("LastUpdateDate", "N/A"),
            "genome_size": meta_data.get("GenomeLength", summary_dict.get("BpLength", "N/A")),
            "contig_n50": meta_data.get("ContigN50", "N/A"),
            "number_of_contigs": meta_data.get("ContigCount", "N/A"),
            "gc_percent": meta_data.get("GCPercent", "N/A"),
            "ftp_path": ftp_path,
            "biosample": summary_dict.get("BioSampleAccn", "N/A"),
            "bioproject": summary_dict.get("BioProjectAccn", "N/A"),
            "additional_info": "Data from NCBI Assembly",
            "last_updated": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error parsing assembly summary for {accession}: {str(e)}")
        return None

# ========== ENHANCED STATISTICS FUNCTIONS ==========

async def fetch_enhanced_assembly_stats(accession: str):
    """Enhanced statistics fetcher that tries multiple sources"""
    try:
        base_accession = accession.split('.')[0]
        
        # Try multiple FTP paths for assembly stats
        ftp_paths = []
        
        if accession.startswith('GCF_'):
            # RefSeq path
            path_part = base_accession.replace('GCF_', '')
            ftp_paths.append(
                f"https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/{path_part[:3]}/{path_part[3:6]}/{path_part[6:9]}/{base_accession}_{base_accession}/{base_accession}_{base_accession}_assembly_stats.txt"
            )
            # Also try GenBank equivalent
            gca_accession = base_accession.replace('GCF_', 'GCA_')
            path_part_gca = gca_accession.replace('GCA_', '')
            ftp_paths.append(
                f"https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/{path_part_gca[:3]}/{path_part_gca[3:6]}/{path_part_gca[6:9]}/{gca_accession}_{gca_accession}/{gca_accession}_{gca_accession}_assembly_stats.txt"
            )
        else:
            # GenBank path
            path_part = base_accession.replace('GCA_', '')
            ftp_paths.append(
                f"https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/{path_part[:3]}/{path_part[3:6]}/{path_part[6:9]}/{base_accession}_{base_accession}/{base_accession}_{base_accession}_assembly_stats.txt"
            )
        
        # Try each FTP path
        for ftp_path in ftp_paths:
            try:
                logger.info(f"Trying FTP path: {ftp_path}")
                response = requests.get(ftp_path, timeout=10)
                if response.status_code == 200:
                    stats = parse_assembly_stats_file(response.text)
                    if stats:
                        logger.info(f"✅ Found assembly stats for {accession}")
                        return stats
            except Exception as e:
                logger.debug(f"FTP path failed: {ftp_path}, error: {str(e)}")
                continue
        
        # If FTP fails, try NCBI Datasets API for statistics
        return await fetch_ncbi_datasets_stats(accession)
        
    except Exception as e:
        logger.warning(f"Enhanced stats fetch failed for {accession}: {str(e)}")
        return None

def parse_assembly_stats_file(stats_text: str):
    """Parse assembly statistics from NCBI stats file"""
    stats = {}
    try:
        lines = stats_text.split('\n')
        for line in lines:
            line = line.strip()
            if 'total length' in line.lower() and 'scaffold' not in line.lower():
                # Extract number from line like "total length: 4641652"
                parts = line.split(':')
                if len(parts) > 1:
                    stats['genome_size'] = parts[1].strip().split()[0]  # Take first number
            elif 'contig n50' in line.lower():
                parts = line.split(':')
                if len(parts) > 1:
                    stats['contig_n50'] = parts[1].strip().split()[0]
            elif 'number of contigs' in line.lower():
                parts = line.split(':')
                if len(parts) > 1:
                    stats['number_of_contigs'] = parts[1].strip().split()[0]
            elif 'gc' in line.lower() and '%' in line.lower():
                parts = line.split(':')
                if len(parts) > 1:
                    stats['gc_percent'] = parts[1].strip().replace('%', '')
        
        return stats if stats else None
    except Exception as e:
        logger.error(f"Error parsing assembly stats file: {str(e)}")
        return None

async def fetch_ncbi_datasets_stats(accession: str):
    """Try NCBI Datasets API for assembly statistics"""
    try:
        url = f"https://api.ncbi.nlm.nih.gov/datasets/v1/assembly/{accession}"
        headers = {"Accept": "application/json"}
        
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            return parse_datasets_stats(data)
        return None
    except Exception as e:
        logger.debug(f"NCBI Datasets stats failed: {str(e)}")
        return None

def parse_datasets_stats(data: dict):
    """Parse statistics from NCBI Datasets API response"""
    try:
        stats = {}
        if 'assembly' in data and 'assembly_stats' in data['assembly']:
            stats_data = data['assembly']['assembly_stats']
            stats['genome_size'] = stats_data.get('total_sequence_length')
            stats['contig_n50'] = stats_data.get('contig_n50')
            stats['number_of_contigs'] = stats_data.get('number_of_contigs')
            stats['gc_percent'] = stats_data.get('gc_percent')
        
        return stats if any(stats.values()) else None
    except Exception as e:
        logger.debug(f"Error parsing datasets stats: {str(e)}")
        return None


# async def fetch_ena_metadata(accession: str):
#     """Fetch metadata from ENA as fallback"""
#     try:
#         base_accession = accession.split('.')[0]
        
#         # Try ENA endpoint
#         url = f"https://www.ebi.ac.uk/ena/portal/api/filereport?accession={base_accession}&result=assembly&format=json"
        
#         response = requests.get(url, timeout=10)
#         if response.status_code == 200:
#             data = response.json()
#             if data and isinstance(data, list) and len(data) > 0:
#                 ena_data = parse_ena_response(data[0], accession)
#                 if ena_data:
#                     logger.info(f"✅ ENA data found for {accession}")
#                     return ena_data
        
#         return None
        
#     except Exception as e:
#         logger.warning(f"ENA fetch failed for {accession}: {str(e)}")
#         return None

# async def fetch_ena_metadata(accession: str):
#     """Fetch metadata from ENA as fallback"""
#     try:
#         base_accession = accession.split('.')[0]
        
#         # Try ENA endpoint
#         url = f"https://www.ebi.ac.uk/ena/portal/api/filereport?accession={base_accession}&result=assembly&format=json"
        
#         logger.info(f"Fetching ENA data from: {url}")
#         response = requests.get(url, timeout=10)
        
#         if response.status_code == 200:
#             data = response.json()
#             logger.info(f"ENA raw response: {data}")
            
#             if data and isinstance(data, list) and len(data) > 0:
#                 ena_item = data[0]
#                 logger.info(f"ENA item keys: {ena_item.keys()}")
                
#                 ena_data = parse_ena_response(ena_item, accession)
#                 logger.info(f"Parsed ENA data: {ena_data}")
                
#                 if ena_data and ena_data.get("organism", {}).get("sci_name") not in ["Unknown", None, ""]:
#                     logger.info(f"✅ ENA data found for {accession}")
#                     return ena_data
#                 else:
#                     logger.warning(f"ENA data has invalid organism name for {accession}")
        
#         logger.warning(f"No valid ENA data found for {accession}")
#         return None
        
#     except Exception as e:
#         logger.warning(f"ENA fetch failed for {accession}: {str(e)}")
#         return None

async def fetch_ena_metadata(accession: str):
    """Fetch metadata from ENA as fallback"""
    try:
        base_accession = accession.split('.')[0]
        
        # Try ENA endpoint
        url = f"https://www.ebi.ac.uk/ena/portal/api/filereport?accession={base_accession}&result=assembly&fields=all&format=json"
        
        logger.info(f"Fetching ENA data from: {url}")
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"ENA response status: {response.status_code}")
            logger.info(f"ENA raw response type: {type(data)}")
            logger.info(f"ENA raw response length: {len(data) if isinstance(data, list) else 'not a list'}")
            
            if data and isinstance(data, list) and len(data) > 0:
                ena_item = data[0]
                logger.info(f"ENA item type: {type(ena_item)}")
                logger.info(f"ENA item: {ena_item}")
                
                # Check what fields are available
                if ena_item:
                    logger.info(f"ENA item keys: {list(ena_item.keys())}")
                    
                    # Check for scientific name in different possible fields
                    sci_name = ena_item.get('scientific_name') or ena_item.get('organism_name') or ena_item.get('species')
                    logger.info(f"ENA scientific name found: {sci_name}")
                    
                    ena_data = parse_ena_response(ena_item, accession)
                    if ena_data:
                        logger.info(f"✅ Valid ENA data parsed for {accession}")
                        return ena_data
                    else:
                        logger.warning(f"❌ ENA data parsing failed for {accession}")
            else:
                logger.warning(f"ENA returned empty or invalid response for {accession}")
        
        logger.warning(f"No valid ENA data found for {accession}, status: {response.status_code}")
        return None
        
    except Exception as e:
        logger.warning(f"ENA fetch failed for {accession}: {str(e)}")
        return None

# def parse_ena_response(ena_data, accession: str):
#     """Parse ENA API response"""
#     try:
#         return {
#             "database": "ena",
#             "accession": accession,
#             "organism": {
#                 "sci_name": ena_data.get("scientific_name", "Unknown"),
#                 "common_name": ena_data.get("common_name", "Unknown"),
#                 "tax_id": str(ena_data.get("tax_id", "N/A"))
#             },
#             "assembly_name": ena_data.get("assembly_name", f"Assembly {accession.split('.')[0]}"),
#             "assembly_level": ena_data.get("assembly_level", "N/A"),
#             "submission_date": ena_data.get("first_public", "N/A"),
#             "genome_size": ena_data.get("total_length", "N/A"),
#             "contig_n50": ena_data.get("contig_n50", "N/A"),
#             "number_of_contigs": ena_data.get("number_of_contigs", "N/A"),
#             "gc_percent": ena_data.get("gc_percent", "N/A"),
#             "ftp_path": ena_data.get("ftp_path", f"https://www.ebi.ac.uk/ena/browser/view/{accession}"),
#             "additional_info": "Data from European Nucleotide Archive",
#             "last_updated": datetime.utcnow().isoformat()
#         }
#     except Exception as e:
#         logger.error(f"Error parsing ENA response: {str(e)}")
#         return None

def parse_ena_response(ena_data, accession: str):
    """Parse ENA API response with flexible field mapping"""
    try:
        # Flexible field mapping - ENA uses different field names
        sci_name = (
            ena_data.get("scientific_name") or 
            ena_data.get("organism_name") or 
            ena_data.get("species") or 
            ena_data.get("organism") or
            "Unknown"
        )
        
        common_name = ena_data.get("common_name") or ena_data.get("strain") or "Unknown"
        tax_id = str(ena_data.get("tax_id") or ena_data.get("taxid") or "N/A")
        
        assembly_name = (
            ena_data.get("assembly_name") or 
            ena_data.get("name") or 
            f"Assembly {accession.split('.')[0]}"
        )
        
        assembly_level = ena_data.get("assembly_level") or ena_data.get("level") or "N/A"
        
        # Try different field names for statistics
        genome_size = (
            ena_data.get("total_length") or 
            ena_data.get("genome_length") or 
            ena_data.get("size") or
            "N/A"
        )
        
        contig_n50 = ena_data.get("contig_n50") or ena_data.get("n50") or "N/A"
        number_of_contigs = ena_data.get("number_of_contigs") or ena_data.get("contig_count") or "N/A"
        gc_percent = ena_data.get("gc_percent") or ena_data.get("gc_content") or "N/A"
        
        # Construct FTP path
        ftp_path = ena_data.get("ftp_path")
        if not ftp_path:
            ftp_path = f"https://www.ebi.ac.uk/ena/browser/view/{accession}"
        
        result = {
            "database": "ena",
            "accession": accession,
            "organism": {
                "sci_name": sci_name,
                "common_name": common_name,
                "tax_id": tax_id
            },
            "assembly_name": assembly_name,
            "assembly_level": assembly_level,
            "submission_date": ena_data.get("first_public") or ena_data.get("submission_date") or "N/A",
            "genome_size": genome_size,
            "contig_n50": contig_n50,
            "number_of_contigs": number_of_contigs,
            "gc_percent": gc_percent,
            "ftp_path": ftp_path,
            "additional_info": "Data from European Nucleotide Archive",
            "last_updated": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Parsed ENA data for {accession}: {result['organism']['sci_name']}")
        return result
        
    except Exception as e:
        logger.error(f"Error parsing ENA response for {accession}: {str(e)}")
        return None

def create_minimal_metadata(accession: str, reason: str):
    """Create minimal metadata when all sources fail"""
    return {
        "database": "minimal",
        "accession": accession,
        "organism": {"sci_name": "Unknown", "common_name": "Unknown", "tax_id": "N/A"},
        "assembly_name": f"Assembly {accession.split('.')[0] if '.' in accession else accession}",
        "additional_info": f"Limited data: {reason}",
        "ftp_path": f"https://www.ncbi.nlm.nih.gov/datasets/genome/{accession}/",
        "last_updated": datetime.utcnow().isoformat()
    }

# ========== SEARCH ENDPOINTS ==========


# @app.get("/search/")
# @limiter.limit("10/minute")
# async def search_ncbi(
#     request: Request,
#     database: str = Query(..., description="NCBI database to search"),
#     query: Optional[str] = None,
#     accession_ids: Optional[str] = None,
#     taxid: Optional[int] = None,
#     organism: Optional[str] = None,
#     retmax: int = 20,
# ):
#     """Main search endpoint"""
#     try:
#         if database == "assembly":
#             return await search_assemblies(organism, taxid, accession_ids, retmax)
#         else:
#             return await search_other_databases(database, query, organism, taxid, accession_ids, retmax)

#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error in /search endpoint: {str(e)}\n{traceback.format_exc()}")
#         raise HTTPException(status_code=500, detail=str(e))

# @app.get("/search/")
# @limiter.limit("10/minute")
# async def search_ncbi(
#     request: Request,
#     database: str = Query(..., description="NCBI database to search"),
#     query: Optional[str] = None,
#     accession_ids: Optional[str] = None,
#     taxid: Optional[int] = None,
#     organism: Optional[str] = None,
#     retmax: int = 20,
# ):
#     """Main search endpoint"""
#     try:
#         # Normalize database parameter
#         database = database.lower().strip()
        
#         # Validate database
#         supported_databases = ["assembly", "nucleotide", "gene", "taxonomy", "protein"]
#         if database not in supported_databases:
#             raise HTTPException(
#                 status_code=400, 
#                 detail=f"Database '{database}' is not supported. Supported: {', '.join(supported_databases)}"
#             )
        
#         logger.info(f"🔍 Search request - Database: {database}")
        
#         if database == "assembly":
#             logger.info("✅ Routing to search_assemblies")
#             return await search_assemblies(organism, taxid, accession_ids, retmax)
#         else:
#             logger.info(f"🔍 Routing to search_other_databases for: {database}")
#             return await search_other_databases(database, query, organism, taxid, accession_ids, retmax)

#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error in /search endpoint: {str(e)}\n{traceback.format_exc()}")
#         raise HTTPException(status_code=500, detail=str(e))

@app.get("/search/")
@limiter.limit("10/minute")
async def search_ncbi(
    request: Request,
    database: str = Query(..., description="NCBI database to search"),
    query: Optional[str] = None,
    accession_ids: Optional[str] = None,
    taxid: Optional[int] = None,
    organism: Optional[str] = None,
    retmax: int = 20,
):
    """Main search endpoint"""
    try:
        # Normalize database parameter
        database = database.lower().strip()
        
        # Validate database
        supported_databases = ["assembly", "nucleotide", "gene", "taxonomy", "protein"]
        if database not in supported_databases:
            raise HTTPException(
                status_code=400, 
                detail=f"Database '{database}' is not supported. Supported: {', '.join(supported_databases)}"
            )
        
        logger.info(f"🔍 Search request - Database: {database}, Organism: {organism}, Accessions: {accession_ids}")
        
        if database == "assembly":
            logger.info("✅ Routing to search_assemblies")
            return await search_assemblies(organism, taxid, accession_ids, retmax)
        else:
            logger.info(f"🔍 Routing to search_other_databases for: {database}")
            return await search_other_databases(database, query, organism, taxid, accession_ids, retmax)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in /search endpoint: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

# async def search_assemblies(organism: Optional[str], taxid: Optional[int], accession_ids: Optional[str], retmax: int):
#     """Search for assemblies"""
#     search_terms = []
    
#     # Build search terms
#     if accession_ids:
#         accession_list = [uid.strip() for uid in accession_ids.split(",") if uid.strip()]
#         if accession_list:
#             search_terms.append(f"({' OR '.join(accession_list)})[Accession]")
    
#     if taxid:
#         search_terms.append(f"txid{taxid}[Organism]")
    
#     if organism:
#         search_terms.append(f'"{organism}"[Organism]')
    
#     if not search_terms:
#         raise HTTPException(status_code=400, detail="Assembly search requires organism name, taxid, or accession numbers")
    
#     # Construct final query
#     search_query = " AND ".join(search_terms).strip()
#     logger.info(f"Assembly search query: {search_query}")
    
#     try:
#         rate_limit()
        
#         # Search for assembly IDs
#         handle = Entrez.esearch(db="assembly", term=search_query, retmax=retmax)
#         search_results = Entrez.read(handle)
#         handle.close()
        
#         if not search_results["IdList"]:
#             return {
#                 "database": "assembly",
#                 "query": search_query,
#                 "metadata": [],
#                 "failed_accessions": [],
#                 "message": "No assemblies found"
#             }
        
#         # Fetch metadata for each assembly
#         metadata = []
#         failed_accessions = []
        
#         for uid in search_results["IdList"]:
#             try:
#                 # Use the UID to fetch metadata
#                 assembly_data = await fetch_assembly_metadata(f"UID_{uid}")
#                 metadata.append(assembly_data)
                    
#             except Exception as e:
#                 logger.error(f"Error fetching assembly {uid}: {str(e)}")
#                 failed_accessions.append(f"UID_{uid}")
        
#         return {
#             "database": "assembly",
#             "query": search_query,
#             "metadata": metadata,
#             "failed_accessions": failed_accessions,
#         }
        
#     except Exception as e:
#         logger.error(f"Assembly search error: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

async def direct_accession_search(accession_list: List[str], search_query: str, retmax: int):
    """Directly fetch assemblies by accession without NCBI search"""
    metadata = []
    failed_accessions = []
    
    # Add a safety check
    if not accession_list:
        return {
            "database": "assembly",
            "query": search_query,
            "metadata": [],
            "failed_accessions": [],
            "message": "No accessions provided for direct search"
        }
    
    for accession in accession_list:
        try:
            logger.info(f"Direct fetch for accession: {accession}")
            assembly_data = await fetch_assembly_metadata(accession)
            
            # FIXED: Better condition to check if we have valid data
            if (assembly_data and 
                assembly_data.get("database") != "minimal" and 
                assembly_data.get("accession") and
                (assembly_data.get("organism", {}).get("sci_name") not in ["Unknown", None, ""] or
                 assembly_data.get("assembly_name") not in ["Unknown", None, ""])):
                
                metadata.append(assembly_data)
                logger.info(f"✅ Successfully fetched {accession}")
            else:
                failed_accessions.append(accession)
                logger.warning(f"❌ Failed to fetch valid data for {accession}")
                
        except Exception as e:
            logger.error(f"Error fetching assembly {accession}: {str(e)}")
            failed_accessions.append(accession)
    
    return {
        "database": "assembly",
        "query": search_query,
        "metadata": metadata,
        "failed_accessions": failed_accessions,
        "message": f"Direct accession search - {len(metadata)} succeeded, {len(failed_accessions)} failed"
    }

# async def direct_accession_search(accession_list: List[str], search_query: str, retmax: int):
#     """Directly fetch assemblies by accession without NCBI search"""
#     metadata = []
#     failed_accessions = []
    
#     # Add a safety check
#     if not accession_list:
#         return {
#             "database": "assembly",
#             "query": search_query,
#             "metadata": [],
#             "failed_accessions": [],
#             "message": "No accessions provided for direct search"
#         }

#     for accession in accession_list:
#         try:
#             logger.info(f"Direct fetch for accession: {accession}")
#             assembly_data = await fetch_assembly_metadata(accession)
#             if assembly_data and assembly_data.get("organism", {}).get("sci_name") != "Unknown":
#                 metadata.append(assembly_data)
#                 logger.info(f"✅ Successfully fetched {accession}")
#             else:
#                 failed_accessions.append(accession)
#                 logger.warning(f"❌ Failed to fetch {accession}")
#         except Exception as e:
#             logger.error(f"Error fetching assembly {accession}: {str(e)}")
#             failed_accessions.append(accession)
    
#     return {
#         "database": "assembly",
#         "query": search_query,
#         "metadata": metadata,
#         "failed_accessions": failed_accessions,
#         "message": f"Direct accession search - {len(metadata)} succeeded, {len(failed_accessions)} failed"
#     }

async def direct_accession_search(accession_list: List[str], search_query: str, retmax: int):
    """Directly fetch assemblies by accession without NCBI search"""
    metadata = []
    failed_accessions = []
    
    # Add a safety check
    if not accession_list:
        return {
            "database": "assembly",
            "query": search_query,
            "metadata": [],
            "failed_accessions": [],
            "message": "No accessions provided for direct search"
        }
    
    for accession in accession_list:
        try:
            logger.info(f"Direct fetch for accession: {accession}")
            assembly_data = await fetch_assembly_metadata(accession)
            
            # FIXED: Better condition to check if we have valid data
            if (assembly_data and 
                assembly_data.get("database") != "minimal" and 
                assembly_data.get("accession") and
                (assembly_data.get("organism", {}).get("sci_name") not in ["Unknown", None, ""] or
                 assembly_data.get("assembly_name") not in ["Unknown", None, ""])):
                
                metadata.append(assembly_data)
                logger.info(f"✅ Successfully fetched {accession}")
            else:
                failed_accessions.append(accession)
                logger.warning(f"❌ Failed to fetch valid data for {accession}")
                
        except Exception as e:
            logger.error(f"Error fetching assembly {accession}: {str(e)}")
            failed_accessions.append(accession)
    
    return {
        "database": "assembly",
        "query": search_query,
        "metadata": metadata,
        "failed_accessions": failed_accessions,
        "message": f"Direct accession search - {len(metadata)} succeeded, {len(failed_accessions)} failed"
    }

async def standard_ncbi_assembly_search(search_query: str, retmax: int):
    """Standard NCBI assembly search for organism/taxid queries"""
    try:
        rate_limit()
        
        # Search for assembly IDs
        handle = Entrez.esearch(
            db="assembly", 
            term=search_query, 
            retmax=retmax,
            retmode="xml"
        )
        search_results = Entrez.read(handle)
        handle.close()
        
        if not search_results["IdList"]:
            return {
                "database": "assembly",
                "query": search_query,
                "metadata": [],
                "failed_accessions": [],
                "message": "No assemblies found"
            }
        
        # Fetch metadata for each assembly
        metadata = []
        failed_accessions = []
        
        for uid in search_results["IdList"]:
            try:
                assembly_data = await fetch_assembly_metadata(f"UID_{uid}")
                metadata.append(assembly_data)
            except Exception as e:
                logger.error(f"Error fetching assembly {uid}: {str(e)}")
                failed_accessions.append(f"UID_{uid}")
        
        return {
            "database": "assembly",
            "query": search_query,
            "metadata": metadata,
            "failed_accessions": failed_accessions,
        }
        
    except Exception as e:
        logger.error(f"NCBI assembly search failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Assembly search failed: {str(e)}")
    
    
async def search_assemblies(organism: Optional[str], taxid: Optional[int], accession_ids: Optional[str], retmax: int):
    """Search for assemblies with robust error handling"""
    search_terms = []
    accession_list = []
    
    # Parse accession IDs if provided
    if accession_ids and accession_ids.strip():
        accession_list = [acc.strip() for acc in accession_ids.split(",") if acc.strip()]
        if accession_list:
            accession_terms = [f'"{acc}"[Accession]' for acc in accession_list]
            search_terms.append(f"({' OR '.join(accession_terms)})")
    
    # Add organism filter if provided
    if organism and organism.strip():
        search_terms.append(f'"{organism.strip()}"[Organism]')
    
    # Add taxid filter if provided
    if taxid:
        search_terms.append(f"txid{taxid}[Organism]")
    
    # Validate we have at least one search criterion
    if not search_terms:
        raise HTTPException(
            status_code=400, 
            detail="Assembly search requires organism name, taxid, or accession numbers"
        )
    
    # Construct final query
    search_query = " AND ".join(search_terms).strip()
    logger.info(f"Assembly search query: {search_query}")
    
    # Determine search strategy
    has_accessions_only = bool(accession_list) and not organism and not taxid
    has_mixed_criteria = bool(accession_list) and (organism or taxid)
    
    if has_accessions_only:
        logger.info("Direct accession search detected, using optimized approach")
        return await direct_accession_search(accession_list, search_query, retmax)
    elif has_mixed_criteria:
        logger.info("Mixed criteria search, using standard NCBI search")
        return await standard_ncbi_assembly_search(search_query, retmax)
    else:
        logger.info("Organism/taxid only search, using standard NCBI search")
        return await standard_ncbi_assembly_search(search_query, retmax)

async def fallback_direct_accession_search(accession_list, search_query):
    """Fallback: try to fetch each accession directly without NCBI search"""
    metadata = []
    failed_accessions = []
    
    for accession in accession_list:
        try:
            logger.info(f"Fallback: Direct fetch for {accession}")
            # Try to fetch the assembly directly by accession
            assembly_data = await fetch_assembly_metadata(accession)
            if assembly_data and assembly_data.get("organism", {}).get("sci_name") != "Unknown":
                metadata.append(assembly_data)
            else:
                failed_accessions.append(accession)
        except Exception as e:
            logger.error(f"Fallback failed for {accession}: {str(e)}")
            failed_accessions.append(accession)
    
    return {
        "database": "assembly",
        "query": search_query,
        "metadata": metadata,
        "failed_accessions": failed_accessions,
        "message": f"Used fallback method - {len(metadata)} succeeded, {len(failed_accessions)} failed"
    }

async def search_other_databases(database, query, organism, taxid, accession_ids, retmax):
    """Search other NCBI databases"""
    supported_databases = ["nucleotide", "gene", "taxonomy", "protein"]
    
    if database not in supported_databases:
        raise HTTPException(
            status_code=400, 
            detail=f"Database '{database}' is not supported. Supported: {', '.join(supported_databases)}"
        )

    search_terms = []
    
    if query:
        search_terms.append(query)
    if taxid:
        search_terms.append(f"txid{taxid}[Organism]")
    if organism:
        search_terms.append(f'"{organism}"[Organism]')
    if accession_ids:
        accession_list = [uid.strip() for uid in accession_ids.split(",") if uid.strip()]
        if accession_list:
            search_terms.append(f"({' OR '.join(accession_list)})[Accession]")

    search_query = " AND ".join(search_terms).strip() if search_terms else ""
    
    if not search_query:
        raise HTTPException(status_code=400, detail="Search query is empty")
    
    try:
        rate_limit()
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

        metadata = []
        failed_uids = []
        
        for uid in search_results["IdList"]:
            try:
                if database == "nucleotide":
                    data = await fetch_nucleotide_metadata(uid)
                elif database == "gene":
                    data = await fetch_gene_metadata(uid)
                elif database == "taxonomy":
                    data = await fetch_taxonomy_metadata(uid)
                else:
                    data = None
                
                if data:
                    metadata.append(data)
                else:
                    failed_uids.append(uid)
            except Exception as e:
                logger.error(f"Error fetching metadata for UID {uid}: {str(e)}")
                failed_uids.append(uid)

        return {
            "database": database,
            "query": search_query,
            "metadata": metadata,
            "failed_uids": failed_uids,
        }
        
    except Exception as e:
        logger.error(f"Search error for {database}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

# ========== NUCLEOTIDE METADATA ==========
async def fetch_nucleotide_metadata(uid: str):
    """Fetch metadata for nucleotide records"""
    try:
        cached_data = await check_cache("nucleotide", uid)
        if cached_data:
            return cached_data

        logger.info(f"Fetching nucleotide data for UID: {uid}")
        rate_limit()
        
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
            "source": record.annotations.get("source", "Unknown"),
        }

        return await save_to_cache(metadata)

    except Exception as e:
        logger.error(f"Error fetching nucleotide data for UID {uid}: {e}")
        return None
    
# ========== GENE METADATA ==========

async def fetch_gene_metadata(uid: str):
    """Fetch metadata for gene records"""
    try:
        cached_data = await check_cache("gene", uid)
        if cached_data:
            return cached_data

        logger.info(f"Fetching gene data for UID: {uid}")
        rate_limit()
        
        # Fetch gene summary
        handle = Entrez.esummary(db="gene", id=uid, retmode="xml")
        summary_data = Entrez.read(handle, validate=False)
        handle.close()
        
        if "DocumentSummarySet" not in summary_data:
            return None
            
        doc_summary = summary_data["DocumentSummarySet"].get("DocumentSummary", [])
        if not doc_summary:
            return None
            
        summary = doc_summary[0]
        summary_dict = dict(summary.items()) if hasattr(summary, 'items') else {}
        
        metadata = {
            "database": "gene",
            "accession": summary_dict.get("Id", uid),
            "gene_name": summary_dict.get("Name", "Unknown"),
            "description": summary_dict.get("Description", "Unknown"),
            "organism": {
                "sci_name": summary_dict.get("ScientificName", "Unknown"),
                "common_name": summary_dict.get("CommonName", "Unknown"),
                "tax_id": str(summary_dict.get("TaxId", "N/A"))
            },
            "chromosome": summary_dict.get("Chromosome", "N/A"),
            "map_location": summary_dict.get("MapLocation", "N/A"),
            "summary": summary_dict.get("Summary", "N/A"),
            "ncbi_link": f"https://www.ncbi.nlm.nih.gov/gene/{uid}"
        }

        return await save_to_cache(metadata)

    except Exception as e:
        logger.error(f"Error fetching gene data for UID {uid}: {e}")
        return None
# ========== TAXONOMY METADATA ==========

async def fetch_taxonomy_metadata(uid: str):
    """Fetch metadata for taxonomy records"""
    try:
        cached_data = await check_cache("taxonomy", uid)
        if cached_data:
            return cached_data

        logger.info(f"Fetching taxonomy data for UID: {uid}")
        rate_limit()
        
        # Fetch taxonomy data
        handle = Entrez.efetch(db="taxonomy", id=uid, retmode="xml")
        taxonomy_data = Entrez.read(handle, validate=False)
        handle.close()
        
        if not taxonomy_data:
            return None
            
        taxon = taxonomy_data[0]  # First taxon in response
        
        metadata = {
            "database": "taxonomy",
            "accession": str(taxon.get("TaxId", uid)),
            "organism": {
                "sci_name": taxon.get("ScientificName", "Unknown"),
                "common_name": taxon.get("CommonName", "Unknown"),
                "tax_id": str(taxon.get("TaxId", "N/A"))
            },
            "rank": taxon.get("Rank", "N/A"),
            "division": taxon.get("Division", "N/A"),
            "genetic_code": taxon.get("GeneticCode", {}).get("GCId", "N/A"),
            "lineage": taxon.get("Lineage", "N/A"),
            "ncbi_link": f"https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id={uid}"
        }

        return await save_to_cache(metadata)

    except Exception as e:
        logger.error(f"Error fetching taxonomy data for UID {uid}: {e}")
        return None


@app.get("/")
async def root():
    return {"message": "Unified NCBI Metadata API is running"}

@app.get("/test/{accession}")
async def test_accession(accession: str):
    """Test endpoint for debugging"""
    result = await fetch_assembly_metadata(accession)
    return result

@app.get("/debug/{accession}")
async def debug_accession(accession: str):
    """Debug endpoint to test accession fetching"""
    result = {
        "accession": accession,
        "sources_tried": [],
        "final_result": None
    }
    
    # Test ENA
    try:
        ena_data = await fetch_ena_metadata(accession)
        result["sources_tried"].append({
            "source": "ENA",
            "success": ena_data is not None,
            "data": ena_data
        })
    except Exception as e:
        result["sources_tried"].append({
            "source": "ENA",
            "success": False,
            "error": str(e)
        })
    
    # Test NCBI Assembly
    try:
        ncbi_data = await fetch_assembly_by_accession(accession)
        result["sources_tried"].append({
            "source": "NCBI Assembly",
            "success": ncbi_data is not None,
            "data": ncbi_data
        })
    except Exception as e:
        result["sources_tried"].append({
            "source": "NCBI Assembly",
            "success": False,
            "error": str(e)
        })
    
    # Test final result
    result["final_result"] = await fetch_assembly_metadata(accession)
    
    return result

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)