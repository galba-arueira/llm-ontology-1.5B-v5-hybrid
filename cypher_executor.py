"""
Cypher Executor para V5 RAG System

Responsável por:
1. Carregar templates de Cypher do arquivo de configuração
2. Executar planos gerados pelo V5 Planner
3. Lidar com execução multi-step (encadeamento de resultados)
"""

import json
from neo4j import GraphDatabase

CONFIG_FILE = "v5_intents_config.json"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "neo4j123"


class CypherExecutor:
    def __init__(self, config_file=CONFIG_FILE):
        self.driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
        )
        # intent_id -> cypher_template (string)
        self.templates = self._load_templates(config_file)

    def close(self):
        self.driver.close()

    def _load_templates(self, config_file):
        """Carrega mapa de intent_id -> cypher_template"""
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
                return {
                    intent["intent_id"]: intent["cypher_template"]
                    for intent in config["intents"]
                }
        except FileNotFoundError:
            print(f"⚠️ Arquivo {config_file} não encontrado. Execute make_v5_intents.py primeiro.")
            return {}

    def execute_plan(self, plan: dict):
        """
        Executa um plano no Neo4j.

        plan = {
          "plan": [
            { "step": 1, "intent_id": "...", "value": "..." },
            ...
          ]
        }

        Retorna lista de dicts com as propriedades dos nós retornados em cada step.
        """
        if "plan" not in plan:
            return {"error": "Plano inválido"}

        results_all = []

        with self.driver.session() as session:
            for step in plan["plan"]:
                intent_id = step["intent_id"]
                value = step["value"]

                cypher_tpl = self.templates.get(intent_id)
                if not cypher_tpl:
                    print(f"   ⚠️ Nenhum template Cypher encontrado para intent_id={intent_id}")
                    continue

                # 🔍 LOG BEM VERBOSO
                print("   --- EXECUTANDO STEP ---")
                print("   Intent:", intent_id)
                print("   Cypher:", cypher_tpl)
                print("   Param value:", repr(value), "type:", type(value))

                params = {"value": str(value)}  # força string

                try:
                    neo_result = session.run(cypher_tpl, parameters=params)
                    step_rows = [record["resultado"] for record in neo_result]

                    print(f"   Registros retornados: {len(step_rows)}")

                    for record in step_rows:
                        # Se for Node, usa _properties; se vier outra coisa, tenta converter
                        if hasattr(record, "_properties"):
                            results_all.append(record._properties)
                        elif isinstance(record, dict):
                            results_all.append(record)
                        else:
                            # fallback genérico
                            try:
                                results_all.append(dict(record))
                            except Exception:
                                results_all.append({"raw": str(record)})

                except Exception as e:
                    print("   ❌ Erro no Neo4j:", e)
                    return {"error": str(e)}

        return results_all


if __name__ == "__main__":
    executor = CypherExecutor()
    if executor.templates:
        print(f"Carregados {len(executor.templates)} templates.")
    else:
        print("Nenhum template carregado.")
