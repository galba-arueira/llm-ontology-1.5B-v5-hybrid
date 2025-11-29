"""
Test Script for V5 Hybrid Planner (Dynamic)
===========================================

Testa o SemanticQueryPlanner usando a configuração real (v5_intents_config.json).
Valida classificação de intents e extração de entidades.
"""

import json
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from semantic_query_planner import get_planner

def run_tests():
    print("🧪 Testes do V5 Hybrid Planner com Sinônimos\n")
    
    planner = get_planner()
    
    # Casos de teste críticos - 20 testes variados
    test_cases = [
        # ========== TESTES DE BUSCA SIMPLES (1-hop) ==========
        {
            "query": "Buscar pessoa com CPF 12345678900",
            "expected_entity": "12345678900",
            "expected_entity_type": "TargetPerson",
            "description": "Busca simples por CPF"
        },
        {
            "query": "Localizar telefone (11) 99988-7766",
            "expected_entity": "11999887766",
            "expected_entity_type": "PhoneNumber",
            "description": "Busca simples por telefone com formatação"
        },
        {
            "query": "Buscar caso 1234",
            "expected_entity": "1234",
            "expected_entity_type": "Case",
            "description": "Busca simples por número de caso"
        },
        {
            "query": "Buscar placa veicular ABC1234",
            "expected_entity": "ABC1234",
            "expected_entity_type": "LicensePlate",
            "description": "Busca simples por placa (formato antigo)"
        },
        {
            "query": "Localizar equipamento com IMEI 123456789012345",
            "expected_entity": "123456789012345",
            "expected_entity_type": "Device",
            "description": "Busca simples por IMEI"
        },
        {
            "query": "Buscar registro de veículo com RENAVAM 12345678901",
            "expected_entity": "12345678901",
            "expected_entity_type": "VehicleRegistration",
            "description": "Busca simples por RENAVAM"
        },
        {
            "query": "Buscar veículo marca Toyota",
            "expected_entity": "Toyota",
            "expected_entity_type": "Vehicle",
            "description": "Busca simples por marca de veículo"
        },
        {
            "query": "Localizar carro ano 2020",
            "expected_entity": "2020",
            "expected_entity_type": "Vehicle",
            "description": "Busca simples por ano de veículo"
        },
        {
            "query": "Buscar carro de ano 2020",
            "expected_entity": "2020",
            "expected_entity_type": "Vehicle",
            "description": "Busca simples por ano de veículo"
        },
        
        # ========== TESTES DE BUSCA MULTI-HOP (2-hop e 3-hop) ==========
        {
            "query": "Quem é o dono do veículo de placa ABC1234?",
            "expected_entity": "ABC1234",
            "expected_path": ["TargetPerson", "Vehicle", "LicensePlate"],
            "description": "Busca composta 3-hop (dono pela placa)"
        },
        {
            "query": "Buscar item de evidência do caso 5678",
            "expected_entity": "5678",
            "expected_path": ["EvidenceItem", "Case", "TargetPerson"],
            "description": "Busca composta 2-hop (evidência por caso)"
        },
        
        # ========== TESTES DE WHATSAPP E MENSAGENS ==========
        {
            "query": "Buscar mensagens WhatsApp do telefone 21987654321",
            "expected_entity": "21987654321",
            "description": "Busca de mensagens por telefone"
        },
        
        # ========== TESTES COM VARIAÇÕES DE FORMATO ==========
        {
            "query": "Buscar CPF de 111.222.333-44",
            "expected_entity": "11122233344",
            "expected_entity_type": "TargetPerson",
            "description": "Busca por CPF com pontuação"
        },
        {
            "query": "Telefone (21) 98765-4321",
            "expected_entity": "21987654321",
            "expected_entity_type": "PhoneNumber",
            "description": "Busca por telefone com formatação completa"
        },
        {
            "query": "Placa ABC-1D23",
            "expected_entity": "ABC1D23",
            "expected_entity_type": "LicensePlate",
            "description": "Busca por placa Mercosul com hífen"
        },
        
        # ========== TESTES DE SINÔNIMOS E VARIAÇÕES ==========
        {
            "query": "Localizar investigado com CPF 55566677788",
            "expected_entity": "55566677788",
            "expected_entity_type": "TargetPerson",
            "description": "Busca usando sinônimo 'investigado' para TargetPerson"
        },
        {
            "query": "Buscar procedimento 9999",
            "expected_entity": "9999",
            "expected_entity_type": "Case",
            "description": "Busca usando sinônimo 'procedimento' para Case"
        },
        {
            "query": "Localizar celular 11912345678",
            "expected_entity": "11912345678",
            "expected_entity_type": "PhoneNumber",
            "description": "Busca usando sinônimo 'celular' para PhoneNumber"
        },
        {
            "query": "Buscar moto marca Honda",
            "expected_entity": "Honda",
            "expected_entity_type": "Vehicle",
            "description": "Busca usando sinônimo 'moto' para Vehicle"
        },
        
        # ========== TESTES DE CRIMES E PRISÕES ==========
        {
            "query": "quem foi preso por tráfico de drogas?",
            "expected_entity": "drogas",
            "description": "Busca de prisão por tipo de crime (partial match)"
        }
    ]
    
    passed = 0
    failed = 0
    
    for i, case in enumerate(test_cases, 1):
        query = case["query"]
        print(f"\n{'='*60}")
        print(f"Teste {i}: {case['description']}")
        print(f"Query: '{query}'")
        
        # Classificar intent - retorna lista de (intent, score)
        results = planner.classify_intent(query)
        
        print("  DEBUG: Top 5 intents:")
        for idx, (res_intent, res_score) in enumerate(results[:5]):
            print(f"    {idx+1}. {res_intent['intent_id']} ({res_intent['description']}) - Score: {res_score:.3f}")

        intent, score = results[0]  # Pegar o melhor resultado
        print(f"  Intent: {intent['intent_id']} (score: {score:.3f})")
        print(f"  Descrição: {intent['description']}")
        
        # Gerar plano
        result = planner.generate_plan(query)
        
        if "error" in result:
            print(f"  ❌ Erro: {result['error']}")
            failed += 1
            continue
        
        plan = result["plan"][0]
        extracted_entity = plan["value"]
        
        # Validar entidade extraída
        entity_match = (extracted_entity == case["expected_entity"])
        
        # Validar path ou entity_type
        path_match = True
        if "expected_path" in case:
            actual_path = intent.get("path_nodes", [])
            path_match = (actual_path == case["expected_path"])
            if not path_match:
                print(f"  ⚠️  Path esperado: {case['expected_path']}")
                print(f"      Path obtido:   {actual_path}")
        elif "expected_entity_type" in case:
            # Para buscas simples, verificar se é o entity_type correto
            actual_type = intent.get("entity_type")
            path_match = (actual_type == case["expected_entity_type"])
            if not path_match:
                print(f"  ⚠️  Entity type esperado: {case['expected_entity_type']}")
                print(f"      Entity type obtido:   {actual_type}")
        
        if entity_match and path_match and score > 0.5:
            print(f"  ✅ PASSOU")
            print(f"     Entidade: {extracted_entity}")
            if "path_nodes" in intent:
                print(f"     Path: {' -> '.join(intent['path_nodes'])}")
            passed += 1
        else:
            print(f"  ❌ FALHOU")
            if not entity_match:
                print(f"     Esperado: {case['expected_entity']}")
                print(f"     Obtido:   {extracted_entity}")
            if not path_match:
                print(f"     Path incorreto")
            if score <= 0.5:
                print(f"     Score muito baixo: {score:.3f}")
            failed += 1
    
    print("\n" + "="*60)
    print(f"RESULTADO FINAL: {passed}/{len(test_cases)} testes passaram")
    print(f"✅ Passou: {passed} | ❌ Falhou: {failed}")
    print("="*60)

if __name__ == "__main__":
    run_tests()
