"""
Gerador de Intents V5 (METADATA-DRIVEN - 100% Genérico)
==========================================================

Gera intents dinamicamente a partir de metadados na ontologia.
ZERO hardcoding de domínio específico.

Requer:
- Ontologia carregada no Neo4j via n10s
- v5core.ttl (já contém os metadados)
"""

from neo4j import GraphDatabase
import json
import re
from typing import Dict, List, Tuple, Set
from collections import deque

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "neo4j123"

MAX_DEPTH = 3
OUTPUT_FILE = "v5_intents_config.json"

IGNORED_LABELS = {
    "Resource", "Class", "Restriction", "Ontology", "Individual",
    "ObjectProperty", "SymmetricProperty", "AsymmetricProperty",
    "IrreflexiveProperty", "DatatypeProperty", "Entity",
    "NamedIndividual", "Agent", "Activity", "Communication", "SpatialThing",
}

IGNORED_PROPERTY_PREFIXES = (
    "_applyNeo4j", "_class", "_dataTypePropertyLabel", "_domainRel",
    "_handle", "_keep", "_objectPropertyLabel", "_rangeRel",
    "_relNamePropName", "_subClassOfRel", "_subPropertyOfRel",
    "owl_", "rdf_", "rdfs_", "xsd",
)

IGNORED_PROPERTIES = {
    "_applyNeo4jNaming", "_classLabel", "_classNamePropName",
    "_dataTypePropertyLabel", "_domainRel", "_handleMultival",
    "_handleRDFTypes", "_handleVocabUris", "_keepCustomDataTypes",
    "_keepLang", "_objectPropertyLabel", "_rangeRel", "_relNamePropName",
    "_subClassOfRel", "_subPropertyOfRel",
    "uri", "localName",
}

# ============================================================================
# UTILS
# ============================================================================

def camel_or_upper_to_words(s: str) -> str:
    if s.isupper():
        words = s.split("_")
    else:
        words = re.sub(r'(?<!^)(?=[A-Z])', ' ', s).split()
    return " ".join(w.lower() for w in words)

def slugify(*parts: str) -> str:
    text = "_".join(parts)
    text = text.lower()
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text

# ============================================================================
# METADATA LOADING FROM NEO4J
# ============================================================================

def get_property_metadata(driver) -> Dict[str, Dict]:
    """
    Busca metadados de todas as DatatypeProperties da ontologia.
    
    Retorna dict com:
    - normalizationType: "numeric" | "alphanumeric" | "text"
    - priority: 1 (alta) | 2 (média) | 3 (baixa)
    - examples: List[str] de padrões de exemplo
    """
    cypher = """
    MATCH (p:DatatypeProperty)
    RETURN 
        p.localName AS propName,
        p.normalizationType AS normType,
        p.propertyPriority AS priority,
        p.examplePattern AS examplePattern
    """
    
    metadata = {}
    with driver.session() as session:
        for r in session.run(cypher):
            prop_name = r["propName"]
            if not prop_name:
                continue

            # Agora os metadados vêm DIRETAMENTE da ontologia (não hardcoded!)
            norm_type = r.get("normType") or "text"
            
            # Prioridade já convertida para int no script de importação
            priority = r.get("priority") or 3
            
            # Exemplos separados por |
            example_str = r.get("examplePattern") or ""
            examples = [ex.strip() for ex in str(example_str).split("|")] if example_str else []

            metadata[prop_name] = {
                "normalizationType": norm_type,
                "priority": priority,
                "examples": examples,
            }
    
    return metadata
    
def get_class_metadata(driver) -> Dict[str, Dict]:
    """
    Busca metadados de todas as Classes da ontologia.

    Retorna dict com:
    - importantProperties: List[str] de propriedades importantes
    - compositeExamples: List[str] de padrões de exemplo compostos
    """
    cypher = """
    MATCH (c:Class)
    WHERE c.localName IS NOT NULL
    RETURN 
        c.localName AS className,
        c.hasImportantProperty AS importantProps,
        c.compositeExamplePattern AS compositePattern
    """

    metadata = {}
    with driver.session() as session:
        for r in session.run(cypher):
            class_name = r["className"]
            if not class_name:
                continue

            # ----- importantProps: pode ser string ou lista -----
            important_raw = r.get("importantProps")
            important_props: List[str] = []

            if isinstance(important_raw, list):
                for item in important_raw:
                    if not item:
                        continue
                    if isinstance(item, str):
                        important_props.extend(
                            p.strip() for p in item.split(",") if p.strip()
                        )
            elif isinstance(important_raw, str):
                important_props = [p.strip() for p in important_raw.split(",") if p.strip()]
            else:
                important_props = []

            # ----- compositePattern: pode ser string ou lista -----
            composite_raw = r.get("compositePattern")
            composite_examples: List[str] = []

            if isinstance(composite_raw, list):
                parts = [p for p in composite_raw if p]
            elif isinstance(composite_raw, str):
                parts = [composite_raw]
            else:
                parts = []

            for part in parts:
                if not isinstance(part, str):
                    continue
                composite_examples.extend(
                    ex.strip() for ex in part.split("|") if ex.strip()
                )

            metadata[class_name] = {
                "importantProperties": important_props,
                "compositeExamples": composite_examples,
            }

    return metadata
# ============================================================================
# DYNAMIC NORMALIZATION (METADATA-DRIVEN)
# ============================================================================

def make_normalized_where_clause(entity_var: str, prop: str, value_param: str, prop_metadata: Dict) -> str:
    """
    Gera cláusula WHERE com normalização baseada em metadados.
    """
    norm_type = prop_metadata.get(prop, {}).get("normalizationType", "text")
    
    if norm_type == "numeric":
        return f"apoc.text.replace({entity_var}.{prop}[0], '[^0-9]', '') = {value_param}"
    elif norm_type == "alphanumeric":
        return f"replace(replace({entity_var}.{prop}[0], '-', ''), ' ', '') = {value_param}"
    elif norm_type == "text_contains":
        return f"toLower({entity_var}.{prop}[0]) CONTAINS toLower({value_param})"
    else:
        return f"{entity_var}.{prop}[0] = {value_param}"

# ============================================================================
# NEO4J: SINÔNIMOS
# ============================================================================

def get_synonyms(driver) -> Dict[str, List[str]]:
    """Busca sinônimos PT para cada classe no Neo4j"""
    cypher = """
    MATCH (n:Resource)
    WHERE n.synonyms_pt_clean IS NOT NULL
    RETURN n.localName AS className, n.synonyms_pt_clean AS synonyms
    """
    
    synonyms_map = {}
    with driver.session() as session:
        for r in session.run(cypher):
            class_name = r["className"]
            synonyms_raw = r["synonyms"]
            
            if isinstance(synonyms_raw, str):
                synonyms_list = [s.strip() for s in synonyms_raw.split(",")]
            else:
                synonyms_list = synonyms_raw
                
            synonyms_map[class_name] = synonyms_list
            
    return synonyms_map

# ============================================================================
# NEO4J: SCHEMA
# ============================================================================

def get_schema_edges(driver) -> List[Tuple[str, str, str]]:
    cypher = """
    MATCH (a)-[r]->(b)
    WITH labels(a) AS fromLabels, type(r) AS relType, labels(b) AS toLabels
    UNWIND fromLabels AS fromLabel
    UNWIND toLabels AS toLabel
    WITH fromLabel, relType, toLabel
    WHERE NOT fromLabel IN $ignored
      AND NOT toLabel   IN $ignored
    RETURN DISTINCT fromLabel, relType, toLabel
    """
    with driver.session() as session:
        records = session.run(cypher, ignored=list(IGNORED_LABELS))
        return [(r["fromLabel"], r["relType"], r["toLabel"]) for r in records]

def build_meta_graph(edges: List[Tuple[str, str, str]]) -> Dict[str, List[Tuple[str, str]]]:
    graph: Dict[str, List[Tuple[str, str]]] = {}
    for from_label, rel_type, to_label in edges:
        if from_label in IGNORED_LABELS or to_label in IGNORED_LABELS:
            continue
        graph.setdefault(from_label, []).append((rel_type, to_label))
        graph.setdefault(to_label, []).append((rel_type, from_label))
    return graph

def shortest_paths_from(start: str, meta_graph: Dict, max_depth: int):
    paths = {}
    q = deque()
    q.append((start, [start], [], 0))
    visited = {start}
    
    while q:
        current, nodes_path, rels_path, depth = q.popleft()
        if depth >= max_depth:
            continue
        
        for rel_type, nxt in meta_graph.get(current, []):
            new_nodes = nodes_path + [nxt]
            new_rels = rels_path + [rel_type]
            
            if nxt not in paths:
                paths[nxt] = (new_nodes, new_rels)
            
            if depth + 1 < max_depth and nxt not in visited:
                visited.add(nxt)
                q.append((nxt, new_nodes, new_rels, depth + 1))
    
    paths.pop(start, None)
    return paths

def get_node_properties_by_label(driver) -> Dict[str, List[str]]:
    cypher = """
    CALL db.schema.nodeTypeProperties()
    YIELD nodeLabels, propertyName
    RETURN nodeLabels, propertyName
    """
    props_by_label = {}
    
    with driver.session() as session:
        for r in session.run(cypher):
            for label in r["nodeLabels"]:
                if label in IGNORED_LABELS:
                    continue
                prop_name = r["propertyName"]
                if not prop_name or prop_name in IGNORED_PROPERTIES:
                    continue
                if any(prop_name.startswith(pfx) for pfx in IGNORED_PROPERTY_PREFIXES):
                    continue
                
                props_by_label.setdefault(label, [])
                if prop_name not in props_by_label[label]:
                    props_by_label[label].append(prop_name)
    
    return props_by_label

def make_cypher_pattern_with_directions(
    nodes: List[str],
    rels: List[str],
    edge_set: Set[Tuple[str, str, str]],
) -> str:
    """Gera MATCH pattern com direções corretas"""
    pattern_parts = [f"(start:{nodes[0]})"]
    
    for i, rel_type in enumerate(rels):
        src_label = nodes[i]
        dst_label = nodes[i + 1]
        alias = f"n{i+1}" if i < len(rels) - 1 else "end"
        
        if (src_label, rel_type, dst_label) in edge_set:
            pattern_parts.append(f"-[:{rel_type}]->({alias}:{dst_label})")
        elif (dst_label, rel_type, src_label) in edge_set:
            pattern_parts.append(f"<-[:{rel_type}]-({alias}:{dst_label})")
        else:
            pattern_parts.append(f"-[:{rel_type}]-({alias}:{dst_label})")
    
    return "".join(pattern_parts)

# ============================================================================
# V5 INTENT GENERATION (METADATA-DRIVEN)
# ============================================================================

def generate_v5_intent_property(
    label: str, 
    prop: str, 
    intent_id: str, 
    synonyms_map: Dict,
    prop_metadata: Dict
):
    """Gera intent V5 para busca por propriedade (100% através de metadados)"""
    
    # Sinônimos ORIGINAIS (para descrição)
    label_syns_orig = synonyms_map.get(label, [camel_or_upper_to_words(label)])
    prop_syns_orig = synonyms_map.get(prop, [camel_or_upper_to_words(prop)])
    
    # Sinônimos LOWERCASE (para exemplos)
    label_syns_lower = [s.lower() for s in label_syns_orig]
    prop_syns_lower = [s.lower() for s in prop_syns_orig]
    
    category = slugify(label, "search")
    
    # Exemplos GENÉRICOS (padrão automático)
    examples = []
    for label_syn in label_syns_lower[:2]:
        for prop_syn in prop_syns_lower[:2]:
            examples.extend([
                f"Buscar {label_syn} com {prop_syn} <VALOR>",
                f"Localizar {label_syn} pelo {prop_syn} <VALOR>",
                f"Quais {label_syn} possuem {prop_syn} <VALOR>?",
            ])
    
    # Padrões curtos automáticos
    for label_syn in label_syns_lower[:1]:
        examples.extend([
            f"Buscar {label_syn} <VALOR>",
            f"{label_syn} <VALOR>",
        ])
    
    for prop_syn in prop_syns_lower[:1]:
        examples.extend([
            f"{prop_syn} <VALOR>",
        ])
    
    # METADADOS: Adicionar examples específicos da ontologia (SE EXISTIREM)
    meta_examples = prop_metadata.get(prop, {}).get("examples", [])
    for ex in meta_examples:
        examples.insert(0, ex)  # Inserir no início para terem prioridade
    
    # Cypher com normalização baseada em metadados
    where_clause = make_normalized_where_clause("n", prop, "$value", prop_metadata)
    cypher = f"MATCH (n:{label}) WHERE {where_clause} RETURN n"
    
    return {
        "intent_id": intent_id,
        "category": category,
        "description": f"Buscar {label_syns_orig[0]} por {prop_syns_orig[0]}",
        "entity_type": label,
        "property": prop,
        "examples": examples[:15],  # Limitar a 15 exemplos
        "cypher_template": cypher,
        "steps": 1
    }

def generate_v5_intent_composite(
    nodes: List[str],
    rels: List[str],
    prop: str,
    edge_set: Set,
    intent_id: str,
    synonyms_map: Dict,
    prop_metadata: Dict,
    class_metadata: Dict
):
    """Gera intent V5 para busca composta (100% através de metadados)"""
    start = nodes[0]
    end = nodes[-1]
    
    # Sinônimos ORIGINAIS
    start_syns_orig = synonyms_map.get(start, [camel_or_upper_to_words(start)])
    end_syns_orig = synonyms_map.get(end, [camel_or_upper_to_words(end)])
    prop_syns_orig = synonyms_map.get(prop, [camel_or_upper_to_words(prop)])
    
    # Sinônimos LOWERCASE
    start_syns_lower = [s.lower() for s in start_syns_orig]
    end_syns_lower = [s.lower() for s in end_syns_orig]
    prop_syns_lower = [s.lower() for s in prop_syns_orig]
    
    category = slugify(start, end, "search")
    
    # Exemplos GENÉRICOS
    examples = []
    
    for s_syn in start_syns_lower[:2]:
        for e_syn in end_syns_lower[:2]:
            for p_syn in prop_syns_lower[:1]:
                examples.append(f"Buscar {s_syn} associados a {e_syn} com {p_syn} <VALOR>")
                examples.append(f"Quais {s_syn} estão conectados a {e_syn} onde {p_syn} é <VALOR>?")
    
    # Padrão natural para 3-hop paths
    if len(nodes) == 3:
        middle_node = nodes[1]
        middle_syns_orig = synonyms_map.get(middle_node, [camel_or_upper_to_words(middle_node)])
        middle_syns_lower = [s.lower() for s in middle_syns_orig]
        
        for s_syn in start_syns_lower[:2]:
            for m_syn in middle_syns_lower[:3]:
                for p_syn in prop_syns_lower[:1]:
                    examples.append(f"Quem é o {s_syn} do {m_syn} de {p_syn} <VALOR>?")
                    examples.append(f"Buscar {s_syn} do {m_syn} com {p_syn} <VALOR>")
    
    # METADADOS: Adicionar composite examples da classe INICIAL
    # Gather composite examples from both start and end classes
    class_meta_start = class_metadata.get(start, {})
    class_meta_end = class_metadata.get(end, {})
    composite_examples = class_meta_start.get("compositeExamples", []) + class_meta_end.get("compositeExamples", [])
    for ex in composite_examples:
        # Only add if the example mentions a node in the path (simple heuristic)
        # This gives higher priority to examples like the one we added for LicensePlate.
        examples.insert(0, ex)  # High priority

    
    # Cypher com normalização
    pattern = make_cypher_pattern_with_directions(nodes, rels, edge_set)
    where_clause = make_normalized_where_clause("end", prop, "$value", prop_metadata)
    cypher = f"MATCH {pattern} WHERE {where_clause} RETURN start as resultado"
    
    max_examples = 15 if len(nodes) == 3 else 5
    
    return {
        "intent_id": intent_id,
        "category": category,
        "description": f"Buscar {start_syns_orig[0]} via {end_syns_orig[0]} por {prop_syns_orig[0]}",
        "path_nodes": nodes,
        "path_rels": rels,
        "property": prop,
        "examples": examples[:max_examples],
        "cypher_template": cypher,
        "steps": 2
    }

# ============================================================================
# MAIN
# ============================================================================

def generate_v5_config():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    try:
        print("🔄 Conectando ao Neo4j...")
        
        # 1. CARREGAR METADADOS DA ONTOLOGIA
        print("📊 Carregando metadados de propriedades...")
        prop_metadata = get_property_metadata(driver)
        print(f"   {len(prop_metadata)} propriedades com metadados")
        
        print("📊 Carregando metadados de classes...")
        class_metadata = get_class_metadata(driver)
        print(f"   {len(class_metadata)} classes com metadados")
        
        # 2. CARREGAR SINÔNIMOS
        print("📚 Buscando sinônimos PT da ontologia...")
        synonyms_map = get_synonyms(driver)
        print(f"   {len(synonyms_map)} classes com sinônimos")
        
        # 3. SCHEMA
        edges = get_schema_edges(driver)
        print(f"   Encontradas {len(edges)} arestas de schema")
        
        meta_graph = build_meta_graph(edges)
        print(f"   Labels no meta-grafo: {len(meta_graph.keys())}")
        
        props_by_label = get_node_properties_by_label(driver)
        edge_set = set(edges)
        
        intents = []
        intent_counter = 1
        
        # 4. PROPERTY INTENTS (1-step) - METADATA-DRIVEN
        print("\n📝 Gerando intents de propriedade (1-step)...")
        for label, props in props_by_label.items():
            # Ordenar propriedades por prioridade (metadados)
            props_sorted = sorted(props, key=lambda p: prop_metadata.get(p, {}).get("priority", 3))
            
            for prop in props_sorted[:2]:  # Top 2 props
                intent_id = f"intent_{intent_counter}"
                intent = generate_v5_intent_property(label, prop, intent_id, synonyms_map, prop_metadata)
                intents.append(intent)
                intent_counter += 1
                print(f"   {intent_id}: {intent['category']}")
        
        # 5. COMPOSITE INTENTS (multi-hop) - METADATA-DRIVEN
        print("\n📝 Gerando intents compostos (multi-hop)...")
        seen = set()
        for start in meta_graph.keys():
            paths_from_start = shortest_paths_from(start, meta_graph, MAX_DEPTH)
            for end_label, (nodes, rels) in paths_from_start.items():
                if end_label not in props_by_label:
                    continue
                
                # METADADOS: Selecionar propriedades importantes
                end_class_meta = class_metadata.get(end_label, {})
                important_props = end_class_meta.get("importantProperties", [])
                
                # Propriedades selecionadas: primeira + importantes (se existirem)
                end_props = props_by_label[end_label]
                selected_props = end_props[:1]  # Primeira propriedade
                
                # Adicionar importantes (se não já incluídas)
                for imp_prop in important_props:
                    if imp_prop in end_props and imp_prop not in selected_props:
                        selected_props.append(imp_prop)
                
                for prop in selected_props:
                    key = (tuple(nodes), prop)
                    if key in seen:
                        continue
                    seen.add(key)
                    
                    intent_id = f"intent_{intent_counter}"
                    intent = generate_v5_intent_composite(
                        nodes, rels, prop, edge_set, intent_id, 
                        synonyms_map, prop_metadata, class_metadata
                    )
                    intents.append(intent)
                    intent_counter += 1
                    print(f"   {intent_id}: {intent['category']}")
        
        # Salvar configuração
        config = {
            "version": "5.2-metadata",
            "generated_at": "2025-11-26",
            "total_intents": len(intents),
            "intents": intents
        }
        
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Configuração V5 (METADATA-DRIVEN) salva em {OUTPUT_FILE}")
        print(f"   Total de intents: {len(intents)}")
        print(f"   Propriedades com metadados: {len(prop_metadata)}")
        print(f"   Classes com metadados: {len(class_metadata)}")
        
        return config
        
    finally:
        driver.close()

if __name__ == "__main__":
    generate_v5_config()
