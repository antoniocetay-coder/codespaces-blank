import json
import sqlite3
from config import DB_PATH

# Conecta no seu banco de dados
conn = sqlite3.connect(DB_PATH)

# Cria a tabela da malha clínica
conn.execute("""
    CREATE TABLE IF NOT EXISTS ontology_edges (
        source TEXT NOT NULL,
        relation TEXT NOT NULL,
        target TEXT NOT NULL,
        UNIQUE(source, relation, target)
    )
""")

# Lê o JSON gigante que você gerou
with open("ontology.json", "r", encoding="utf-8") as f:
    edges = json.load(f)

# Injeta as arestas (ignorando as repetidas se houver)
count = 0
for edge in edges:
    try:
        conn.execute("""
            INSERT OR IGNORE INTO ontology_edges (source, relation, target)
            VALUES (?, ?, ?)
        """, (edge['source'], edge['relation'], edge['target']))
        count += 1
    except Exception as e:
        print(f"Erro na aresta {edge}: {e}")

conn.commit()
print(f"✅ SUCESSO! {count} conexões foram injetadas no seu banco de dados.")