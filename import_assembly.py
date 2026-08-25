import json
from collections import Counter

filename = "pseudomonas_all.jsonl"

organisms = Counter()
levels = Counter()

with open(filename, "r", encoding="utf-8") as f:
    for line in f:
        record = json.loads(line)

        organism = record.get("organism", {})
        assembly_info = record.get("assembly_info", {})

        organism_name = organism.get("organism_name")
        assembly_level = assembly_info.get("assembly_level")

        if organism_name:
            organisms[organism_name] += 1

        if assembly_level:
            levels[assembly_level] += 1

print("Total records:", sum(organisms.values()))

print("\nTop organisms:")
for name, count in organisms.most_common(20):
    print(count, name)

print("\nAssembly levels:")
for level, count in levels.items():
    print(count, level)