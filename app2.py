# app.py - Production-Ready NCBI Metadata API (FIXED VERSION)
from fastapi import FastAPI, HTTPException, Query, Request
from typing import Optional, List, Dict, Any
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
import requests
import xml.etree.ElementTree as ET
import re

# ==================== CONFIGURATION ====================
load_dotenv()

# NCBI Configuration
Entrez.email = os.getenv("NCBI_EMAIL", "abdullah.1970333@studenti.uniroma1.it")
Entrez.api_key = os.getenv("NCBI_API_KEY")

# MongoDB Configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://admin2:Cloud786@clusterfull.tn88z.mongodb.net/taxonomy")

# Initialize MongoDB
try:
    client = MongoClient(MONGO_URI, maxPoolSize=50, connectTimeoutMS=30000)
    client.admin.command('ping')
    db = client.taxonomy
    print("✅ Connected to MongoDB successfully!")
except Exception as e:
    print(f"❌ MongoDB connection failed: {e}")
    db = None

# FastAPI App Setup
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="NCBI Metadata API")
app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== RATE LIMITER ====================
class AsyncRateLimiter:
    """Thread-safe async rate limiter for NCBI API"""
    def __init__(self, min_interval: float = 0.34):
        self.min_interval = min_interval
        self.last_request_time = 0
        self.lock = asyncio.Lock()
    
    async def __call__(self):
        async with self.lock:
            current_time = time.time()
            elapsed = current_time - self.last_request_time
            if elapsed < self.min_interval:
                sleep_time = self.min_interval - elapsed
                logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)
            self.last_request_time = time.time()

rate_limiter = AsyncRateLimiter()

# ==================== CACHE FUNCTIONS ====================
async def check_cache(database: str, identifier: str) -> Optional[Dict[str, Any]]:
    """Check MongoDB cache for existing metadata"""
    if db is None:
        return None
    try:
        cached_data = db.metadata.find_one({"database": database, "accession": identifier})
        if cached_data:
            cached_data["_id"] = str(cached_data["_id"])
            logger.info(f"💾 Cache hit for {database}:{identifier}")
            return cached_data
        return None
    except Exception as e:
        logger.error(f"Cache check error: {e}")
        return None

async def save_to_cache(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Save metadata to MongoDB cache"""
    if db is None:
        return metadata
    try:
        # Remove _id if exists to avoid duplicate key error
        if "_id" in metadata:
            del metadata["_id"]
        result = db.metadata.insert_one(metadata)
        metadata["_id"] = str(result.inserted_id)
        logger.info(f"💾 Saved to cache: {metadata['database']}:{metadata['accession']}")
        return metadata
    except Exception as e:
        logger.error(f"Cache save error: {e}")
        return metadata

# ==================== NCBI DATASETS API (PRIMARY SOURCE) ====================
async def fetch_from_datasets_api(accession: str) -> Optional[Dict[str, Any]]:
    """
    PRIMARY SOURCE: NCBI Datasets API provides complete assembly metadata
    This is the most reliable way to get all statistics
    """
    try:
        base_accession = accession.split('.')[0]
        url = f"https://api.ncbi.nlm.nih.gov/datasets/v2alpha/genome/accession/{accession}"
        headers = {"Accept": "application/json"}
        
        logger.info(f"🌐 Fetching from Datasets API: {url}")
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            logger.warning(f"Datasets API returned {response.status_code}")
            return None
        
        data = response.json()
        
        # Navigate the response structure
        if "reports" not in data or not data["reports"]:
            logger.warning(f"No reports in Datasets API response for {accession}")
            return None
        
        report = data["reports"][0]
        
        # Extract organism info
        organism_info = report.get("organism", {})
        taxonomy_info = organism_info.get("taxonomy", {})
        organism_name = organism_info.get("organism_name", "Unknown")
        common_name = taxonomy_info.get("common_name", "Unknown")
        tax_id = str(taxonomy_info.get("tax_id", "N/A"))
        
        # Extract assembly info
        assembly_info = report.get("assembly_info", {})
        assembly_name = assembly_info.get("assembly_name", "Unknown")
        assembly_level = assembly_info.get("assembly_level", "Unknown")
        submission_date = assembly_info.get("submission_date", "Unknown")
        release_date = assembly_info.get("release_date", "Unknown")
        
        # Extract statistics - THIS IS WHERE THE NULL VALUES COME FROM
        stats = report.get("assembly_stats", {})
        total_length = stats.get("total_sequence_length")
        contig_count = stats.get("number_of_contigs")
        contig_n50 = stats.get("contig_n50")
        contig_l50 = stats.get("contig_l50")
        scaffold_count = stats.get("number_of_scaffolds")
        scaffold_n50 = stats.get("scaffold_n50")
        scaffold_l50 = stats.get("scaffold_l50")
        gc_percent = stats.get("gc_percent")
        genome_coverage = stats.get("genome_coverage")
        
        # Extract biosample info
        biosample_info = report.get("biosample", {})
        biosample_accession = biosample_info.get("accession", "N/A")
        biosample_description = biosample_info.get("description", {}).get("description_text", "N/A")
        biosample_submitter = biosample_info.get("submitter", {}).get("submitter_name", "N/A")
        biosample_attributes = {}
        for attr in biosample_info.get("attributes", []):
            if "name" in attr and "value" in attr:
                biosample_attributes[attr["name"]] = attr["value"]
        
        # Extract assembly metadata (quality metrics)
        checkm_info = report.get("checkm_info", {})
        assembly_software = assembly_info.get("assembly_software", "N/A")
        completeness = checkm_info.get("completeness") if checkm_info else None
        contamination = checkm_info.get("contamination") if checkm_info else None
        
        # Determine quality category
        quality = None
        if assembly_info.get("seq_quals"):
            quality = assembly_info["seq_quals"][0] if assembly_info["seq_quals"] else None
        
        # Build FTP links
        ftp_path_refseq = assembly_info.get("ftp_path", "")
        ftp_path_genbank = report.get("genbank_ftppath", "") or report.get("genbank_ftp_path", "")
        
        # Build external links
        external_links = {
            "ncbi": f"https://www.ncbi.nlm.nih.gov/datasets/genome/{accession}/",
            "assembly": f"https://www.ncbi.nlm.nih.gov/assembly/{accession}/"
        }
        if ftp_path_refseq:
            external_links["refseq_ftp"] = ftp_path_refseq
        if ftp_path_genbank:
            external_links["genbank_ftp"] = ftp_path_genbank
            # Also add ENA link
            gca_accession = accession.replace("GCF_", "GCA_") if accession.startswith("GCF_") else None
            if gca_accession:
                path_part = gca_accession.split('.')[0].replace("GCA_", "")
                external_links["ena"] = f"ftp://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/{path_part[:3]}/{path_part[3:6]}/{path_part[6:9]}/{gca_accession.split('.')[0]}_{gca_accession.split('.')[0]}"
        
        # Format human-readable genome size
        genome_size_human = None
        if total_length:
            genome_size_human = format_bp(total_length)
        
        result = {
            "database": "assembly",
            "accession": accession,
            "organism": {
                "scientific_name": organism_name,
                "common_name": common_name if common_name != "Unknown" else None,
                "tax_id": tax_id
            },
            "assembly": {
                "name": assembly_name,
                "level": assembly_level,
                "submission_date": format_date(submission_date),
                "last_update": format_date(release_date) if release_date != "Unknown" else submission_date
            },
            "statistics": {
                "genome_size_bp": total_length,
                "genome_size_human": genome_size_human,
                "contigs": {
                    "count": contig_count,
                    "n50": contig_n50,
                    "l50": contig_l50
                },
                "scaffolds": {
                    "count": scaffold_count,
                    "n50": scaffold_n50,
                    "l50": scaffold_l50
                },
                "gc_percent": round(gc_percent, 2) if gc_percent else None,
                "genome_coverage": genome_coverage
            },
            "biosample": {
                "accession": biosample_accession if biosample_accession != "N/A" else None,
                "description": biosample_description if biosample_description != "N/A" else None,
                "submitter": biosample_submitter if biosample_submitter != "N/A" else None,
                "attributes": biosample_attributes if biosample_attributes else {}
            },
            "assembly_metadata": {
                "quality": quality,
                "assembly_software": assembly_software if assembly_software != "N/A" else None,
                "completeness": completeness,
                "contamination": contamination
            },
            "external_links": external_links,
            "meta": {
                "source": "ncbi_datasets_api",
                "last_updated": datetime.utcnow().isoformat()
            }
        }
        
        logger.info(f"✅ Successfully fetched complete data from Datasets API for {accession}")
        return result
        
    except Exception as e:
        logger.error(f"❌ Datasets API error for {accession}: {e}\n{traceback.format_exc()}")
        return None

def format_bp(bp: int) -> str:
    """Format base pairs to human readable format"""
    if bp is None:
        return None
    if bp >= 1_000_000_000:
        return f"{bp/1_000_000_000:.2f} Gb"
    elif bp >= 1_000_000:
        return f"{bp/1_000_000:.2f} Mb"
    elif bp >= 1_000:
        return f"{bp/1_000:.2f} Kb"
    return f"{bp} bp"

def format_date(date_str: str) -> Optional[str]:
    """Format date string to consistent format"""
    if not date_str or date_str == "Unknown":
        return None
    try:
        # Handle YYYY-MM-DD format
        if len(date_str) == 10:
            return date_str
        # Handle other formats
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d')
    except:
        return date_str

# ==================== ENTREZ FALLBACK ====================
async def fetch_from_entrez(accession: str) -> Optional[Dict[str, Any]]:
    """Fallback: Fetch from Entrez esummary"""
    try:
        base_accession = accession.split('.')[0]
        
        await rate_limiter()
        handle = Entrez.esearch(db="assembly", term=f"{base_accession}[Accession]", retmax=1)
        search_result = Entrez.read(handle)
        handle.close()
        
        if not search_result.get("IdList"):
            return None
        
        assembly_id = search_result["IdList"][0]
        
        await rate_limiter()
        handle = Entrez.esummary(db="assembly", id=assembly_id, retmode="xml")
        summary_data = Entrez.read(handle, validate=False)
        handle.close()
        
        return parse_entrez_assembly_summary(summary_data, accession)
        
    except Exception as e:
        logger.error(f"❌ Entrez error for {accession}: {e}")
        return None

def parse_entrez_assembly_summary(summary_data: Any, accession: str) -> Optional[Dict[str, Any]]:
    """Parse NCBI esummary response for assembly - FIXED PARSING"""
    try:
        if "DocumentSummarySet" not in summary_data:
            return None
            
        doc_summary = summary_data["DocumentSummarySet"].get("DocumentSummary", [])
        if not doc_summary:
            return None
            
        summary = doc_summary[0]
        summary_dict = dict(summary.items()) if hasattr(summary, 'items') else {}
        
        # Basic info
        sci_name = summary_dict.get("SpeciesName", "Unknown")
        tax_id = str(summary_dict.get("Taxid", "N/A"))
        common_name = summary_dict.get("CommonName", "") or None
        assembly_name = summary_dict.get("AssemblyName", f"Assembly {accession}")
        assembly_level = summary_dict.get("AssemblyStatus", "Unknown")
        submission_date = summary_dict.get("SubmissionDate", "Unknown")
        update_date = summary_dict.get("LastUpdateDate", "Unknown")
        
        # FTP paths
        ftp_path_refseq = summary_dict.get("FtpPath_RefSeq", "")
        ftp_path_genbank = summary_dict.get("FtpPath_GenBank", "")
        
        # Parse the Meta XML - THIS IS CRITICAL
        meta_stats = parse_meta_xml(summary_dict.get("Meta", ""))
        
        # Build result
        result = {
            "database": "assembly",
            "accession": summary_dict.get("AssemblyAccession", accession),
            "organism": {
                "scientific_name": sci_name,
                "common_name": common_name,
                "tax_id": tax_id
            },
            "assembly": {
                "name": assembly_name,
                "level": assembly_level,
                "submission_date": format_date(submission_date) if submission_date != "Unknown" else None,
                "last_update": format_date(update_date) if update_date != "Unknown" else None
            },
            "statistics": {
                "genome_size_bp": meta_stats.get("total_length"),
                "genome_size_human": format_bp(meta_stats.get("total_length")),
                "contigs": {
                    "count": meta_stats.get("contig_count"),
                    "n50": meta_stats.get("contig_n50"),
                    "l50": meta_stats.get("contig_l50")
                },
                "scaffolds": {
                    "count": meta_stats.get("scaffold_count"),
                    "n50": meta_stats.get("scaffold_n50"),
                    "l50": meta_stats.get("scaffold_l50")
                },
                "gc_percent": meta_stats.get("gc_percent"),
                "genome_coverage": meta_stats.get("coverage")
            },
            "biosample": {
                "accession": summary_dict.get("BioSampleAccn") or None,
                "description": meta_stats.get("biosample_description"),
                "submitter": summary_dict.get("SubmitterOrganization") or None,
                "attributes": {}
            },
            "assembly_metadata": {
                "quality": summary_dict.get("assembly_status") or None,
                "assembly_software": meta_stats.get("assembly_software"),
                "completeness": None,
                "contamination": None
            },
            "external_links": {
                "ncbi": f"https://www.ncbi.nlm.nih.gov/datasets/genome/{accession}/",
                "assembly": f"https://www.ncbi.nlm.nih.gov/assembly/{accession}/"
            },
            "meta": {
                "source": "entrez_esummary",
                "last_updated": datetime.utcnow().isoformat()
            }
        }
        
        if ftp_path_refseq:
            result["external_links"]["refseq_ftp"] = ftp_path_refseq
        if ftp_path_genbank:
            result["external_links"]["genbank_ftp"] = ftp_path_genbank
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Entrez parsing error for {accession}: {e}\n{traceback.format_exc()}")
        return None

def parse_meta_xml(meta_xml: str) -> Dict[str, Any]:
    """
    Parse the Meta XML from NCBI Assembly esummary
    This contains all the statistics that were showing as null
    """
    stats = {}
    if not meta_xml:
        return stats
    
    try:
        # Wrap in root if needed
        if not meta_xml.strip().startswith('<'):
            return stats
            
        xml_str = f"<root>{meta_xml}</root>"
        root = ET.fromstring(xml_str)
        
        # Direct children of root
        for child in root:
            tag = child.tag.lower()
            text = child.text
            
            # Handle different field names NCBI uses
            if tag == "stat" and child.attrib:
                # Stats are often in format: <stat category="total_length">4641652</stat>
                category = child.attrib.get("category", "").lower()
                if "total" in category and "length" in category:
                    stats["total_length"] = int(text) if text and text.isdigit() else None
                elif "contig" in category and "n50" in category:
                    stats["contig_n50"] = int(text) if text and text.isdigit() else None
                elif "contig" in category and "count" in category:
                    stats["contig_count"] = int(text) if text and text.isdigit() else None
                elif "contig" in category and "l50" in category:
                    stats["contig_l50"] = int(text) if text and text.isdigit() else None
                elif "scaffold" in category and "n50" in category:
                    stats["scaffold_n50"] = int(text) if text and text.isdigit() else None
                elif "scaffold" in category and "count" in category:
                    stats["scaffold_count"] = int(text) if text and text.isdigit() else None
                elif "scaffold" in category and "l50" in category:
                    stats["scaffold_l50"] = int(text) if text and text.isdigit() else None
                elif "gc" in category:
                    stats["gc_percent"] = float(text) if text else None
                elif "coverage" in category:
                    stats["coverage"] = float(text) if text else None
            else:
                # Direct tag names
                if tag == "total-length" or tag == "totallength":
                    stats["total_length"] = int(text) if text and text.replace('.','').isdigit() else None
                elif tag == "contig-n50" or tag == "contign50":
                    stats["contig_n50"] = int(text) if text and text.isdigit() else None
                elif tag == "contig-count" or tag == "contigcount" or tag == "number-of-contigs":
                    stats["contig_count"] = int(text) if text and text.isdigit() else None
                elif tag == "contig-l50" or tag == "contigl50":
                    stats["contig_l50"] = int(text) if text and text.isdigit() else None
                elif tag == "scaffold-n50" or tag == "scaffoldn50":
                    stats["scaffold_n50"] = int(text) if text and text.isdigit() else None
                elif tag == "scaffold-count" or tag == "scaffoldcount" or tag == "number-of-scaffolds":
                    stats["scaffold_count"] = int(text) if text and text.isdigit() else None
                elif tag == "scaffold-l50" or tag == "scaffoldl50":
                    stats["scaffold_l50"] = int(text) if text and text.isdigit() else None
                elif tag == "gc-percent" or tag == "gcpercent" or tag == "gc":
                    stats["gc_percent"] = float(text) if text else None
                elif tag == "coverage" or tag == "genome-coverage":
                    stats["coverage"] = float(text) if text else None
                elif tag == "assembly-software":
                    stats["assembly_software"] = text
                elif tag == "description" and "biosample_description" not in stats:
                    stats["biosample_description"] = text
        
        # Also try to parse as text if XML parsing didn't get much
        if not stats.get("total_length"):
            text_stats = parse_meta_text(meta_xml)
            stats.update(text_stats)
        
        logger.debug(f"Parsed Meta XML stats: {stats}")
        return stats
        
    except ET.ParseError as e:
        logger.warning(f"Meta XML parse error: {e}")
        return parse_meta_text(meta_xml)
    except Exception as e:
        logger.error(f"Meta XML processing error: {e}")
        return {}

def parse_meta_text(meta_text: str) -> Dict[str, Any]:
    """Fallback: Parse meta as plain text looking for patterns"""
    stats = {}
    try:
        # Look for patterns like "Total sequence length: 4641652"
        patterns = {
            "total_length": r"(?:total.*?(?:sequence\s*)?length|genome\s*size)[:\s]+([0-9,]+)",
            "contig_count": r"(?:number\s*of\s*contigs|contig\s*count)[:\s]+([0-9,]+)",
            "contig_n50": r"contig\s*n50[:\s]+([0-9,]+)",
            "contig_l50": r"contig\s*l50[:\s]+([0-9,]+)",
            "scaffold_count": r"(?:number\s*of\s*scaffolds|scaffold\s*count)[:\s]+([0-9,]+)",
            "scaffold_n50": r"scaffold\s*n50[:\s]+([0-9,]+)",
            "scaffold_l50": r"scaffold\s*l50[:\s]+([0-9,]+)",
            "gc_percent": r"gc\s*(?:percent|%?)[:\s]+([0-9.]+)",
            "coverage": r"(?:coverage|depth)[:\s]+([0-9.]+)x?"
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, meta_text, re.IGNORECASE)
            if match:
                value = match.group(1).replace(',', '')
                try:
                    if key == "gc_percent" or key == "coverage":
                        stats[key] = float(value)
                    else:
                        stats[key] = int(value)
                except ValueError:
                    pass
        
        return stats
    except Exception as e:
        logger.error(f"Text parsing error: {e}")
        return {}

# ==================== ENA FALLBACK ====================
async def fetch_from_ena(accession: str) -> Optional[Dict[str, Any]]:
    """Fetch from ENA API as final fallback"""
    try:
        base_accession = accession.split('.')[0]
        # Try both RefSeq and GenBank accessions
        accessions_to_try = [base_accession]
        if accession.startswith("GCF_"):
            accessions_to_try.append(base_accession.replace("GCF_", "GCA_"))
        elif accession.startswith("GCA_"):
            accessions_to_try.append(base_accession.replace("GCA_", "GCF_"))
        
        for acc in accessions_to_try:
            url = f"https://www.ebi.ac.uk/ena/portal/api/filereport?accession={acc}&result=assembly&format=json"
            
            logger.info(f"🌐 Fetching from ENA: {url}")
            response = requests.get(url, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if data and isinstance(data, list) and len(data) > 0:
                    return parse_ena_response(data[0], accession)
        
        return None
        
    except Exception as e:
        logger.warning(f"❌ ENA fetch failed for {accession}: {e}")
        return None

def parse_ena_response(ena_data: Dict[str, Any], accession: str) -> Dict[str, Any]:
    """Parse ENA API response"""
    try:
        total_length = ena_data.get("total_length")
        if total_length:
            try:
                total_length = int(total_length)
            except:
                total_length = None
        
        gc_percent = ena_data.get("gc_percent")
        if gc_percent:
            try:
                gc_percent = float(gc_percent)
            except:
                gc_percent = None
        
        contig_n50 = ena_data.get("contig_n50")
        if contig_n50:
            try:
                contig_n50 = int(contig_n50)
            except:
                contig_n50 = None
        
        contig_count = ena_data.get("number_of_contigs")
        if contig_count:
            try:
                contig_count = int(contig_count)
            except:
                contig_count = None
        
        return {
            "database": "assembly",
            "accession": accession,
            "organism": {
                "scientific_name": ena_data.get("scientific_name", "Unknown"),
                "common_name": ena_data.get("common_name") or None,
                "tax_id": str(ena_data.get("tax_id", "N/A"))
            },
            "assembly": {
                "name": ena_data.get("assembly_name", f"Assembly {accession.split('.')[0]}"),
                "level": ena_data.get("assembly_level", "Unknown"),
                "submission_date": ena_data.get("first_public") or None,
                "last_update": ena_data.get("last_public") or None
            },
            "statistics": {
                "genome_size_bp": total_length,
                "genome_size_human": format_bp(total_length),
                "contigs": {
                    "count": contig_count,
                    "n50": contig_n50,
                    "l50": None
                },
                "scaffolds": {
                    "count": None,
                    "n50": None,
                    "l50": None
                },
                "gc_percent": round(gc_percent, 2) if gc_percent else None,
                "genome_coverage": None
            },
            "biosample": {
                "accession": ena_data.get("biosample_accession") or None,
                "description": None,
                "submitter": ena_data.get("study_center") or None,
                "attributes": {}
            },
            "assembly_metadata": {
                "quality": None,
                "assembly_software": ena_data.get("assembly_software") or None,
                "completeness": None,
                "contamination": None
            },
            "external_links": {
                "ncbi": f"https://www.ncbi.nlm.nih.gov/datasets/genome/{accession}/",
                "ena": f"https://www.ebi.ac.uk/ena/browser/view/{accession}"
            },
            "meta": {
                "source": "ena_api",
                "last_updated": datetime.utcnow().isoformat()
            }
        }
    except Exception as e:
        logger.error(f"❌ ENA parsing error: {e}")
        return create_minimal_metadata(accession, "ENA parse error")

# ==================== MAIN METADATA FETCHER ====================
async def fetch_assembly_metadata(accession: str) -> Dict[str, Any]:
    """
    Main entry point for fetching assembly metadata.
    Tries: 1) Cache -> 2) Datasets API -> 3) Entrez -> 4) ENA -> 5) Minimal
    """
    try:
        # Check cache first
        cached = await check_cache("assembly", accession)
        if cached:
            return cached

        logger.info(f"🔍 Fetching assembly: {accession}")
        
        # Handle UID format
        if accession.startswith('UID_'):
            uid_number = accession.replace('UID_', '')
            result = await fetch_assembly_by_uid(uid_number)
        else:
            result = await fetch_assembly_by_accession(accession)
        
        return result
            
    except Exception as e:
        logger.error(f"❌ Failed to fetch {accession}: {str(e)}")
        return create_minimal_metadata(accession, f"Fetch error: {str(e)}")

async def fetch_assembly_by_uid(uid: str) -> Dict[str, Any]:
    """Fetch assembly using NCBI UID"""
    try:
        # First get the accession from the UID
        await rate_limiter()
        handle = Entrez.esummary(db="assembly", id=uid, retmode="xml")
        summary_data = Entrez.read(handle, validate=False)
        handle.close()
        
        if "DocumentSummarySet" in summary_data:
            doc_summary = summary_data["DocumentSummarySet"].get("DocumentSummary", [])
            if doc_summary:
                doc_dict = dict(doc_summary[0].items()) if hasattr(doc_summary[0], 'items') else {}
                real_accession = doc_dict.get("AssemblyAccession", f"UID_{uid}")
                return await fetch_assembly_by_accession(real_accession)
        
        return create_minimal_metadata(f"UID_{uid}", "Could not resolve UID")
        
    except Exception as e:
        logger.error(f"UID fetch error {uid}: {e}")
        return create_minimal_metadata(f"UID_{uid}", f"UID error: {e}")

async def fetch_assembly_by_accession(accession: str) -> Dict[str, Any]:
    """
    Fetch assembly by accession (GCF_/GCA_)
    Uses multiple sources with fallback
    """
    
    # SOURCE 1: NCBI Datasets API (BEST SOURCE - has all stats)
    datasets_result = await fetch_from_datasets_api(accession)
    if datasets_result and has_meaningful_stats(datasets_result):
        logger.info(f"✅ Got complete data from Datasets API for {accession}")
        return await save_to_cache(datasets_result)
    
    # SOURCE 2: Entrez esummary (SECONDARY)
    entrez_result = await fetch_from_entrez(accession)
    if entrez_result and has_meaningful_stats(entrez_result):
        logger.info(f"✅ Got data from Entrez for {accession}")
        # Try to enhance with datasets data if we got partial
        if datasets_result:
            entrez_result = merge_results(entrez_result, datasets_result)
        return await save_to_cache(entrez_result)
    
    # If we got partial data from either source, use the better one
    if datasets_result:
        logger.info(f"⚠️ Using partial data from Datasets API for {accession}")
        return await save_to_cache(datasets_result)
    if entrez_result:
        logger.info(f"⚠️ Using partial data from Entrez for {accession}")
        return await save_to_cache(entrez_result)
    
    # SOURCE 3: ENA (FALLBACK)
    ena_result = await fetch_from_ena(accession)
    if ena_result:
        logger.info(f"✅ Got data from ENA for {accession}")
        return await save_to_cache(ena_result)
    
    # SOURCE 4: Minimal
    return create_minimal_metadata(accession, "All sources failed")

def has_meaningful_stats(metadata: Dict[str, Any]) -> bool:
    """Check if metadata has at least some meaningful statistics"""
    stats = metadata.get("statistics", {})
    genome_size = stats.get("genome_size_bp")
    contigs = stats.get("contigs", {}).get("count")
    gc = stats.get("gc_percent")
    
    # At least 2 out of 3 should be present
    present_count = sum(1 for x in [genome_size, contigs, gc] if x is not None)
    return present_count >= 2

def merge_results(primary: Dict[str, Any], secondary: Dict[str, Any]) -> Dict[str, Any]:
    """Merge two results, filling nulls from secondary into primary"""
    result = primary.copy()
    
    for key in secondary:
        if key == "statistics":
            if not result.get("statistics"):
                result["statistics"] = {}
            for stat_key, stat_value in secondary["statistics"].items():
                if isinstance(stat_value, dict):
                    if not result["statistics"].get(stat_key):
                        result["statistics"][stat_key] = {}
                    for sub_key, sub_value in stat_value.items():
                        if result["statistics"].get(stat_key, {}).get(sub_key) is None:
                            result["statistics"][stat_key][sub_key] = sub_value
                elif result["statistics"].get(stat_key) is None:
                    result["statistics"][stat_key] = stat_value
        elif key not in result or result[key] is None:
            result[key] = secondary[key]
    
    return result

def create_minimal_metadata(accession: str, reason: str) -> Dict[str, Any]:
    """Create minimal metadata when all sources fail"""
    return {
        "database": "assembly",
        "accession": accession,
        "organism": {
            "scientific_name": "Unknown",
            "common_name": None,
            "tax_id": None
        },
        "assembly": {
            "name": None,
            "level": None,
            "submission_date": None,
            "last_update": None
        },
        "statistics": {
            "genome_size_bp": None,
            "genome_size_human": None,
            "contigs": {"count": None, "n50": None, "l50": None},
            "scaffolds": {"count": None, "n50": None, "l50": None},
            "gc_percent": None,
            "genome_coverage": None
        },
        "biosample": {
            "accession": None,
            "description": None,
            "submitter": None,
            "attributes": {}
        },
        "assembly_metadata": {
            "quality": None,
            "assembly_software": None,
            "completeness": None,
            "contamination": None
        },
        "external_links": {
            "ncbi": f"https://www.ncbi.nlm.nih.gov/datasets/genome/{accession}/"
        },
        "meta": {
            "source": "minimal",
            "reason": reason,
            "last_updated": datetime.utcnow().isoformat()
        }
    }

# ==================== SEARCH ENDPOINTS ====================
@app.get("/search/")
@limiter.limit("10/minute")
async def search_ncbi(
    request: Request,
    database: str = Query(..., description="NCBI database to search"),
    query: Optional[str] = None,
    accession_ids: Optional[str] = None,
    taxid: Optional[int] = None,
    organism: Optional[str] = None,
    retmax: int = Query(20, ge=1, le=100),
):
    """Unified search endpoint for all NCBI databases"""
    try:
        if database == "assembly":
            return await search_assemblies(organism, taxid, accession_ids, retmax)
        else:
            return await search_other_databases(database, query, organism, taxid, accession_ids, retmax)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

async def search_assemblies(organism: Optional[str], taxid: Optional[int], accession_ids: Optional[str], retmax: int) -> Dict[str, Any]:
    """Search NCBI Assembly database"""
    search_terms = []
    
    if accession_ids:
        accession_list = [uid.strip() for uid in accession_ids.split(",") if uid.strip()]
        if accession_list:
            search_terms.append(f"({' OR '.join(accession_list)})[Accession]")
    
    if taxid:
        search_terms.append(f"txid{taxid}[Organism]")
    
    if organism:
        search_terms.append(f'"{organism}"[Organism]')
    
    if not search_terms:
        raise HTTPException(status_code=400, detail="Assembly search requires organism name, taxid, or accession numbers")
    
    search_query = " AND ".join(search_terms).strip()
    logger.info(f"🔍 Assembly search: {search_query}")
    
    try:
        await rate_limiter()
        
        handle = Entrez.esearch(db="assembly", term=search_query, retmax=retmax)
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
        
        metadata = []
        failed_accessions = []
        
        for uid in search_results["IdList"]:
            try:
                await rate_limiter()
                handle = Entrez.esummary(db="assembly", id=uid, retmode="xml")
                summary = Entrez.read(handle)
                handle.close()
                
                if "DocumentSummarySet" in summary and "DocumentSummary" in summary["DocumentSummarySet"]:
                    doc = summary["DocumentSummarySet"]["DocumentSummary"][0]
                    doc_dict = dict(doc.items()) if hasattr(doc, 'items') else {}
                    real_accession = doc_dict.get("AssemblyAccession", f"UID_{uid}")
                    
                    assembly_data = await fetch_assembly_metadata(real_accession)
                    metadata.append(assembly_data)
                else:
                    failed_accessions.append(f"UID_{uid}")
            except Exception as e:
                logger.error(f"Error processing assembly {uid}: {e}")
                failed_accessions.append(f"UID_{uid}")
        
        return {
            "database": "assembly",
            "query": search_query,
            "metadata": metadata,
            "failed_accessions": failed_accessions,
            "message": f"Found {len(metadata)} assembly records"
        }
        
    except Exception as e:
        logger.error(f"Assembly search error: {e}")
        raise HTTPException(status_code=500, detail=f"Assembly search failed: {str(e)}")

async def search_other_databases(
    database: str,
    query: Optional[str],
    organism: Optional[str],
    taxid: Optional[int],
    accession_ids: Optional[str],
    retmax: int
) -> Dict[str, Any]:
    """Search other NCBI databases (nucleotide, gene, taxonomy)"""
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
        await rate_limiter()
        
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
                logger.error(f"Error fetching {database} metadata for {uid}: {e}")
                failed_uids.append(uid)

        return {
            "database": database,
            "query": search_query,
            "metadata": metadata,
            "failed_uids": failed_uids,
        }
        
    except Exception as e:
        logger.error(f"Search error for {database}: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

# ==================== OTHER DATABASE FETCHERS ====================
async def fetch_nucleotide_metadata(uid: str) -> Optional[Dict[str, Any]]:
    """Fetch nucleotide record metadata"""
    try:
        cached = await check_cache("nucleotide", uid)
        if cached:
            return cached

        await rate_limiter()
        
        handle = Entrez.efetch(db="nucleotide", id=uid, rettype="gb", retmode="text")
        records = list(SeqIO.parse(handle, "genbank"))
        if not records:
            return None
        
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
        logger.error(f"Nucleotide fetch error {uid}: {e}")
        return None

async def fetch_gene_metadata(uid: str) -> Optional[Dict[str, Any]]:
    """Fetch gene record metadata"""
    try:
        cached = await check_cache("gene", uid)
        if cached:
            return cached

        await rate_limiter()
        
        handle = Entrez.esummary(db="gene", id=uid, retmode="xml")
        summary = Entrez.read(handle, validate=False)
        handle.close()

        if "DocumentSummarySet" not in summary:
            return None
            
        doc_summary = summary["DocumentSummarySet"].get("DocumentSummary", [])
        if not doc_summary:
            return None
        
        gene_data = doc_summary[0]
        gene_dict = dict(gene_data.items()) if hasattr(gene_data, 'items') else {}
        
        metadata = {
            "database": "gene",
            "accession": gene_dict.get("Name", f"GENE_{uid}"),
            "organism": gene_dict.get("Organism", "Unknown"),
            "description": gene_dict.get("Description", "Unknown"),
            "gene_id": str(uid),
            "other_aliases": gene_dict.get("OtherAliases", "N/A"),
            "chromosome": gene_dict.get("Chromosome", "N/A"),
            "map_location": gene_dict.get("MapLocation", "N/A"),
        }

        return await save_to_cache(metadata)

    except Exception as e:
        logger.error(f"Gene fetch error {uid}: {e}")
        return None

async def fetch_taxonomy_metadata(uid: str) -> Optional[Dict[str, Any]]:
    """Fetch taxonomy record metadata"""
    try:
        cached = await check_cache("taxonomy", uid)
        if cached:
            return cached

        await rate_limiter()
        
        handle = Entrez.efetch(db="taxonomy", id=uid, retmode="xml")
        tax_record = Entrez.read(handle)
        handle.close()

        if not tax_record:
            return None
        
        tax_data = tax_record[0]
        
        metadata = {
            "database": "taxonomy",
            "accession": str(uid),
            "organism": {
                "sci_name": tax_data.get("ScientificName", "Unknown"),
                "common_name": tax_data.get("CommonName", "Unknown"),
                "tax_id": str(uid)
            },
            "rank": tax_data.get("Rank", "Unknown"),
            "lineage": tax_data.get("Lineage", "Unknown"),
        }

        return await save_to_cache(metadata)

    except Exception as e:
        logger.error(f"Taxonomy fetch error {uid}: {e}")
        return None

# ==================== TEST/DEBUG ENDPOINTS ====================
@app.get("/test/{accession}")
async def test_accession(accession: str):
    """Test endpoint for debugging"""
    return await fetch_assembly_metadata(accession)

@app.get("/diagnose/{accession}")
async def diagnose(accession: str):
    """Detailed diagnostics for debugging null values"""
    results = {
        "input": accession,
        "datasets_api": None,
        "entrez": None,
        "ena": None,
        "final_result": None
    }
    
    # Test each source
    datasets = await fetch_from_datasets_api(accession)
    if datasets:
        results["datasets_api"] = {
            "success": True,
            "stats_present": {
                "genome_size": datasets.get("statistics", {}).get("genome_size_bp") is not None,
                "contig_count": datasets.get("statistics", {}).get("contigs", {}).get("count") is not None,
                "gc_percent": datasets.get("statistics", {}).get("gc_percent") is not None,
            },
            "raw_stats": datasets.get("statistics")
        }
    
    entrez = await fetch_from_entrez(accession)
    if entrez:
        results["entrez"] = {
            "success": True,
            "stats_present": {
                "genome_size": entrez.get("statistics", {}).get("genome_size_bp") is not None,
                "contig_count": entrez.get("statistics", {}).get("contigs", {}).get("count") is not None,
                "gc_percent": entrez.get("statistics", {}).get("gc_percent") is not None,
            },
            "raw_stats": entrez.get("statistics")
        }
    
    ena = await fetch_from_ena(accession)
    if ena:
        results["ena"] = {
            "success": True,
            "stats_present": {
                "genome_size": ena.get("statistics", {}).get("genome_size_bp") is not None,
                "contig_count": ena.get("statistics", {}).get("contigs", {}).get("count") is not None,
                "gc_percent": ena.get("statistics", {}).get("gc_percent") is not None,
            },
            "raw_stats": ena.get("statistics")
        }
    
    results["final_result"] = await fetch_assembly_metadata(accession)
    
    return results

@app.get("/raw-datasets/{accession}")
async def raw_datasets(accession: str):
    """Get raw response from Datasets API for debugging"""
    try:
        url = f"https://api.ncbi.nlm.nih.gov/datasets/v2alpha/genome/accession/{accession}"
        response = requests.get(url, headers={"Accept": "application/json"}, timeout=30)
        return {
            "status_code": response.status_code,
            "url": url,
            "response": response.json() if response.status_code == 200 else response.text
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "mongodb": "connected" if db else "disconnected",
        "ncbi_api_key": "configured" if Entrez.api_key else "missing"
    }

@app.get("/")
async def root():
    return {
        "message": "NCBI Metadata API is running",
        "endpoints": {
            "search": "/search/?database=assembly&organism=Escherichia%20coli",
            "test": "/test/GCF_000005845.2",
            "diagnose": "/diagnose/GCF_000005845.2",
            "raw_datasets": "/raw-datasets/GCF_000005845.2",
            "health": "/health"
        }
    }

# ==================== MAIN ====================
if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )