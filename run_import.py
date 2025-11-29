from neo4j import GraphDatabase
import sys

URI = "bolt://localhost:7687"
AUTH = ("neo4j", "neo4j123")
CYPHER_FILE = "reset_and_import_ontology.cypher"

def run_import():
    print(f"📂 Reading {CYPHER_FILE}...")
    with open(CYPHER_FILE, "r") as f:
        cypher_script = f.read()

    print(f"🐘 Connecting to Neo4j at {URI}...")
    try:
        with GraphDatabase.driver(URI, auth=AUTH) as driver:
            with driver.session() as session:
                print("🚀 Executing Cypher script via apoc.cypher.runMany...")
                result = session.run("CALL apoc.cypher.runMany($script, {})", script=cypher_script)
                result.consume()
                print("✅ Ontology imported successfully!")
    except Exception as e:
        print(f"❌ Error importing ontology: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_import()
