"""
v5 RAG Chat (V5 Hybrid)
============================

Sistema de chat que integra:
1. V5 Semantic Planner (para entender intenção e extrair entidades)
2. Cypher Executor (para buscar no Neo4j)
3. Qwen-2.5-1.5B-Instruct (para formatar resposta e conversar)

Fluxo:
User Query -> Planner (Score > 0.6?)
    Sim -> Executa no Neo4j -> Contexto -> LLM -> Resposta
    Não -> LLM -> Resposta (conversa geral)
"""

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from semantic_query_planner import get_planner
from cypher_executor import CypherExecutor
import json

# Configuração
MODEL_PATH = "Qwen/Qwen2.5-1.5B-Instruct" # Modelo base, não o fine-tuned
SYSTEM_PROMPT = """Você é o assistente do sistema forense v5. 
Te enviarei 1 pergunta e 1 resposta e quero que você formate a resposta usando APENAS as informações que estão na resposta, sem adicionar informações que não estão na resposta"""

class RAGChat:
    def __init__(self):
        print("🚀 Inicializando v5 RAG System...")
        
        # 1. Planner & Executor
        self.planner = get_planner()
        self.executor = CypherExecutor()
        
        # 2. LLM
        print(f"🔄 Carregando LLM ({MODEL_PATH})...")
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_PATH,
            device_map="auto",
            torch_dtype=torch.float16
        )
        print("✅ Sistema pronto!\n")

    def generate_response(self, query, context=None):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
        
        user_content = query
        
        if context: 
            # Converte o contexto (Neo4j) em texto legível
            context_text = self._format_context_as_text(context)
            user_content = f"""
PERGUNTA: 
{query}

RESPOSTA:
{context_text}


"""
            
        messages.append({
            "role": "user", 
            "content": user_content
        })

        print(messages)

        # === A PARTIR DAQUI É QUE VOCÊ REALMENTE CHAMA O LLM ===
        text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
        
        inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=512,
                do_sample=False  # greedy: menos aleatório, mais estável para teste
            )
            
        response = self.tokenizer.decode(outputs[0], skip_special_tokens=False)
        
        # Limpa tokens do template do Qwen (genérico, não preso a placa)
        if "<|im_start|>assistant" in response:
            response = response.split("<|im_start|>assistant")[-1]
            response = response.split("<|im_end|>")[0].strip()
        elif "<|assistant|>" in response:
            response = response.split("<|assistant|>")[-1]
            response = response.split("<|end|>")[0].strip()
        
        return response
    
    def _format_context_as_text(self, context):
        """Convert Neo4j results to natural language"""
        if not context:
            return "Nenhum dado encontrado."
        
        text_parts = []
        for i, record in enumerate(context, 1):
            if not isinstance(record, dict):
                # fallback: tudo que não for dict vira string bruta
                text_parts.append(f"{i}:")
                text_parts.append(f"  - raw: {record}")
                continue

            text_parts.append(f"{i}:")
            
            # Handle nested structure (e.g., {'resultado': {...}})
            data = record
            if len(record) == 1 and isinstance(list(record.values())[0], dict):
                # Unwrap single-key dict
                data = list(record.values())[0]
            
            for key, value in data.items():
                if key in ['uri', 'localName']:
                    continue  # Skip campos técnicos
                
                # Handle list values
                if isinstance(value, list):
                    value = value[0] if len(value) == 1 else ", ".join(str(v) for v in value)
                
                # "bonitiza" o nome das chaves (genérico: funciona pra qualquer entidade)
                key_pretty = (
                    key.replace('_', ' ')
                       .replace('personFullName', 'Nome')
                       .replace('cpf', 'CPF')
                )
                text_parts.append(f"  - {key_pretty}: {value}")
        
        return "\n".join(text_parts)


    def chat_loop(self):
        print("💬 Chat iniciado. Digite 'sair' para encerrar.")
        print("-" * 50)
        
        while True:
            try:
                query = input("\n👤 Você: ").strip()
                if query.lower() in ["sair", "exit", "quit"]:
                    break
                if not query:
                    continue
                
                # 1. Analisar Intenção
                print("   Thinking...", end="\r")
                alls = self.planner.classify_intent(query)
                context = []

                best_intent, best_score = alls[0]
                print(f"   {best_intent}: {best_score}")

                if best_score > 0.55:
                    plan = self.planner.generate_plan(query)

                    if "error" not in plan:
                        results = self.executor.execute_plan(plan)

                        if isinstance(results, dict) and "error" in results:
                            print(f"   ⚠️ Erro na execução: {results['error']}")
                        elif not results:
                            print("   ⚠️ Nenhum dado encontrado no grafo.")
                            context.append({
                                "info": "Nenhum registro encontrado no banco de dados para esta consulta."
                            })
                        else:
                            print(f"   ✅ Encontrados {len(results)} registros.")
                            # results é uma lista de dicts -> flatten no contexto
                            context.extend(results)
                else:
                    # score baixo: não é consulta de grafo, deixa o LLM responder "livre"
                    pass
                
                # 2. Gerar Resposta
                response = self.generate_response(query, context)
                print(f"🤖 v5: {response}")
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"❌ Erro: {e}")

if __name__ == "__main__":
    chat = RAGChat()
    chat.chat_loop()
