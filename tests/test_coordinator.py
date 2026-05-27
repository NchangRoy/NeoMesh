import os
import sys
import pytest
import asyncio

# Setup import path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
grandparent_dir = os.path.dirname(parent_dir)
if grandparent_dir not in sys.path:
    sys.path.insert(0, grandparent_dir)

from distributed_neo4j.parser.cypher_parser import CypherParser
from distributed_neo4j.parser.ast import QueryAST, MatchClause, WhereClause, ReturnClause, LimitClause
from distributed_neo4j.metadata.shard_manager import MetadataManager
from distributed_neo4j.planner.logical_planner import LogicalPlanner, SemanticError
from distributed_neo4j.planner.physical_planner import PhysicalPlanner
from distributed_neo4j.planner.operators import RemoteScan, HashJoin, Projection, Limit
from distributed_neo4j.execution.join_engine import hash_join, resolve_key_path
from distributed_neo4j.execution.executor import Executor

# Setup a clean metadata manager pointing to current configs directory
@pytest.fixture
def metadata_mgr():
    config_dir = os.path.join(parent_dir, "configs")
    return MetadataManager(config_dir)


def test_parser_single_shard():
    parser = CypherParser()
    q = "MATCH (u:User)-[:POSTED]->(p:Post) RETURN u,p"
    ast = parser.parse(q)
    assert isinstance(ast, QueryAST)
    assert isinstance(ast.match, MatchClause)
    assert len(ast.match.paths) == 1
    assert ast.where is None
    assert isinstance(ast.return_clause, ReturnClause)
    assert len(ast.return_clause.items) == 2


def test_parser_create_database():
    parser = CypherParser()
    q = "CREATE DATABASE myNewDB IN shard_2 WITH TABLES (Person, Animal) RELATIONS (OWNS)"
    ast = parser.parse(q)
    assert isinstance(ast, QueryAST)
    assert ast.ddl is not None
    assert ast.ddl.db_name == "myNewDB"
    assert ast.ddl.shard_name == "shard_2"
    assert "Person" in ast.ddl.tables
    assert "Animal" in ast.ddl.tables
    assert "OWNS" in ast.ddl.relations

def test_parser_cross_shard():
    parser = CypherParser()
    q = "MATCH (u:User),(o:Order) WHERE u.id = o.userId RETURN u, o LIMIT 5"
    ast = parser.parse(q)
    assert isinstance(ast, QueryAST)
    assert len(ast.match.paths) == 2
    assert isinstance(ast.where, WhereClause)
    assert isinstance(ast.limit, LimitClause)
    assert ast.limit.value == 5


def test_metadata_routing(metadata_mgr):
    assert metadata_mgr.get_table_db("User") == "social_db"
    assert metadata_mgr.get_shard_for_table("User") == "shard_1"
    
    assert metadata_mgr.get_table_db("Order") == "commerce_db"
    assert metadata_mgr.get_shard_for_table("Order") == "shard_2"

    assert metadata_mgr.get_relationship_db("POSTED") == "social_db"
    assert metadata_mgr.get_shard_for_relationship("POSTED") == "shard_1"


def test_planner_single_shard(metadata_mgr):
    parser = CypherParser()
    q = "MATCH (u:User)-[:POSTED]->(p:Post) RETURN u,p"
    ast = parser.parse(q)
    
    logical_planner = LogicalPlanner(metadata_mgr)
    logical_plan = logical_planner.plan(ast)
    
    physical_planner = PhysicalPlanner(metadata_mgr)
    physical_plan = physical_planner.plan(logical_plan, q)
    
    # Single-shard query should map to a single RemoteScan
    assert isinstance(physical_plan, RemoteScan)
    assert physical_plan.shard == "shard_1"
    assert physical_plan.query == q


def test_planner_cross_shard(metadata_mgr):
    parser = CypherParser()
    q = "MATCH (u:User),(o:Order) WHERE u.id = o.userId RETURN u,o LIMIT 5"
    ast = parser.parse(q)
    
    logical_planner = LogicalPlanner(metadata_mgr)
    logical_plan = logical_planner.plan(ast)
    
    physical_planner = PhysicalPlanner(metadata_mgr)
    physical_plan = physical_planner.plan(logical_plan, q)
    
    # Cross-shard query should have Limit -> Projection -> HashJoin -> RemoteScans
    assert isinstance(physical_plan, Limit)
    assert physical_plan.limit == 5
    
    proj = physical_plan.child
    assert isinstance(proj, Projection)
    
    join = proj.child
    assert isinstance(join, HashJoin)
    assert join.left_key == "u.id"
    assert join.right_key == "o.userId"
    
    assert isinstance(join.left, RemoteScan)
    assert join.left.shard == "shard_1"
    
    assert isinstance(join.right, RemoteScan)
    assert join.right.shard == "shard_2"


def test_hash_join():
    left = [
        {"u": {"id": "u1", "name": "Alice"}},
        {"u": {"id": "u2", "name": "Bob"}}
    ]
    right = [
        {"o": {"id": "o1", "userId": "u1", "amount": 10.0}},
        {"o": {"id": "o2", "userId": "u1", "amount": 20.0}},
        {"o": {"id": "o3", "userId": "u3", "amount": 30.0}}
    ]
    
    result = hash_join(left, right, "u.id", "o.userId")
    # Result should join u1 with o1 and o2. u3 is omitted (inner join)
    assert len(result) == 2
    assert result[0]["u"]["name"] == "Alice"
    assert result[0]["o"]["id"] == "o1"
    assert result[1]["u"]["name"] == "Alice"
    assert result[1]["o"]["id"] == "o2"


@pytest.mark.asyncio
async def test_end_to_end_mock(metadata_mgr):
    parser = CypherParser()
    q = "MATCH (u:User),(o:Order) WHERE u.id = o.userId RETURN u.name AS name, o.amount AS amt LIMIT 10"
    ast = parser.parse(q)
    
    logical_planner = LogicalPlanner(metadata_mgr)
    logical_plan = logical_planner.plan(ast)
    
    physical_planner = PhysicalPlanner(metadata_mgr)
    physical_plan = physical_planner.plan(logical_plan, q)
    
    executor = Executor(metadata_mgr, mock=True)
    try:
        results = await executor.execute(physical_plan)
        # Verify result content based on mock dataset
        assert len(results) == 3  # Alice has 2 orders, Bob has 1 order
        
        # Verify projected field names
        assert "name" in results[0]
        assert "amt" in results[0]
        
        names = [r["name"] for r in results]
        assert "Alice" in names
        assert "Bob" in names
    finally:
        executor.close()
