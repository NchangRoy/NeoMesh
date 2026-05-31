import os
import sys
import asyncio
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

# Add the parent directory to sys.path so we can import distributed_neo4j modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
grandparent_dir = os.path.dirname(parent_dir)
if grandparent_dir not in sys.path:
    sys.path.insert(0, grandparent_dir)

from distributed_neo4j.metadata.shard_manager import MetadataManager
from distributed_neo4j.parser.cypher_parser import CypherParser
from distributed_neo4j.planner.logical_planner import LogicalPlanner, SemanticError, LogicalCreateDatabase
from distributed_neo4j.planner.physical_planner import PhysicalPlanner
from distributed_neo4j.execution.executor import Executor

api_app = FastAPI(title="Distributed Neo4j API")

# Initialize Metadata Manager
metadata_mgr = None

@api_app.on_event("startup")
async def startup_event():
    global metadata_mgr
    metadata_mgr = MetadataManager()

# Mount static files
static_dir = os.path.join(current_dir, "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

api_app.mount("/static", StaticFiles(directory=static_dir), name="static")

@api_app.get("/", response_class=HTMLResponse)
async def read_index():
    index_path = os.path.join(static_dir, "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse(content="<h1>Index not found</h1>", status_code=404)
    with open(index_path, "r") as f:
        return HTMLResponse(content=f.read())

class QueryRequest(BaseModel):
    query: str

class ShardRequest(BaseModel):
    name: str
    host: str
    port: int
    user: str
    password: str

class DatabaseRequest(BaseModel):
    db_name: str
    shard_name: str

class NodeRequest(BaseModel):
    label: str
    db_name: str

class RelationshipRequest(BaseModel):
    type: str
    db_name: str

@api_app.get("/api/shards")
async def get_shards():
    return list(metadata_mgr.shard_manager.shard_configs.keys())

@api_app.post("/api/shards")
async def add_shard(req: ShardRequest):
    metadata_mgr.shard_manager.shard_configs[req.name] = {
        "host": req.host,
        "port": req.port,
        "user": req.user,
        "password": req.password
    }
    return {"status": "success", "message": f"Shard {req.name} added."}

@api_app.get("/api/databases")
async def get_databases():
    return metadata_mgr.shard_manager.db_to_shard

@api_app.post("/api/databases")
async def add_database(req: DatabaseRequest):
    metadata_mgr.create_database(req.db_name, req.shard_name, [], [])
    return {"status": "success", "message": f"Database {req.db_name} added to {req.shard_name}."}

@api_app.get("/api/nodes")
async def get_nodes():
    return metadata_mgr.schema_manager.label_to_db

@api_app.post("/api/nodes")
async def add_node(req: NodeRequest):
    if req.label not in metadata_mgr.schema_manager.label_to_db:
        metadata_mgr.schema_manager.label_to_db[req.label] = []
    if req.db_name not in metadata_mgr.schema_manager.label_to_db[req.label]:
        metadata_mgr.schema_manager.label_to_db[req.label].append(req.db_name)
    metadata_mgr.schema_manager._save_schema()
    return {"status": "success", "message": f"Node {req.label} added."}

@api_app.get("/api/relationships")
async def get_relationships():
    return metadata_mgr.schema_manager.relationship_to_db

@api_app.post("/api/relationships")
async def add_relationship(req: RelationshipRequest):
    if req.type not in metadata_mgr.schema_manager.relationship_to_db:
        metadata_mgr.schema_manager.relationship_to_db[req.type] = []
    if req.db_name not in metadata_mgr.schema_manager.relationship_to_db[req.type]:
        metadata_mgr.schema_manager.relationship_to_db[req.type].append(req.db_name)
    metadata_mgr.schema_manager._save_schema()
    return {"status": "success", "message": f"Relationship {req.type} added."}

@api_app.post("/api/query")
async def execute_query(request: QueryRequest):
    cypher = request.query.strip()
    mock_env = os.environ.get("NEO4J_MOCK_EXECUTION", "1")
    mock = True if mock_env == "1" else False
    
    cmd_lower = cypher.lower()
    if cmd_lower.startswith("use "):
        db_name = cypher[4:].strip()
        metadata_mgr.set_current_db(db_name)
        return {"status": "success", "results": [{"message": f"Switched to database: '{db_name}'"}]}
        
    parser = CypherParser()
    try:
        ast = parser.parse(cypher)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"Syntax Error: {e}"})

    logical_planner = LogicalPlanner(metadata_mgr)
    try:
        logical_plan = logical_planner.plan(ast)
    except SemanticError as e:
        return JSONResponse(status_code=400, content={"error": f"Semantic Error: {e}"})

    physical_planner = PhysicalPlanner(metadata_mgr)
    try:
        physical_plan = physical_planner.plan(logical_plan, cypher)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"Planning Error: {e}"})

    executor = Executor(metadata_mgr, mock=mock)
    try:
        results = await executor.execute(physical_plan)
        if isinstance(logical_plan, LogicalCreateDatabase):
            metadata_mgr.create_database(
                db_name=logical_plan.db_name,
                shard_name=logical_plan.shard_name,
                tables=logical_plan.tables,
                relations=logical_plan.relations
            )
            return {"status": "success", "results": [{"message": f"Created database {logical_plan.db_name} on {logical_plan.shard_name}"}]}
        else:
            return {"status": "success", "results": results}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Execution Error: {e}"})
    finally:
        executor.close()
