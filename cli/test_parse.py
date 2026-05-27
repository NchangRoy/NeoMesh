import sys
import os
sys.path.insert(0, os.path.abspath('distributed_neo4j'))
from parser.cypher_parser import CypherParser
parser = CypherParser()
query = 'MATCH (a:User), (b:User) WHERE a.name = "Charlie from DB-2" CREATE (a)-[:FOLLOWS]->(b)'
print(parser.parse(query))
