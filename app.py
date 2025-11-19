from fastapi import FastAPI, HTTPException, Query, Request
from typing import List, Optional
from Bio import Entrez
from Bio import SeqIO
from pymongo import MongoClient
from fastapi.middleware.cors import CORSMiddleware
import time
import uvicorn
import traceback
from datetime import datetime, timedelta
from dotenv import load_dotenv
import asyncio
import logging
import os
from slowapi import Limiter
from slowapi.util import get_remote_address
from pymongo.errors import ConnectionFailure
import requests
import xml.etree.ElementTree as ET
import re
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


# async def save_to_cache(metadata: dict):
#     """Save metadata to MongoDB cache with TTL"""
#     if db is None:
#         return metadata
#     try:
#         # Add expiration time (7 days for minimal data, 30 days for good data)
#         if metadata.get("database") == "minimal" or metadata.get("organism", {}).get("sci_name") == "Unknown":
#             expires_at = datetime.utcnow() + timedelta(days=1)  # 1 day for minimal data
#         else:
#             expires_at = datetime.utcnow() + timedelta(days=30)  # 30 days for good data
        
#         metadata["expires_at"] = expires_at
#         metadata["last_updated"] = datetime.utcnow()
        
#         result = db.metadata.replace_one(
#             {"database": metadata["database"], "accession": metadata["accession"]},
#             metadata,
#             upsert=True
#         )
        
#         # Create TTL index if it doesn't exist
#         try:
#             db.metadata.create_index("expires_at", expireAfterSeconds=0)
#         except:
#             pass  # Index already exists
            
#         metadata["_id"] = str(result.upserted_id) if result.upserted_id else metadata.get("_id")
#         logger.info(f"Saved metadata for {metadata['database']} {metadata['accession']} to cache")
#         return metadata
#     except Exception as e:
#         logger.error(f"Error saving to cache: {e}")
#         return metadata

async def save_to_cache(metadata: dict):
    """Save metadata to MongoDB cache with TTL"""
    if db is None:
        return metadata
    try:
        # Add expiration time
        if metadata.get("database") == "minimal" or metadata.get("organism", {}).get("sci_name") == "Unknown":
            expires_at = datetime.utcnow() + timedelta(days=1)  # 1 day for minimal data
        else:
            expires_at = datetime.utcnow() + timedelta(days=30)  # 30 days for good data
        
        metadata["expires_at"] = expires_at
        metadata["last_updated"] = datetime.utcnow()
        
        result = db.metadata.replace_one(
            {"database": metadata["database"], "accession": metadata["accession"]},
            metadata,
            upsert=True
        )
        
        logger.info(f"Saved metadata for {metadata['database']} {metadata['accession']} to cache")
        return metadata
    except Exception as e:
        logger.error(f"Error saving to cache: {e}")
        return metadata

async def check_cache(database: str, identifier: str):
    """Check MongoDB cache for existing metadata"""
    if db is None:
        return None
    try:
        cached_data = db.metadata.find_one({
            "database": database, 
            "accession": identifier,
            "expires_at": {"$gt": datetime.utcnow()}  # Only return non-expired
        })
        if cached_data:
            cached_data["_id"] = str(cached_data["_id"])
            logger.info(f"Cache hit for {database} {identifier}")
            return cached_data
        return None
    except Exception as e:
        logger.error(f"Error checking cache: {e}")
        return None

async def check_cache(database: str, identifier: str):
    """Check MongoDB cache for existing metadata"""
    if db is None:
        return None
    try:
        cached_data = db.metadata.find_one({
            "database": database, 
            "accession": identifier,
            "expires_at": {"$gt": datetime.utcnow()}  # Only return non-expired
        })
        if cached_data:
            cached_data["_id"] = str(cached_data["_id"])
            logger.info(f"Cache hit for {database} {identifier}")
            return cached_data
        return None
    except Exception as e:
        logger.error(f"Error checking cache: {e}")
        return None

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
#     """Main assembly metadata fetcher with enhanced fallback"""
#     try:
#         # Check cache first
#         cached_data = await check_cache("assembly", accession)
#         if cached_data:
#             return cached_data

#         logger.info(f"Fetching assembly metadata for: {accession}")
        
#         approaches = [
#             {"name": "ENA", "func": fetch_ena_metadata},
#             {"name": "NCBI Assembly", "func": fetch_assembly_by_accession},
#             {"name": "NCBI Datasets", "func": fetch_ncbi_datasets_direct},
#         ]
        
#         for approach in approaches:
#             try:
#                 logger.info(f"Trying {approach['name']} for {accession}")
#                 data = await approach['func'](accession)
                
#                 if data and is_valid_assembly_data(data):
#                     logger.info(f"✅ {approach['name']} success for {accession}")
                    
#                     # Enhance with additional statistics if missing
#                     if missing_stats(data):
#                         enhanced_stats = await fetch_enhanced_assembly_stats(accession)
#                         if enhanced_stats:
#                             data.update(enhanced_stats)
#                             data['additional_info'] = f"Data from {approach['name']} with enhanced statistics"
                    
#                     return await save_to_cache(data)
                    
#             except Exception as e:
#                 logger.warning(f"{approach['name']} failed for {accession}: {str(e)}")
#                 continue
        
#         # All approaches failed
#         logger.error(f"All approaches failed for {accession}")
#         return create_minimal_metadata(accession, "All data sources failed")
        
#     except Exception as e:
#         logger.error(f"Error fetching assembly metadata for {accession}: {str(e)}")
#         return create_minimal_metadata(accession, f"Error: {str(e)}")

async def fetch_assembly_metadata(accession: str, force_refresh: bool = False):
    """Main assembly metadata fetcher with force refresh option"""
    try:
        # Check cache first (unless forcing refresh)
        if not force_refresh:
            cached_data = await check_cache("assembly", accession)
            if cached_data:
                # If cached data is minimal and older than 1 hour, refresh
                if (cached_data.get("database") == "minimal" or 
                    cached_data.get("organism", {}).get("sci_name") == "Unknown"):
                    cache_age = datetime.utcnow() - cached_data.get("last_updated", datetime.utcnow())
                    if cache_age > timedelta(hours=1):
                        logger.info(f"Minimal cache data for {accession} is old, refreshing")
                    else:
                        return cached_data
                else:
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


# async def fetch_enhanced_assembly_stats(accession: str):
#     """Enhanced statistics fetcher with multiple fallback methods"""
#     try:
#         base_accession = accession.split('.')[0]
        
#         # Method 1: Try NCBI Datasets API first
#         logger.info(f"Trying NCBI Datasets API for {accession}")
#         datasets_stats = await fetch_ncbi_datasets_stats(accession)
#         if datasets_stats and any(v != "N/A" for v in datasets_stats.values()):
#             logger.info(f"✅ NCBI Datasets success for {accession}")
#             return datasets_stats
        
#         # Method 2: Try Assembly Report from FTP
#         logger.info(f"Trying Assembly Report for {accession}")
#         assembly_report_stats = await fetch_assembly_report_stats(accession)
#         if assembly_report_stats:
#             return assembly_report_stats
        
#         # Method 3: Try multiple FTP path patterns for stats file
#         ftp_stats = await try_multiple_ftp_patterns(base_accession)
#         if ftp_stats:
#             return ftp_stats
            
#         # Method 4: Try ENA API
#         logger.info(f"Trying ENA API for {accession}")
#         ena_stats = await fetch_ena_statistics(accession)
#         if ena_stats:
#             return ena_stats
            
#         # Method 5: Try to parse from the assembly directory
#         directory_stats = await parse_assembly_directory(accession)
#         if directory_stats:
#             return directory_stats
            
#         return None
        
#     except Exception as e:
#         logger.warning(f"All enhanced stats methods failed for {accession}: {str(e)}")
#         return None



async def try_multiple_ftp_patterns(base_accession: str):
    """Try multiple FTP path patterns for assembly statistics"""
    try:
        ftp_patterns = []
        
        if base_accession.startswith('GCF_'):
            # RefSeq patterns
            path_part = base_accession.replace('GCF_', '')
            patterns = [
                f"https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/{path_part[:3]}/{path_part[3:6]}/{path_part[6:9]}/{base_accession}*/{base_accession}*_assembly_stats.txt",
                f"https://ftp.ncbi.nlm.nih.gov/genomes/refseq/assembly/{base_accession}/*_assembly_stats.txt"
            ]
        else:
            # GenBank patterns  
            path_part = base_accession.replace('GCA_', '')
            patterns = [
                f"https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/{path_part[:3]}/{path_part[3:6]}/{path_part[6:9]}/{base_accession}*/{base_accession}*_assembly_stats.txt",
                f"https://ftp.ncbi.nlm.nih.gov/genomes/genbank/assembly/{base_accession}/*_assembly_stats.txt"
            ]
        
        for pattern in patterns:
            try:
                # Clean the pattern to get base directory
                base_dir = pattern.replace('*', '').rsplit('/', 1)[0]
                logger.info(f"Trying FTP directory: {base_dir}")
                response = requests.get(base_dir, timeout=10)
                if response.status_code == 200:
                    # Look for stats file in directory listing
                    stats_file = await find_file_in_listing(response.text, "*assembly_stats.txt")
                    if stats_file:
                        stats_response = requests.get(stats_file, timeout=10)
                        if stats_response.status_code == 200:
                            stats = parse_assembly_stats_file(stats_response.text)
                            if stats:
                                logger.info(f"Found stats via FTP: {stats}")
                                return stats
            except Exception as e:
                logger.debug(f"FTP pattern failed: {pattern}, error: {str(e)}")
                continue
                
        return None
    except Exception as e:
        logger.debug(f"try_multiple_ftp_patterns failed: {str(e)}")
        return None

# async def fetch_enhanced_assembly_stats(accession: str):
#     """Enhanced statistics fetcher with multiple fallback methods"""
#     try:
#         base_accession = accession.split('.')[0]
        
#         # Method 1: Try NCBI Datasets API first
#         logger.info(f"Trying NCBI Datasets API for {accession}")
#         datasets_stats = await fetch_ncbi_datasets_stats(accession)
#         if datasets_stats and any(v != "N/A" for v in datasets_stats.values()):
#             logger.info(f"✅ NCBI Datasets success for {accession}")
#             return datasets_stats
        
#         # Method 2: Try Assembly Report from FTP
#         logger.info(f"Trying Assembly Report for {accession}")
#         assembly_report_stats = await fetch_assembly_report_stats(accession)
#         if assembly_report_stats:
#             return assembly_report_stats
        
#         # Method 3: Try multiple FTP path patterns for stats file
#         ftp_stats = await try_multiple_ftp_patterns(base_accession)
#         if ftp_stats:
#             return ftp_stats
            
#         # Method 4: Try ENA API
#         logger.info(f"Trying ENA API for {accession}")
#         ena_stats = await fetch_ena_statistics(accession)
#         if ena_stats:
#             return ena_stats
            
#         # Method 5: Try to parse from the assembly directory
#         directory_stats = await parse_assembly_directory(accession)
#         if directory_stats:
#             return directory_stats
            
#         return None
        
#     except Exception as e:
#         logger.warning(f"All enhanced stats methods failed for {accession}: {str(e)}")
#         return None

# async def fetch_enhanced_assembly_stats(accession: str):
#     """Enhanced statistics fetcher with multiple fallback methods"""
#     try:
#         base_accession = accession.split('.')[0]
        
#         # Method 1: Try NCBI Datasets API first
#         logger.info(f"Trying NCBI Datasets API for {accession}")
#         datasets_stats = await fetch_ncbi_datasets_stats(accession)
#         if datasets_stats and any(v != "N/A" for v in datasets_stats.values()):
#             logger.info(f"✅ NCBI Datasets success for {accession}")
#             return datasets_stats
        
#         # Method 2: Try Assembly Report from FTP
#         logger.info(f"Trying Assembly Report for {accession}")
#         assembly_report_stats = await fetch_assembly_report_stats(accession)
#         if assembly_report_stats:
#             return assembly_report_stats
        
#         # Method 3: Try multiple FTP path patterns for stats file
#         ftp_stats = await try_multiple_ftp_patterns(base_accession)
#         if ftp_stats:
#             return ftp_stats
            
#         # Method 4: Try ENA API
#         logger.info(f"Trying ENA API for {accession}")
#         ena_stats = await fetch_ena_statistics(accession)
#         if ena_stats:
#             return ena_stats
            
#         # Method 5: Try to parse from the assembly directory
#         directory_stats = await parse_assembly_directory(accession)
#         if directory_stats:
#             return directory_stats
            
#         return None
        
#     except Exception as e:
#         logger.warning(f"All enhanced stats methods failed for {accession}: {str(e)}")
#         return None

async def fetch_enhanced_assembly_stats(accession: str):
    """
    Tries multiple methods to fetch assembly statistics in a robust, maintainable way.
    
    This function combines the desired methods from the second snippet with the
    superior loop-based architecture of the first snippet.
    """
    try:
        # This line is from your second snippet and is needed for one of the methods.
        base_accession = accession.split('.')[0]
        
        # This is the list of approaches from your first snippet.
        # We will fill it with all the methods you want to try.
        approaches = [
            # Method 1: From your second snippet
            {"name": "NCBI Datasets API", "func": fetch_ncbi_datasets_stats},
            
            # Method 2: From your second snippet
            {"name": "Assembly Report", "func": fetch_assembly_report_stats},
            
            # Method 3: From your second snippet, using the base_accession
            {"name": "FTP Stats Files", "func": lambda acc: try_multiple_ftp_patterns(base_accession)},
            
            # Method 4: From your second snippet
            {"name": "ENA Statistics", "func": fetch_ena_statistics},
            
            # Method 5: From your second snippet
            {"name": "Directory Analysis", "func": parse_assembly_directory},
            
            # This was an extra method in your first snippet, which we can keep as a bonus.
            {"name": "Sequence Analysis", "func": analyze_sequence_files},
        ]
        
        # This loop is the superior architecture from your first snippet.
        # It replaces the long chain of 'if' statements from the second snippet.
        for approach in approaches:
            try:
                logger.info(f"Trying {approach['name']} for {accession}")
                
                # Call the function for the current approach
                stats = await approach['func'](accession)
                
                # This is a robust success check that works for all methods.
                # It's an improvement over the different checks in your second snippet.
                if stats and any(v not in ["N/A", None, ""] for v in stats.values()):
                    logger.info(f"✅ {approach['name']} success for {accession}")
                    return stats
                    
            except Exception as e:
                # If an approach fails, log it and CONTINUE to the next one.
                # This makes the function very resilient.
                logger.debug(f"{approach['name']} failed: {str(e)}")
                continue
        
        # If the loop finishes without returning, all methods failed.
        logger.warning(f"All statistics methods failed for {accession}")
        return None
        
    except Exception as e:
        # This is a final safety net for any unexpected errors.
        logger.warning(f"Enhanced stats fetch failed for {accession}: {str(e)}")
        return None

async def fetch_assembly_report_stats(accession: str):
    """Try to get statistics from assembly report file"""
    try:
        base_accession = accession.split('.')[0]
        
        # Construct assembly report URL
        if base_accession.startswith('GCF_'):
            path_part = base_accession.replace('GCF_', '')
            url = f"https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/{path_part[:3]}/{path_part[3:6]}/{path_part[6:9]}/{base_accession}*/{base_accession}*_assembly_report.txt"
        else:
            path_part = base_accession.replace('GCA_', '')
            url = f"https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/{path_part[:3]}/{path_part[3:6]}/{path_part[6:9]}/{base_accession}*/{base_accession}*_assembly_report.txt"
        
        # Try to find and download the report
        response = requests.get(url.replace('*', '').rsplit('/', 1)[0], timeout=10)
        if response.status_code == 200:
            # Look for assembly report in directory listing
            report_url = await find_file_in_listing(response.text, "*assembly_report.txt")
            if report_url:
                report_response = requests.get(report_url, timeout=10)
                if report_response.status_code == 200:
                    return parse_assembly_report(report_response.text)
        
        return None
    except Exception as e:
        logger.debug(f"Assembly report fetch failed: {str(e)}")
        return None

def parse_assembly_report(report_text: str):
    """Parse assembly report file for statistics"""
    stats = {}
    try:
        lines = report_text.split('\n')
        total_length = 0
        contig_count = 0
        
        for line in lines:
            line = line.strip()
            if line.startswith('#') and 'Sequence-Length' in line:
                # Extract sequence length
                parts = line.split()
                if len(parts) > 1:
                    try:
                        length = int(parts[-1].replace(',', ''))
                        total_length += length
                        contig_count += 1
                    except ValueError:
                        pass
            elif 'Total sequence length' in line.lower():
                parts = line.split(':')
                if len(parts) > 1:
                    stats['genome_size'] = parts[1].strip().split()[0]
        
        if total_length > 0 and not stats.get('genome_size'):
            stats['genome_size'] = str(total_length)
        if contig_count > 0 and not stats.get('number_of_contigs'):
            stats['number_of_contigs'] = str(contig_count)
            
        return stats if stats else None
        
    except Exception as e:
        logger.debug(f"Error parsing assembly report: {str(e)}")
        return None

async def parse_assembly_directory(accession: str):
    """Try to parse statistics from assembly directory files"""
    try:
        base_accession = accession.split('.')[0]
        
        # Try to get the directory listing
        if base_accession.startswith('GCF_'):
            path_part = base_accession.replace('GCF_', '')
            base_url = f"https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/{path_part[:3]}/{path_part[3:6]}/{path_part[6:9]}/{base_accession}*/"
        else:
            path_part = base_accession.replace('GCA_', '')
            base_url = f"https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/{path_part[:3]}/{path_part[3:6]}/{path_part[6:9]}/{base_accession}*/"
        
        response = requests.get(base_url, timeout=10)
        if response.status_code == 200:
            # Parse directory listing to find files that might contain stats
            files = await parse_directory_listing(response.text)
            
            # Try to find and parse any file that might contain statistics
            for file_pattern in ['*stats*', '*report*', '*.txt', '*.out']:
                matching_files = [f for f in files if file_pattern.replace('*', '') in f.lower()]
                for file_url in matching_files:
                    try:
                        file_response = requests.get(file_url, timeout=10)
                        if file_response.status_code == 200:
                            # Try different parsing methods
                            stats = parse_assembly_stats_file(file_response.text)
                            if not stats:
                                stats = parse_generic_stats_file(file_response.text)
                            
                            if stats:
                                return stats
                    except:
                        continue
        
        return None
    except Exception as e:
        logger.debug(f"Directory parsing failed: {str(e)}")
        return None

def parse_generic_stats_file(file_text: str):
    """Try to parse statistics from any file using pattern matching"""
    stats = {}
    try:
        lines = file_text.split('\n')
        
        for line in lines:
            line = line.lower().strip()
            
            # Look for genome size/total length
            if any(term in line for term in ['total length', 'genome size', 'total_size', 'size:']):
                numbers = re.findall(r'\d+[,\.]?\d*', line)
                if numbers and not stats.get('genome_size'):
                    stats['genome_size'] = numbers[0].replace(',', '')
            
            # Look for N50
            if any(term in line for term in ['n50', 'contig n50']):
                numbers = re.findall(r'\d+[,\.]?\d*', line)
                if numbers and not stats.get('contig_n50'):
                    stats['contig_n50'] = numbers[0].replace(',', '')
            
            # Look for contig count
            if any(term in line for term in ['number of contigs', 'contig count', 'contigs:']):
                numbers = re.findall(r'\d+', line)
                if numbers and not stats.get('number_of_contigs'):
                    stats['number_of_contigs'] = numbers[0]
            
            # Look for GC content
            if any(term in line for term in ['gc content', 'gc percent', 'gc%', 'gc:']):
                numbers = re.findall(r'\d+[,\.]?\d*', line)
                if numbers and not stats.get('gc_percent'):
                    stats['gc_percent'] = numbers[0]
        
        return stats if stats else None
        
    except Exception as e:
        logger.debug(f"Generic stats parsing failed: {str(e)}")
        return None

async def fetch_assembly_report_stats(accession: str):
    """Try to get statistics from assembly report file"""
    try:
        base_accession = accession.split('.')[0]
        
        # Construct assembly report URL
        if base_accession.startswith('GCF_'):
            path_part = base_accession.replace('GCF_', '')
            url = f"https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/{path_part[:3]}/{path_part[3:6]}/{path_part[6:9]}/{base_accession}*/{base_accession}*_assembly_report.txt"
        else:
            path_part = base_accession.replace('GCA_', '')
            url = f"https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/{path_part[:3]}/{path_part[3:6]}/{path_part[6:9]}/{base_accession}*/{base_accession}*_assembly_report.txt"
        
        # Try to find and download the report
        response = requests.get(url.replace('*', '').rsplit('/', 1)[0], timeout=10)
        if response.status_code == 200:
            # Look for assembly report in directory listing
            report_url = await find_file_in_listing(response.text, "*assembly_report.txt")
            if report_url:
                report_response = requests.get(report_url, timeout=10)
                if report_response.status_code == 200:
                    return parse_assembly_report(report_response.text)
        
        return None
    except Exception as e:
        logger.debug(f"Assembly report fetch failed: {str(e)}")
        return None

def parse_assembly_report(report_text: str):
    """Parse assembly report file for statistics"""
    stats = {}
    try:
        lines = report_text.split('\n')
        total_length = 0
        contig_count = 0
        
        for line in lines:
            line = line.strip()
            if line.startswith('#') and 'Sequence-Length' in line:
                # Extract sequence length
                parts = line.split()
                if len(parts) > 1:
                    try:
                        length = int(parts[-1].replace(',', ''))
                        total_length += length
                        contig_count += 1
                    except ValueError:
                        pass
            elif 'Total sequence length' in line.lower():
                parts = line.split(':')
                if len(parts) > 1:
                    stats['genome_size'] = parts[1].strip().split()[0]
        
        if total_length > 0 and not stats.get('genome_size'):
            stats['genome_size'] = str(total_length)
        if contig_count > 0 and not stats.get('number_of_contigs'):
            stats['number_of_contigs'] = str(contig_count)
            
        return stats if stats else None
        
    except Exception as e:
        logger.debug(f"Error parsing assembly report: {str(e)}")
        return None

async def parse_assembly_directory(accession: str):
    """Try to parse statistics from assembly directory files"""
    try:
        base_accession = accession.split('.')[0]
        
        # Try to get the directory listing
        if base_accession.startswith('GCF_'):
            path_part = base_accession.replace('GCF_', '')
            base_url = f"https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/{path_part[:3]}/{path_part[3:6]}/{path_part[6:9]}/{base_accession}*/"
        else:
            path_part = base_accession.replace('GCA_', '')
            base_url = f"https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/{path_part[:3]}/{path_part[3:6]}/{path_part[6:9]}/{base_accession}*/"
        
        response = requests.get(base_url, timeout=10)
        if response.status_code == 200:
            # Parse directory listing to find files that might contain stats
            files = await parse_directory_listing(response.text)
            
            # Try to find and parse any file that might contain statistics
            for file_pattern in ['*stats*', '*report*', '*.txt', '*.out']:
                matching_files = [f for f in files if file_pattern.replace('*', '') in f.lower()]
                for file_url in matching_files:
                    try:
                        file_response = requests.get(file_url, timeout=10)
                        if file_response.status_code == 200:
                            # Try different parsing methods
                            stats = parse_assembly_stats_file(file_response.text)
                            if not stats:
                                stats = parse_generic_stats_file(file_response.text)
                            
                            if stats:
                                return stats
                    except:
                        continue
        
        return None
    except Exception as e:
        logger.debug(f"Directory parsing failed: {str(e)}")
        return None

def parse_generic_stats_file(file_text: str):
    """Try to parse statistics from any file using pattern matching"""
    stats = {}
    try:
        lines = file_text.split('\n')
        
        for line in lines:
            line = line.lower().strip()
            
            # Look for genome size/total length
            if any(term in line for term in ['total length', 'genome size', 'total_size', 'size:']):
                numbers = re.findall(r'\d+[,\.]?\d*', line)
                if numbers and not stats.get('genome_size'):
                    stats['genome_size'] = numbers[0].replace(',', '')
            
            # Look for N50
            if any(term in line for term in ['n50', 'contig n50']):
                numbers = re.findall(r'\d+[,\.]?\d*', line)
                if numbers and not stats.get('contig_n50'):
                    stats['contig_n50'] = numbers[0].replace(',', '')
            
            # Look for contig count
            if any(term in line for term in ['number of contigs', 'contig count', 'contigs:']):
                numbers = re.findall(r'\d+', line)
                if numbers and not stats.get('number_of_contigs'):
                    stats['number_of_contigs'] = numbers[0]
            
            # Look for GC content
            if any(term in line for term in ['gc content', 'gc percent', 'gc%', 'gc:']):
                numbers = re.findall(r'\d+[,\.]?\d*', line)
                if numbers and not stats.get('gc_percent'):
                    stats['gc_percent'] = numbers[0]
        
        return stats if stats else None
        
    except Exception as e:
        logger.debug(f"Generic stats parsing failed: {str(e)}")
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
#     """Parse ENA API response with flexible field mapping"""
#     try:
#         # Flexible field mapping - ENA uses different field names
#         sci_name = (
#             ena_data.get("scientific_name") or 
#             ena_data.get("organism_name") or 
#             ena_data.get("species") or 
#             ena_data.get("organism") or
#             "Unknown"
#         )
        
#         common_name = ena_data.get("common_name") or ena_data.get("strain") or "Unknown"
#         tax_id = str(ena_data.get("tax_id") or ena_data.get("taxid") or "N/A")
        
#         assembly_name = (
#             ena_data.get("assembly_name") or 
#             ena_data.get("name") or 
#             f"Assembly {accession.split('.')[0]}"
#         )
        
#         assembly_level = ena_data.get("assembly_level") or ena_data.get("level") or "N/A"
        
#         # Try different field names for statistics
#         genome_size = (
#             ena_data.get("total_length") or 
#             ena_data.get("genome_length") or 
#             ena_data.get("size") or
#             "N/A"
#         )
        
#         contig_n50 = ena_data.get("contig_n50") or ena_data.get("n50") or "N/A"
#         number_of_contigs = ena_data.get("number_of_contigs") or ena_data.get("contig_count") or "N/A"
#         gc_percent = ena_data.get("gc_percent") or ena_data.get("gc_content") or "N/A"
        
#         # Construct FTP path
#         ftp_path = ena_data.get("ftp_path")
#         if not ftp_path:
#             ftp_path = f"https://www.ebi.ac.uk/ena/browser/view/{accession}"
        
#         result = {
#             "database": "ena",
#             "accession": accession,
#             "organism": {
#                 "sci_name": sci_name,
#                 "common_name": common_name,
#                 "tax_id": tax_id
#             },
#             "assembly_name": assembly_name,
#             "assembly_level": assembly_level,
#             "submission_date": ena_data.get("first_public") or ena_data.get("submission_date") or "N/A",
#             "genome_size": genome_size,
#             "contig_n50": contig_n50,
#             "number_of_contigs": number_of_contigs,
#             "gc_percent": gc_percent,
#             "ftp_path": ftp_path,
#             "additional_info": "Data from European Nucleotide Archive",
#             "last_updated": datetime.utcnow().isoformat()
#         }
        
#         logger.info(f"Parsed ENA data for {accession}: {result['organism']['sci_name']}")
#         return result
        
#     except Exception as e:
#         logger.error(f"Error parsing ENA response for {accession}: {str(e)}")
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
        
        # Extract genome size from base_count (this is available in your ENA response!)
        genome_size = ena_data.get("base_count")
        if genome_size and genome_size != "0":
            genome_size = str(genome_size)  # Convert to string
        else:
            genome_size = "N/A"
        
        # Try other field names for statistics
        contig_n50 = ena_data.get("contig_n50") or ena_data.get("n50") or "N/A"
        number_of_contigs = ena_data.get("number_of_contigs") or ena_data.get("contig_count") or "N/A"
        gc_percent = ena_data.get("gc_percent") or ena_data.get("gc_content") or "N/A"
        
        # Use first_public or last_updated for submission date
        submission_date = ena_data.get("first_public") or ena_data.get("last_updated") or "N/A"
        
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
            "submission_date": submission_date,
            "genome_size": genome_size,  # This should now be 21550525
            "contig_n50": contig_n50,
            "number_of_contigs": number_of_contigs,
            "gc_percent": gc_percent,
            "ftp_path": ftp_path,
            "additional_info": "Data from European Nucleotide Archive",
            "last_updated": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Parsed ENA data for {accession}: genome_size={genome_size}")
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
#         # Normalize database parameter
#         database = database.lower().strip()
        
#         # Validate database
#         supported_databases = ["assembly", "nucleotide", "gene", "taxonomy", "protein"]
#         if database not in supported_databases:
#             raise HTTPException(
#                 status_code=400, 
#                 detail=f"Database '{database}' is not supported. Supported: {', '.join(supported_databases)}"
#             )
        
#         logger.info(f"🔍 Search request - Database: {database}, Organism: {organism}, Accessions: {accession_ids}")
        
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
    # Remove refresh parameter for now
    # refresh: bool = Query(False, description="Force refresh cache")
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
        
        logger.info(f"🔍 Search request - Database: {database}")
        
        if database == "assembly":
            logger.info("✅ Routing to search_assemblies")
            # Remove refresh parameter
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

async def search_assemblies(organism: Optional[str], taxid: Optional[int], accession_ids: Optional[str], retmax: int):
    """Search for assemblies with refresh option"""
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
    
    if has_accessions_only:
        logger.info("Direct accession search detected, using optimized approach")
        return await direct_accession_search(accession_list, search_query, retmax,)
    else:
        logger.info("Using standard NCBI search")
        return await standard_ncbi_assembly_search(search_query, retmax)


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
            
#             # FIXED: Better condition to check if we have valid data
#             if (assembly_data and 
#                 assembly_data.get("database") != "minimal" and 
#                 assembly_data.get("accession") and
#                 (assembly_data.get("organism", {}).get("sci_name") not in ["Unknown", None, ""] or
#                  assembly_data.get("assembly_name") not in ["Unknown", None, ""])):
                
#                 metadata.append(assembly_data)
#                 logger.info(f"✅ Successfully fetched {accession}")
#             else:
#                 failed_accessions.append(accession)
#                 logger.warning(f"❌ Failed to fetch valid data for {accession}")
                
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
    """Directly fetch assemblies by accession with refresh option"""
    metadata = []
    failed_accessions = []
    
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
            
            if assembly_data and is_valid_assembly_data(assembly_data):
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


async def find_files_in_listing(html_content: str, pattern: str):
    """Find files matching pattern in directory listing HTML"""
    try:
        # Simple HTML parsing to find links
        files = []
        pattern_re = pattern.replace('*', '.*')
        
        for line in html_content.split('\n'):
            if 'href="' in line:
                match = re.search(r'href="([^"]*)"', line)
                if match:
                    filename = match.group(1)
                    if re.match(pattern_re, filename, re.IGNORECASE):
                        # Construct full URL
                        base_url = html_content.split('<base href="')[-1].split('"')[0] if '<base href="' in html_content else ""
                        files.append(base_url + filename)
        
        return files
    except Exception as e:
        logger.debug(f"File finding failed: {str(e)}")
        return []

async def find_file_in_listing(html_content: str, pattern: str):
    """Find a single file matching pattern"""
    files = await find_files_in_listing(html_content, pattern)
    return files[0] if files else None

async def find_file_in_listing(html_content: str, pattern: str):
    """Find files matching pattern in directory listing HTML"""
    try:
        # Simple HTML parsing to find links
        files = []
        pattern_re = pattern.replace('*', '.*')
        
        for line in html_content.split('\n'):
            if 'href="' in line:
                match = re.search(r'href="([^"]*)"', line)
                if match:
                    filename = match.group(1)
                    if re.match(pattern_re, filename, re.IGNORECASE) and not filename.endswith('/'):
                        # Construct full URL - extract base from HTML if available
                        base_match = re.search(r'<base href="([^"]*)"', html_content)
                        base_url = base_match.group(1) if base_match else ""
                        # Remove trailing slash from base_url if present
                        base_url = base_url.rstrip('/')
                        file_url = f"{base_url}/{filename}" if base_url else filename
                        files.append(file_url)
        
        return files[0] if files else None
    except Exception as e:
        logger.debug(f"File finding failed: {str(e)}")
        return None

async def analyze_sequence_files(accession: str):
    """Last resort: try to analyze sequence files directly"""
    try:
        base_accession = accession.split('.')[0]
        
        # Find FASTA files in the assembly directory
        if base_accession.startswith('GCF_'):
            path_part = base_accession.replace('GCF_', '')
            base_url = f"https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/{path_part[:3]}/{path_part[3:6]}/{path_part[6:9]}/{base_accession}*/"
        else:
            path_part = base_accession.replace('GCA_', '')
            base_url = f"https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/{path_part[:3]}/{path_part[3:6]}/{path_part[6:9]}/{base_accession}*/"
        
        response = requests.get(base_url, timeout=10)
        if response.status_code == 200:
            fasta_files = await find_files_in_listing(response.text, "*.fna")  # or *.fa, *.fasta
            
            total_length = 0
            sequences = []
            
            # Download and analyze a sample of sequences (first few)
            for fasta_url in fasta_files[:3]:  # Limit to first 3 files
                try:
                    fasta_response = requests.get(fasta_url, timeout=30, stream=True)
                    if fasta_response.status_code == 200:
                        # Parse first part of FASTA to get sequence lengths
                        content = ""
                        for line in fasta_response.iter_lines(decode_unicode=True):
                            if line and not line.startswith('>'):
                                content += line
                            if len(content) > 100000:  # Sample first 100kb
                                break
                        
                        if content:
                            sequences.append({
                                'length': len(content),
                                'gc_content': (content.count('G') + content.count('C') + content.count('g') + content.count('c')) / len(content) * 100
                            })
                            
                except Exception as e:
                    logger.debug(f"Failed to analyze {fasta_url}: {str(e)}")
                    continue
            
            if sequences:
                stats = {}
                total_length = sum(seq['length'] for seq in sequences)
                if total_length > 0:
                    stats['genome_size'] = str(total_length)
                    stats['gc_percent'] = str(round(sum(seq['gc_content'] for seq in sequences) / len(sequences), 2))
                    stats['number_of_contigs'] = str(len(sequences))
                    
                    # Estimate N50 (very rough)
                    lengths = sorted([seq['length'] for seq in sequences], reverse=True)
                    half_total = total_length / 2
                    running_sum = 0
                    for length in lengths:
                        running_sum += length
                        if running_sum >= half_total:
                            stats['contig_n50'] = str(length)
                            break
                
                return stats if stats else None
        
        return None
    except Exception as e:
        logger.debug(f"Sequence analysis failed: {str(e)}")
        return None
async def find_files_in_listing(html_content: str, pattern: str):
    """Find files matching pattern in directory listing HTML"""
    try:
        # Simple HTML parsing to find links
        files = []
        pattern_re = pattern.replace('*', '.*')
        
        for line in html_content.split('\n'):
            if 'href="' in line:
                match = re.search(r'href="([^"]*)"', line)
                if match:
                    filename = match.group(1)
                    if re.match(pattern_re, filename, re.IGNORECASE):
                        # Construct full URL
                        base_url = html_content.split('<base href="')[-1].split('"')[0] if '<base href="' in html_content else ""
                        files.append(base_url + filename)
        
        return files
    except Exception as e:
        logger.debug(f"File finding failed: {str(e)}")
        return []

async def find_file_in_listing(html_content: str, pattern: str):
    """Find a single file matching pattern"""
    files = await find_files_in_listing(html_content, pattern)
    return files[0] if files else None

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
# Add this to debug specific accessions
@app.get("/test-stats/{accession}")
async def test_stats(accession: str):
    """Test all statistics methods for an accession"""
    results = {}
    
    methods = [
        ("NCBI Datasets", fetch_ncbi_datasets_stats),
        ("Assembly Report", fetch_assembly_report_stats),
        ("FTP Stats", lambda acc: try_multiple_ftp_patterns(acc.split('.')[0])),
        ("ENA", fetch_ena_statistics),
        ("Directory", parse_assembly_directory),
        ("Sequence Analysis", analyze_sequence_files),
    ]
    
    for name, method in methods:
        try:
            result = await method(accession)
            results[name] = result
        except Exception as e:
            results[name] = f"Error: {str(e)}"
    
    return {
        "accession": accession,
        "results": results,
        "combined": await fetch_enhanced_assembly_stats(accession)
    }

@app.delete("/cache/{accession}")
async def clear_cache(accession: str):
    """Clear cache for a specific accession"""
    if db is None:
        return {"message": "MongoDB not connected"}
    
    result = db.metadata.delete_one({"accession": accession})
    if result.deleted_count:
        logger.info(f"Cleared cache for {accession}")
        return {"message": f"Cache cleared for {accession}"}
    else:
        return {"message": f"No cache entry found for {accession}"}

@app.delete("/cache/all")
async def clear_all_cache():
    """Clear all cache"""
    if db is None:
        return {"message": "MongoDB not connected"}
    
    result = db.metadata.delete_many({})
    logger.info(f"Cleared all cache entries: {result.deleted_count}")
    return {"message": f"Cleared {result.deleted_count} cache entries"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)