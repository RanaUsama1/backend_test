const mongoose = require("mongoose");
const { Schema } = mongoose;

const bookSchema = new mongoose.Schema(
  {
    // _id : {type: Schema.Types.ObjectId, required: true },
    annotation_details_: { type: String, required: true },
    Age: { type: String, required: true },
    Altitude: { type: String, required: true },
    "Assembly type": { type: Number, required: true },
    "Assembly level": { type: String, required: true },
    "Assembly quality": { type: String, required: true },
    "Assembly software": { type: String, required: true },
    "Broker name": { type: String, required: true },
    "Biomaterial provider": { type: String, required: true },
    "Binning parameters": { type: String, required: true },
    "Binning software": { type: String, required: true },
    "Completeness score": { type: Number, required: true },
    "Contamination score": { type: Number, required: true },
    "Collection date": { type: String, required: true },
    "Completeness software": { type: String, required: true },
    "Collected by": { type: String, required: true },
    "Collecting institution": { type: String, required: true },
    "Culture or strain id": { type: String, required: true },
    "Culture collection": { type: String, required: true },
    "Contig N50": { type: String, required: true },
    "Contig L50": { type: String, required: true },
    "Cell line": { type: String, required: true },
    "Cell Shape": { type: String, required: true },
    Date: { type: String, required: true },
    "Dev stage": { type: String, required: true },
    Disease: { type: String, required: true },
    Depth: { type: String, required: true },
    "Derived from": { type: String, required: true },
    "Estimated size": { type: String, required: true },
    Ecotype: { type: String, required: true },
    "External Id": { type: String, required: true },
    "Environmental-sample": { type: Number, required: true },
    "Env broad scale": { type: String, required: true },
    "Env local scale": { type: String, required: true },
    "Env medium": { type: String, required: true },
    "Geo loc name": { type: String, required: true },
    "Geographic location (region and locality)": {
      type: String,
      required: true,
    },
    "Geographic location (latitude)": { type: Number, required: true },
    "Geographic location (longitude)": { type: Number, required: true },
    genome_statistics_: { type: String, required: true },
    "Genome size": { type: String, required: true },
    "GC percent": { type: Number, required: true },
    Genes: { type: String, required: true, unique: true },
    GenBank: { type: String, required: true, unique: true },
    GAL: { type: String, required: true, unique: true },
    "Genome coverage": { type: Number, required: true, unique: true },
    Host: { type: String, required: true },
    "Host tissue sampled": { type: String, required: true },
    "Isol growth condt": { type: String, required: true },
    "Identifier affiliation": { type: String, required: true },
    "INSDC center alias": { type: String, required: true },
    "INSDC center name": { type: String, required: true },
    "INSDC first public": { type: Number, required: true },
    "INSDC last update": { type: String, required: true, unique: true },
    "INSDC status": { type: String, required: true },
    "Isolation source": { type: String, required: true, unique: true },
    "Investigation type": { type: String, required: true, unique: true },
    Isolate: { type: Number, required: true },
    "Lat lon": { type: String, required: true },
    "Lab host": { type: String, required: true },
    "Linked genomes": { type: String, required: true },
    "Last updated": { type: String, required: true, unique: true },
    "Locus tag prefix": { type: String, required: true },
    "Long Assembly Name": { type: String, required: true },
    "Metagenomic source": { type: String, required: true },
    Metagenomic: { type: Number, required: true },
    Models: { type: Number, required: true },
    "Mating type": { type: Number, required: true },
    "Num replicons": { type: String, required: true },
    "Number of chromosomes": { type: Number, required: true },
    "Number of organelles": { type: Number, required: true },
    "Number of scaffolds": { type: Number, required: true },
    "NCBI RefSeq assembly": { type: Schema.Types.ObjectId, required: true },
    "Number of contigs": { type: Number, required: true },
    Name: { type: String, required: true },
    "Orgmod note": { type: String, required: true },
    Propagation: { type: String, required: true },
    "Passage history": { type: String, required: true },
    "Publication date": { type: Number, required: true },
    Package: { type: String, required: true, unique: true },
    Ploidy: { type: String, required: true },
    Protocol: { type: String, required: true },
    "Project name": { type: String, required: true },
    Provider: { type: String, required: true, unique: true },
    Phenotype: { type: String, required: true, unique: true },
    "Protein coding": { type: String, required: true, unique: true },
    "Relation to type material": { type: String, required: true, unique: true },
    "Ref biomaterial": { type: String, required: true },
    "Receipt date": { type: String, required: true },
    Sex: { type: String, required: true },
    "Sequencing Technology": { type: String, required: true },
    Strain: { type: String, required: true },
    "Sample derived from": { type: String, required: true },
    "Sequencing method": { type: String, required: true },
    "Subsrc note": { type: String, required: true },
    Submitter: { type: String, required: true, unique: true },
    "Submitted to INSDC": { type: Number, required: true },
    "Submitter Id": { type: String, required: true },
    "Sample name": { type: String, required: true },
    SRA: { type: String, required: true },
    Serotype: { type: String, required: true },
    Serovar: { type: String, required: true },
    "SRA BioProject": { type: String, required: true },
    "SRA Run acc": { type: String, required: true },
    "SRA Study acc": { type: String, required: true },
    "Scientific name": { type: String, required: true },
    "Specimen id": { type: String, required: true },
    "Specimen voucher": { type: String, required: true },
    "Submission date": { type: String, required: true },
    "Scaffold N50": { type: String, required: true, unique: true },
    "Scaffold L50": { type: String, required: true, unique: true },
    "Sample type": { type: String, required: true },
    sample_details_Package: { type: String, required: true },
    sample_details_Note: { type: String, required: true },
    "sample_details_Assembly Method": { type: String, required: true },
    "sample_details_Biotic relationship": { type: String, required: true },
    "sample_details_Locus tag prefix": { type: String, required: true },
    sample_details_Cultivar: { type: String, required: true },
    "sample_details_Isolation source": { type: String, required: true },
    "sample_details_Isol growth condt": { type: String, required: true },
    sample_details_Models: { type: String, required: true },
    "sample_details_Project name": { type: String, required: true },
    "sample_details_Orgmod note": { type: String, required: true },
    "sample_details_Biomaterial provider": { type: String, required: true },
    "sample_details_Sample type": { type: String, required: true },
    "sample_details_Sample name": {
      type: String,
      required: true,
      unique: true,
    },
    "Submitted GenBank assembly": {
      type: Schema.Types.ObjectId,
      required: true,
    },
    "sample_details_Geo loc name": { type: String, required: true },
    sample_details_GenBank: { type: String, required: true },
    "sample_details_Dev stage": { type: String, required: true },
    "sample_details_Lat lon": { type: String, required: true },
    sample_details_Age: { type: Number, required: true },
    "sample_details_Subsrc note": { type: String, required: true },
    sample_details_Isolate: { type: String, required: true },
    sample_details_Ecotype: { type: String, required: true },
    "sample_details_BioSample ID": { type: String, required: true },
    sample_details_Description: { type: String, required: true },
    "sample_details_Owner name": { type: String, required: true },
    sample_details_Comment: { type: String, required: true },
    "sample_details_Collection date": { type: String, required: true },
    "sample_details_Env broad scale": { type: String, required: true },
    "sample_details_ENA first public": {
      type: String,
      required: true,
      unique: true,
    },
    "sample_details_ENA last update": { type: String, required: true },
    "sample_details_ENA-CHECKLIST": { type: String, required: true },
    "sample_details_External Id": { type: String, required: true },
    sample_details_Strain: { type: String, required: true },
    sample_details_Forma: { type: String, required: true },
    "sample_details_GOLD Stamp ID": { type: String, required: true },
    "sample_details_Organism Display Name": { type: String, required: true },
    sample_details_Genotype: { type: Number, required: true },
    sample_details_Depth: { type: String, required: true },
    sample_details_Host: { type: String, required: true },
    "sample_details_Investigation type": { type: String, required: true },
    "sample_details_Culture Collection ID": { type: String, required: true },
    Tissue: { type: String, required: true },
    "Taxonomic identity marker": { type: String, required: true },
    Temp: { type: String, required: true },
    "Type-material": { type: String, required: true },
    Tolid: { type: String, required: true },
    "Total ungapped length": { type: String, required: true },
    Variety: { type: String, required: true },
    "WGS project": { type: String, required: true },
    "Water environmental package": { type: String, required: true },
  },
  { collection: "sample_data" }
);

const Book = mongoose.model("Book", bookSchema);
module.exports = Book;
