"""
V5 Hybrid Query Planner (Dynamic)
==================================

Versão dinâmica que carrega intents do v5_intents_config.json.

Funcionalidades:
1. Carrega 300+ intents gerados do Neo4j
2. Gera embeddings para os exemplos de cada intent
3. Classifica query do usuário (Cosine Similarity)
4. Extrai entidades via Regex baseado no tipo de entidade do intent
5. Gera plano de execução (sempre 1 step, pois intents são compostos)
"""

import json
import re
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

CONFIG_FILE = "v5_intents_config.json"
MODEL_NAME = 'paraphrase-multilingual-MiniLM-L12-v2'

class SemanticQueryPlanner:
    def __init__(self, config_file=CONFIG_FILE):
        print(f"🔄 Inicializando SemanticQueryPlanner com {config_file}...")
        self.model = SentenceTransformer(MODEL_NAME)
        self.intents = self._load_intents(config_file)
        self.intent_embeddings = self._compute_embeddings()
        print(f"✅ Planner pronto! {len(self.intents)} intents carregados.")

    def _load_intents(self, config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data["intents"]
        except FileNotFoundError:
            print(f"⚠️ Arquivo {config_file} não encontrado.")
            return []

    def _compute_embeddings(self):
        """Pré-calcula embeddings para todos os exemplos de todos os intents"""
        embeddings = []
        for intent in self.intents:
            # Codifica todos os exemplos e tira a média
            ex_embeddings = self.model.encode(intent["examples"])
            avg_embedding = np.mean(ex_embeddings, axis=0)
            embeddings.append(avg_embedding)
        return np.array(embeddings)

    def classify_intent(self, query, top_k=2):
        """Retorna os top_k melhores intents para a query (por padrão, 2)."""
        query_embedding = self.model.encode([query])[0]

        # Similaridade com todos os intents
        scores = cosine_similarity([query_embedding], self.intent_embeddings)[0]

        # Garante que não peça mais do que a quantidade de intents disponível
        top_k = min(top_k, len(self.intents))

        # Índices dos maiores scores em ordem decrescente
        top_indices = np.argsort(scores)[-top_k:][::-1]

        # Monta lista de (intent, score)
        results = [
            (self.intents[i], float(scores[i]))
            for i in top_indices
        ]

        return results

    def extract_entity(self, query, intent):
        """Extrai entidade baseado no tipo esperado pelo intent"""
        # Tenta inferir o tipo de entidade pelo nome do intent ou propriedade
        # Ex: intent_vehicle_search -> vehicle
        # Ex: property="cpf" -> cpf
        
        text = query.upper()
        
        # 1. CPF
        if "cpf" in intent.get("property", "").lower() or "person" in intent.get("entity_type", "").lower():
            digits = re.sub(r'\D', '', query)
            match = re.search(r'\b(\d{11})\b', digits)
            if match: return match.group(1)

        # 2. Placa (Vehicle)
        if "vehicle" in intent.get("entity_type", "").lower() or "plate" in intent.get("property", "").lower():
            # Mercosul: ABC1D23, Antigo: ABC-1234, Mercosul com hífen: ABC-1D23
            patterns = [
                r'\b([A-Z]{3}[0-9][A-Z0-9][0-9]{2})\b', # Mercosul
                r'\b([A-Z]{3}-?[0-9]{4})\b',            # Antigo (com/sem hífen)
                r'\b([A-Z]{3}-[0-9][A-Z0-9][0-9]{2})\b' # Mercosul com hífen
            ]
            for p in patterns:
                match = re.search(p, text)
                if match: 
                    # Normaliza: remove hífens e espaços para bater com o banco (que pode estar limpo ou sujo, mas a query deve ser limpa se o Cypher limpa)
                    # O Cypher faz replace(n.plate, '-', ''), então o valor passado deve ser SEM hífen se o banco tiver hífen?
                    # Não, o Cypher: replace(DB_VAL, '-', '') = $value
                    # Se DB_VAL é "ABC-1234", vira "ABC1234".
                    # Então $value deve ser "ABC1234".
                    return match.group(1).replace('-', '').replace(' ', '')
        
        # 3. Telefone
        if "phone" in intent.get("entity_type", "").lower() or "telephone" in intent.get("entity_type", "").lower() or "whatsapp" in intent.get("category", "").lower():
            digits = re.sub(r'\D', '', query)
            match = re.search(r'\b(\d{10,11})\b', digits)
            if match: return match.group(1)

        # 4. IMEI (15 dígitos)
        if "imei" in intent.get("property", "").lower() or "device" in intent.get("entity_type", "").lower():
             digits = re.sub(r'\D', '', query)
             match = re.search(r'\b(\d{15})\b', digits)
             if match: return match.group(1)
            
        # Fallback: Tenta todos os regexes se não casou específico
        
        # Telefone (Fallback)
        digits = re.sub(r'\D', '', query)
        if re.search(r'\b(\d{10,11})\b', digits):
             return re.search(r'\b(\d{10,11})\b', digits).group(1)

        # CPF (Fallback)
        if re.search(r'\b(\d{11})\b', digits):
             return re.search(r'\b(\d{11})\b', digits).group(1)
             
        # Placa (Fallback)
        if re.search(r'\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b', text):
            val = re.search(r'\b([A-Z]{3}[0-9][A-Z0-9][0-9]{2})\b', text).group(1)
            return val.replace('-', '').replace(' ', '')
        
        # Número Genérico (Fallback final) - Para caseNumber, deviceID, IMEI, etc
        # Busca qualquer sequência de 3-15 dígitos (aumentado para cobrir IMEI)
        if re.search(r'\b(\d{3,15})\b', digits):
            return re.search(r'\b(\d{3,15})\b', digits).group(1)
            
        # Fallback Textual Genérico (para Marcas, Nomes, etc)
        # Se chegamos aqui, não achamos números nem códigos conhecidos.
        # Assume que o valor está no final da query (ex: "veículo marca Toyota")
        words = query.split()
        if words:
            # Pega a última palavra se tiver mais de 2 letras (evita "de", "da")
            last_word = words[-1]
            if len(last_word) > 2:
                # Remove pontuação final se houver
                last_word = re.sub(r'[.,!?]$', '', last_word)
                return last_word
            
        return None


    def generate_plan(self, query):
        # pega APENAS o melhor intent (lista de tuplas: (intent, score))
        top_intents = self.classify_intent(query, top_k=1)

        # usa o melhor para validar o threshold
        best_intent, best_score = top_intents[0]
        if best_score < 0.4:  # threshold de segurança
            return {"error": "Não entendi sua pergunta (score baixo)."}

        plan_steps = []
        step_number = 1

        for intent, score in top_intents:
            value = self.extract_entity(query, intent)

            if not value:
                # Se não achou a entidade para esse intent, simplesmente pula
                continue

            plan_steps.append({
                "step": step_number,
                "intent_id": intent["intent_id"],
                "description": intent["description"],
                "value": value,
                "output": "$result"
            })
            step_number += 1

        if not plan_steps:
            # Nenhum intent teve entidade extraída
            return {
                "error": (
                    f"Entendi intenções possíveis (ex: '{best_intent['description']}'), "
                    "mas não encontrei a entidade (CPF, Placa, etc.) na frase."
                )
            }

        return {"plan": plan_steps}

        
# Instância global para reuso
_planner_instance = None

def get_planner():
    global _planner_instance
    if _planner_instance is None:
        _planner_instance = SemanticQueryPlanner()
    return _planner_instance

if __name__ == "__main__":
    # Teste rápido
    planner = SemanticQueryPlanner()
    
    queries = [
        "Buscar veículo com placa HHH8I88",
        "Quem é o dono do carro ABC1234?",
        "Quais mensagens o CPF 12345678900 enviou?",
    ]
    
    for q in queries:
        print(f"\nQ: {q}")
        plan = planner.generate_plan(q)
        print(f"Plan: {json.dumps(plan, ensure_ascii=False)}")
