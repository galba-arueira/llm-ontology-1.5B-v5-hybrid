// 1) APAGAR TUDO (CUIDADO!)
MATCH (n)
DETACH DELETE n;

// 2) Resetar configuração do n10s (esta versão NÃO tem YIELD)
CALL n10s.graphconfig.drop();

// 3) Reconfigurar n10s para:
//    - múltiplos labels em ARRAY (necessário para preservar sinônimos)
//    - manter tags de idioma (@pt, @en)
//    - tipos RDF virarem labels
CALL n10s.graphconfig.init({
  handleVocabUris: "SHORTEN",
  handleMultival:  "ARRAY",
  keepLangTag:     true,
  handleRDFTypes:  "LABELS",
  classLabel:      "Class",
  objectPropertyLabel: "ObjectProperty",
  datatypePropertyLabel: "DatatypeProperty"
});

// 3.1 Adicionar mapeamento de prefixo para evitar ns1__
CALL n10s.nsprefixes.add("v5", "https://ontology.v5.com/v5core#");

// 4) Importar ontologia principal
// IMPORTANTE: Precisamos importar TODAS as propriedades customizadas (annotation properties)
// Para isso, usamos predicateExclusionList vazio para garantir que tudo seja importado
CALL n10s.rdf.import.fetch(
  "file:///var/lib/neo4j/import/v5core.ttl",
  "Turtle",
  { 
    shortenUrls: true,
    keepCustomDataTypes: true,
    predicateExclusionList: []
  }
);

// 4.1) Importar APENAS as annotation properties manualmente
// O n10s não importa annotation properties automaticamente, então fazemos import inline
// das triplas específicas que precisamos
CALL n10s.rdf.import.inline('
@prefix v5: <https://ontology.v5.com/v5core#> .

# Importar apenas as triplas de metadados (annotation properties)
v5:cpf v5:normalizationType "numeric" .
v5:cpf v5:propertyPriority 1 .

v5:cnpj v5:normalizationType "numeric" .
v5:cnpj v5:propertyPriority 1 .

v5:phoneNumberValue v5:normalizationType "numeric" .
v5:phoneNumberValue v5:propertyPriority 1 .

v5:deviceIMEI v5:normalizationType "numeric" .
v5:deviceIMEI v5:propertyPriority 1 .

v5:renavam v5:normalizationType "numeric" .
v5:renavam v5:propertyPriority 1 .

v5:caseNumber v5:normalizationType "numeric" .
v5:caseNumber v5:propertyPriority 1 .

v5:licensePlateNumber v5:normalizationType "alphanumeric" .
v5:licensePlateNumber v5:propertyPriority 1 .

v5:chassisNumber v5:normalizationType "alphanumeric" .
v5:chassisNumber v5:propertyPriority 2 .

v5:offenseCode v5:normalizationType "text_contains" .
v5:offenseCode v5:propertyPriority 1 .

v5:accusationDescription v5:normalizationType "text_contains" .
v5:accusationDescription v5:propertyPriority 1 .

v5:personFullName v5:propertyPriority 1 .
v5:caseName v5:propertyPriority 2 .
v5:vehicleBrand v5:propertyPriority 2 .
v5:vehicleModel v5:propertyPriority 2 .

# Class Metadata
v5:TargetPerson v5:hasImportantProperty "cpf" .
v5:LicensePlate v5:hasImportantProperty "licensePlateNumber" .
v5:Case v5:hasImportantProperty "caseNumber" .

# Example Patterns
v5:cpf v5:examplePattern "12345678900|98765432100|Localizar investigado com CPF <VALOR>" .
v5:licensePlateNumber v5:examplePattern "ABC1234|ABC-1234|XYZ-9876|placa <VALOR>" .
v5:renavam v5:examplePattern "12345678901|98765432100" .
', 'Turtle', { shortenUrls: true });

// 5) Importar exemplos (indivíduos)
CALL n10s.rdf.import.fetch(
  "file:///var/lib/neo4j/import/v5core-examples.ttl",
  "Turtle",
  { shortenUrls: true }
);


MATCH (n:Resource)
REMOVE n.synonyms_pt, n.synonyms_en, n.synonyms_pt_clean, n.synonyms_en_clean;


// 2.1 Criar localName a partir de n.uri
MATCH (n:Resource)
WHERE n.uri IS NOT NULL
SET n.localName =
  CASE
    WHEN n.uri CONTAINS '#' THEN last(split(n.uri, '#'))
    ELSE last(split(n.uri, '/'))
  END;

MATCH (n:Resource)
WHERE n.localName IS NOT NULL
RETURN n.uri, n.localName
LIMIT 20;

// 2.2 Renomear labels para remover prefixos (ns1__, v5__, owl__)
MATCH (n:Resource)
WITH n, labels(n) AS oldLabels
WITH n, oldLabels,
     [l IN oldLabels |
       CASE
         WHEN l STARTS WITH 'ns1__' THEN substring(l, size('ns1__'))  // tira só "ns1__"
         WHEN l STARTS WITH 'v5__'  THEN substring(l, size('v5__'))   // tira só "v5__"
         WHEN l STARTS WITH 'owl__' THEN substring(l, size('owl__'))  // tira só "owl__"
         ELSE l
       END
     ] AS newLabels
WHERE newLabels <> oldLabels
CALL apoc.create.setLabels(n, newLabels) YIELD node
RETURN count(node) AS nodesWithFixedLabels;

// 2.3 Renomear relacionamentos para remover prefixos (v5__, owl__)
MATCH (a)-[r]->(b)
WHERE type(r) STARTS WITH 'v5__' OR type(r) STARTS WITH 'owl__'
WITH a, b, r,
     CASE
       WHEN type(r) STARTS WITH 'v5__'  THEN substring(type(r), size('v5__'))   // tira só "v5__"
       WHEN type(r) STARTS WITH 'owl__' THEN substring(type(r), size('owl__'))  // tira só "owl__"
       ELSE type(r)
     END AS newType
CALL apoc.create.relationship(a, newType, properties(r), b) YIELD rel
DELETE r
RETURN count(rel) AS fixedRelationships;

// 2.4 Renomear propriedades para remover prefixos (v5__, ns1__, owl__)
MATCH (n:Resource)
WITH n, [k IN keys(n) WHERE k STARTS WITH 'v5__' OR k STARTS WITH 'ns1__' OR k STARTS WITH 'owl__'] AS badKeys
UNWIND badKeys AS k
WITH n, k,
     CASE
       WHEN k STARTS WITH 'v5__' THEN substring(k, size('v5__'))   // tira só o "v5__"
       WHEN k STARTS WITH 'ns1__' THEN substring(k, size('ns1__')) // tira só o "ns1__"
       WHEN k STARTS WITH 'owl__' THEN substring(k, size('owl__')) // tira só o "owl__"
       ELSE k
     END AS newKey
// evita criar propriedade com nome vazio ou nulo
WHERE newKey IS NOT NULL AND newKey <> ''
CALL apoc.create.setProperty(n, newKey, n[k]) YIELD node
WITH n, k
CALL apoc.create.removeProperties(n, [k]) YIELD node
RETURN count(*) AS fixedProperties;

// 2.5 Materializar Annotation Properties como propriedades de nó
// As annotation properties agora foram importadas mas podem estar como arrays
// Precisamos garantir que sejam valores escalares

MATCH (prop:DatatypeProperty)
WHERE prop.normalizationType IS NOT NULL
WITH prop
SET prop.normalizationType = 
  CASE 
    WHEN size(prop.normalizationType) > 0 THEN prop.normalizationType[0]
    ELSE prop.normalizationType
  END;

MATCH (prop:DatatypeProperty)
WHERE prop.propertyPriority IS NOT NULL
WITH prop
SET prop.propertyPriority = 
  CASE 
    WHEN size(prop.propertyPriority) > 0 THEN toInteger(prop.propertyPriority[0])
    ELSE toInteger(prop.propertyPriority)
  END;

MATCH (prop:DatatypeProperty)
WHERE prop.examplePattern IS NOT NULL
WITH prop
SET prop.examplePattern = 
  CASE 
    WHEN size(prop.examplePattern) > 0 THEN prop.examplePattern[0]
    ELSE prop.examplePattern
  END;

// Verificar que os metadados foram carregados
MATCH (p:DatatypeProperty)
WHERE p.normalizationType IS NOT NULL
RETURN p.localName, p.normalizationType, p.propertyPriority, p.examplePattern
LIMIT 5;


MATCH (n:Resource)
WHERE n.localName IS NOT NULL
RETURN n.uri, n.localName, labels(n)
LIMIT 20;


// LIMPAR QUALQUER COISA ANTIGA (opcional, mas ajuda)
MATCH (n:Resource)
REMOVE n.synonyms_pt, n.synonyms_en, n.synonyms_pt_clean, n.synonyms_en_clean;


MATCH (n:Resource)
WHERE n.rdfs__label IS NOT NULL

// 1) Garante que é lista (mesmo se for único, n10s array deve garantir, mas apoc previne erros)
WITH n, apoc.coll.flatten(apoc.convert.toList(n.rdfs__label)) AS labels

// 2) Converte tudo pra string e filtra
WITH n,
     [x IN labels WHERE toString(x) ENDS WITH '@pt'] AS pt_labels,
     [x IN labels WHERE toString(x) ENDS WITH '@en'] AS en_labels

// 3) Limpa as tags de idioma (@pt, @en) e salva
SET n.synonyms_pt = [x IN pt_labels | substring(toString(x), 0, size(toString(x))-3)],
    n.synonyms_en = [x IN en_labels | substring(toString(x), 0, size(toString(x))-3)],
    n.synonyms_pt_clean = [x IN pt_labels | substring(toString(x), 0, size(toString(x))-3)],
    n.synonyms_en_clean = [x IN en_labels | substring(toString(x), 0, size(toString(x))-3)];

// Verificação (separada para não limitar o update)
MATCH (n:Resource)
WHERE n.synonyms_pt_clean IS NOT NULL
RETURN n.localName, n.synonyms_pt_clean, n.synonyms_en_clean
LIMIT 20;
