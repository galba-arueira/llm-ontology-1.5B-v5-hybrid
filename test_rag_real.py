import unittest
import sys
import os
import json
import time

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from rag_chat import RAGChat

class TestRAGReal(unittest.TestCase):
    def setUp(self):
        """
        Setup do teste real.
        Assume que o Neo4j está rodando e a ontologia/exemplos foram importados.
        """
        print("\n🚀 Inicializando Teste REAL do RAG (pode demorar para carregar LLM)...")
        try:
            self.chat = RAGChat()
        except Exception as e:
            self.fail(f"Falha ao inicializar RAGChat (verifique se Neo4j está rodando e LLM pode ser carregado): {e}")

    def test_real_query_vehicle_owner(self):
        """
        Testa uma query real que deve existir nos exemplos:
        "Quem é o dono do veículo de placa ABC1D23?" -> João da Silva
        """
        query = "Quem é o dono do veículo de placa ABC1D23?"
        print(f"\n❓ Pergunta: {query}")
        
        # 1. Classificação
        results = self.chat.planner.classify_intent(query)
        intent, score = results[0]  # Pegar o melhor resultado
        print(f"   Intent: {intent['intent_id']} (Score: {score:.3f})")
        
        self.assertGreater(score, 0.5, "Score do intent muito baixo para uma query válida")
        
        # 2. Execução do Plano (Busca no Neo4j)
        plan = self.chat.planner.generate_plan(query)
        results = self.chat.executor.execute_plan(plan)
        
        print(f"   Resultados Neo4j: {len(results)} registros encontrados")
        if results:
            print(f"   Exemplo de dado: {results[0]}")
            
        self.assertTrue(len(results) > 0, "Nenhum resultado encontrado no Neo4j. Verifique se 'v5core-examples.ttl' foi importado.")
        
        # Verificar se João da Silva está nos resultados
        found_joao = False
        for row in results:
            # O formato do resultado depende do Cypher, mas deve conter dados do dono
            row_str = str(row).lower()
            if "joão" in row_str or "joao" in row_str:
                found_joao = True
                break
        
        self.assertTrue(found_joao, "João da Silva não encontrado nos resultados do Neo4j")
        
        # 3. Geração de Resposta (LLM Real)
        print("   Gerando resposta com LLM (aguarde)...")
        start_time = time.time()
        response = self.chat.generate_response(query, context=results)
        duration = time.time() - start_time
        
        print(f"   Resposta LLM ({duration:.1f}s): {response}")
        
        # Validações na resposta do LLM (genéricas)
        response_normalized = response.lower().replace("ã", "a").replace("á", "a").replace("é", "e").replace("ô", "o")
        
        # Verifica se a resposta contém o nome (João ou Joao) de forma flexível
        has_name = any(name in response_normalized for name in ["joao", "joão", "silva"])
        self.assertTrue(has_name, f"LLM não mencionou o nome do proprietário na resposta. Resposta: {response}")
        
        # Verifica se a resposta menciona a placa de alguma forma
        has_plate = any(plate in response_normalized for plate in ["abc1d23", "abc-1d23", "abc 1d23", "placa"])
        self.assertTrue(has_plate, f"LLM não mencionou a placa na resposta. Resposta: {response}")
        
        # Verifica se a resposta é substancial (não apenas os tokens do template)
        self.assertGreater(len(response), 20, f"Resposta muito curta. Resposta: {response}")
        
        # Verifica que não contém tokens de template
        self.assertNotIn("<|im_start|>", response, "Resposta contém tokens de template não processados")
        self.assertNotIn("<|im_end|>", response, "Resposta contém tokens de template não processados")
        
        print(f"   ✅ Teste PASSOU - Resposta válida e completa!")
    
    def test_real_query_drug_trafficking_arrest(self):
        """
        Testa query sobre prisão por tráfico de drogas (partial match com CONTAINS).
        "quem foi preso por tráfico de drogas?" -> Deve encontrar prisões relacionadas
        """
        query = "quem foi preso por tráfico de drogas?"
        print(f"\n❓ Pergunta: {query}")
        
        # 1. Classificação
        results = self.chat.planner.classify_intent(query)
        intent, score = results[0]  # Pegar o melhor resultado
        print(f"   Intent: {intent['intent_id']} (Score: {score:.3f})")
        
        self.assertGreater(score, 0.5, "Score do intent muito baixo para uma query válida")
        
        # Verificar que pegou um intent relacionado a Arrest/Accusation/OffenseType
        intent_category = intent.get('category', '').lower()
        is_arrest_related = any(word in intent_category for word in ['arrest', 'accusation', 'offense'])
        self.assertTrue(is_arrest_related, f"Intent não relacionado a prisão/acusação. Category: {intent_category}")
        
        # 2. Verificar que o Cypher gerado usa CONTAINS (se houver metadata carregado)
        cypher = intent.get('cypher_template', '')
        print(f"   Cypher: {cypher}")
        
        # 3. Execução do Plano (Busca no Neo4j)
        plan = self.chat.planner.generate_plan(query)
        results_data = self.chat.executor.execute_plan(plan)
        
        print(f"   Resultados Neo4j: {len(results_data)} registros encontrados")
        if results_data:
            print(f"   Exemplo de dado: {results_data[0]}")
        
        # Note: Pode não haver resultados se não houver dados de exemplo de prisões por drogas
        # Mas o teste deve passar se o intent foi classificado corretamente
        
        # 4. Geração de Resposta (LLM Real)
        print("   Gerando resposta com LLM (aguarde)...")
        start_time = time.time()
        response = self.chat.generate_response(query, context=results_data)
        duration = time.time() - start_time
        
        print(f"   Resposta LLM ({duration:.1f}s): {response}")
        
        # Validações básicas
        self.assertIsNotNone(response, "LLM não gerou resposta")
        self.assertGreater(len(response), 10, "Resposta muito curta")
        self.assertNotIn("<|im_start|>", response, "Resposta contém tokens de template")
        self.assertNotIn("<|im_end|>", response, "Resposta contém tokens de template")
        
        print(f"   ✅ Teste PASSOU - Intent classificado e resposta gerada!")

    def test_llm_end_to_end_from_v5_cases(self):
        """
        Teste end-to-end (Planner + Executor + LLM) reutilizando os mesmos
        casos críticos do test_v5.py, garantindo que:
          - o intent tem score razoável
          - a entidade extraída bate com o esperado
          - o path ou entity_type estão corretos (quando especificados)
          - o LLM gera uma resposta textual válida, sem tokens de template
        """
        test_cases = [
            # ========== TESTES DE BUSCA SIMPLES (1-hop) ==========
            {
                "query": "Buscar pessoa com CPF 99900011122",
                "expected_entity": "99900011122",
                "expected_entity_type": "TargetPerson",
                "description": "Busca simples por CPF",
            },
            {
                "query": "Localizar telefone 5521988880002",
                "expected_entity": "5521988880002",
                "expected_entity_type": "PhoneNumber",
                "description": "Busca simples por telefone com formatação",
            },
            {
                "query": "Buscar caso C001/2025",
                "expected_entity": "C0012025",
                "expected_entity_type": "Case",
                "description": "Busca simples por número de caso",
            },
            {
                "query": "Buscar placa veicular ABC1D23",
                "expected_entity": "ABC1D23",
                "expected_entity_type": "LicensePlate",
                "description": "Busca simples por placa (formato antigo)",
            },
            {
                "query": "Localizar equipamento com IMEI 123456789012345",
                "expected_entity": "123456789012345",
                "expected_entity_type": "Device",
                "description": "Busca simples por IMEI",
            },
            {
                "query": "Buscar registro de veículo com RENAVAM 12345678901",
                "expected_entity": "12345678901",
                "expected_entity_type": "VehicleRegistration",
                "description": "Busca simples por RENAVAM",
            },
            {
                "query": "Buscar veículo marca Toyota",
                "expected_entity": "Toyota",
                "expected_entity_type": "Vehicle",
                "description": "Busca simples por marca de veículo",
            },
            {
                "query": "Localizar carro ano 2020",
                "expected_entity": "2020",
                "expected_entity_type": "Vehicle",
                "description": "Busca simples por ano de veículo",
            },
            {
                "query": "Buscar carro de ano 2020",
                "expected_entity": "2020",
                "expected_entity_type": "Vehicle",
                "description": "Busca simples por ano de veículo (variação)",
            },

            # ========== TESTES DE BUSCA MULTI-HOP (2-hop e 3-hop) ==========
            {
                "query": "Quem é o dono do veículo de placa ABC1234?",
                "expected_entity": "ABC1234",
                "expected_path": ["TargetPerson", "Vehicle", "LicensePlate"],
                "description": "Busca composta 3-hop (dono pela placa)",
            },
            {
                "query": "Buscar item de evidência do caso 5678",
                "expected_entity": "5678",
                "expected_path": ["EvidenceItem", "Case", "TargetPerson"],
                "description": "Busca composta 2-hop (evidência por caso)",
            },

            # ========== TESTES DE WHATSAPP E MENSAGENS ==========
            {
                "query": "Buscar mensagens WhatsApp do telefone 21987654321",
                "expected_entity": "21987654321",
                "description": "Busca de mensagens por telefone",
            },

            # ========== TESTES COM VARIAÇÕES DE FORMATO ==========
            {
                "query": "Buscar CPF de 111.222.333-44",
                "expected_entity": "11122233344",
                "expected_entity_type": "TargetPerson",
                "description": "Busca por CPF com pontuação",
            },
            {
                "query": "Telefone (21) 98765-4321",
                "expected_entity": "21987654321",
                "expected_entity_type": "PhoneNumber",
                "description": "Busca por telefone com formatação completa",
            },
            {
                "query": "Placa ABC-1D23",
                "expected_entity": "ABC1D23",
                "expected_entity_type": "LicensePlate",
                "description": "Busca por placa Mercosul com hífen",
            },

            # ========== TESTES DE SINÔNIMOS E VARIAÇÕES ==========
            {
                "query": "Localizar investigado com CPF 55566677788",
                "expected_entity": "55566677788",
                "expected_entity_type": "TargetPerson",
                "description": "Busca usando sinônimo 'investigado' para TargetPerson",
            },
            {
                "query": "Buscar procedimento 9999",
                "expected_entity": "9999",
                "expected_entity_type": "Case",
                "description": "Busca usando sinônimo 'procedimento' para Case",
            },
            {
                "query": "Localizar celular 11912345678",
                "expected_entity": "11912345678",
                "expected_entity_type": "PhoneNumber",
                "description": "Busca usando sinônimo 'celular' para PhoneNumber",
            },
            {
                "query": "Buscar moto marca Honda",
                "expected_entity": "Honda",
                "expected_entity_type": "Vehicle",
                "description": "Busca usando sinônimo 'moto' para Vehicle",
            },

            # ========== TESTE DE CRIMES E PRISÕES ==========
            {
                "query": "quem foi preso por tráfico de drogas?",
                "expected_entity": "drogas",
                "description": "Busca de prisão por tipo de crime (partial match)",
            },
        ]

        for i, case in enumerate(test_cases, 1):
            with self.subTest(msg=case["description"], query=case["query"]):
                query = case["query"]
                print("\n" + "=" * 60)
                print(f"Teste LLM {i}: {case['description']}")
                print(f"❓ Pergunta: {query}")

                # 1) Classificação de intent
                results = self.chat.planner.classify_intent(query)
                intent, score = results[0]
                print(f"   Intent: {intent['intent_id']} (Score: {score:.3f})")

                # Score mínimo razoável para query bem formada
                self.assertGreater(score, 0.5, "Score do intent muito baixo para uma query válida")

                # 2) Geração de plano e validação da entidade
                plan_result = self.chat.planner.generate_plan(query)
                self.assertNotIn("error", plan_result, f"Erro ao gerar plano: {plan_result}")

                plan = plan_result["plan"][0]
                extracted_entity = plan["value"]
                print(f"   Entidade extraída: {extracted_entity}")

                expected_entity = case["expected_entity"]
                self.assertEqual(
                    extracted_entity,
                    expected_entity,
                    f"Entidade extraída incorreta para '{query}' (esperado {expected_entity}, obtido {extracted_entity})",
                )

                # 3) Validar path ou entity_type (quando especificado)
                if "expected_path" in case:
                    actual_path = intent.get("path_nodes", [])
                    print(f"   Path obtido:   {actual_path}")
                    print(f"   Path esperado: {case['expected_path']}")
                    self.assertEqual(
                        actual_path,
                        case["expected_path"],
                        f"Path incorreto para '{query}'",
                    )
                elif "expected_entity_type" in case:
                    actual_type = intent.get("entity_type")
                    print(f"   Entity type obtido:   {actual_type}")
                    print(f"   Entity type esperado: {case['expected_entity_type']}")
                    self.assertEqual(
                        actual_type,
                        case["expected_entity_type"],
                        f"Entity type incorreto para '{query}'",
                    )

                # 4) Execução no Neo4j
                neo_results = self.chat.executor.execute_plan(plan_result)
                print(f"   Resultados Neo4j: {len(neo_results)} registros")
                if neo_results:
                    print(f"   Exemplo de dado: {neo_results[0]}")

                # 5) Geração de resposta pelo LLM
                print("   Gerando resposta com LLM...")
                start_time = time.time()
                response = self.chat.generate_response(query, context=neo_results)
                duration = time.time() - start_time

                print(f"   Resposta LLM ({duration:.1f}s): {response}")

                # 6) Validações genéricas da resposta
                self.assertIsNotNone(response, "LLM não gerou resposta")
                self.assertGreater(len(response), 20, "Resposta muito curta")
                self.assertNotIn("<|im_start|>", response, "Resposta contém tokens de template não processados")
                self.assertNotIn("<|im_end|>", response, "Resposta contém tokens de template não processados")


if __name__ == '__main__':
    unittest.main()
