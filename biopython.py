from Bio import SeqIO

record = SeqIO.read(
    "/Users/mdabdullah/NM_000546.gb",
    "genbank"
)

print("Accession:", record.id)
print("Length:", len(record.seq))
print("Description:", record.description)
print("Features:", len(record.features))

for feature in record.features:
    print(feature.type, feature.location)
