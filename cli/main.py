import sys
import os
import asyncio
import typer
from rich.console import Console
from rich.table import Table

# Resolve paths so imports work correctly when executed directly
current_dir = os.path.dirname(os.path.abspath(__file__))
grandparent_dir = os.path.dirname(os.path.dirname(current_dir))
if grandparent_dir not in sys.path:
    sys.path.insert(0, grandparent_dir)

from distributed_neo4j.metadata.shard_manager import MetadataManager
from distributed_neo4j.parser.cypher_parser import CypherParser
from distributed_neo4j.planner.logical_planner import LogicalPlanner, SemanticError
from distributed_neo4j.planner.physical_planner import PhysicalPlanner
from distributed_neo4j.execution.executor import Executor

app = typer.Typer(help="Distributed Neo4j Cypher Query Coordinator CLI")
console = Console()


def init_metadata_manager() -> MetadataManager:
    """Initializes and returns the Metadata Manager."""
    try:
        return MetadataManager()
    except Exception as e:
        console.print(f"[bold red]Error loading configuration metadata: {e}[/bold red]")
        raise typer.Exit(code=1)


def process_query(cypher: str, metadata_mgr: MetadataManager, show_plan: bool, mock: bool):
    """Handles the parsing, planning, and execution lifecycle of a single query."""
    # 1. Parse Query
    parser = CypherParser()
    try:
        ast = parser.parse(cypher)
    except Exception as e:
        console.print(f"[bold red]Syntax Error during Cypher parsing: {e}[/bold red]\n")
        return

    # 2. Logical Planning & Semantic Verification
    logical_planner = LogicalPlanner(metadata_mgr)
    try:
        logical_plan = logical_planner.plan(ast)
    except SemanticError as e:
        console.print(f"[bold red]Semantic Error: {e}[/bold red]\n")
        return

    # 3. Physical Planning
    physical_planner = PhysicalPlanner(metadata_mgr)
    try:
        physical_plan = physical_planner.plan(logical_plan, cypher)
    except Exception as e:
        console.print(f"[bold red]Planning Error: {e}[/bold red]\n")
        return

    if show_plan:
        from distributed_neo4j.planner.logical_planner import LogicalCreateDatabase
        console.print("[bold yellow]Logical Plan Summary:[/bold yellow]")
        if isinstance(logical_plan, LogicalCreateDatabase):
            console.print(f"  Target Shard: {logical_plan.shard_name}")
            console.print(f"  Database Name: {logical_plan.db_name}")
            console.print(f"  Tables: {logical_plan.tables}")
            console.print(f"  Relations: {logical_plan.relations}\n")
        else:
            console.print(f"  Variables: {logical_plan.variables}")
            console.print(f"  Relationships: {logical_plan.relationships}")
            console.print(f"  Filters: {logical_plan.filters}")
            console.print(f"  Limit: {logical_plan.limit}\n")
        
        console.print("[bold yellow]Physical Execution Plan Tree:[/bold yellow]")
        console.print(physical_plan)

    # 4. Execution
    executor = Executor(metadata_mgr, mock=mock)
    try:
        results = asyncio.run(executor.execute(physical_plan))
        
        from distributed_neo4j.planner.logical_planner import LogicalCreateDatabase
        if isinstance(logical_plan, LogicalCreateDatabase):
            metadata_mgr.create_database(
                db_name=logical_plan.db_name,
                shard_name=logical_plan.shard_name,
                tables=logical_plan.tables,
                relations=logical_plan.relations
            )
            console.print(f"[bold green]Successfully created database '{logical_plan.db_name}' on shard '{logical_plan.shard_name}' and updated local catalog![/bold green]\n")
        else:
            display_results(results)
            
    except Exception as e:
        console.print(f"[bold red]Runtime Execution Error: {e}[/bold red]\n")
    finally:
        executor.close()


def display_results(results: list):
    """Formats and prints the query execution results in a Rich table."""
    console.print(f"[bold green]Execution Succeeded![/bold green] (Retrieved {len(results)} rows)\n")
    if not results:
        console.print("No records returned.\n")
        return

    table = Table(show_header=True, header_style="bold magenta")
    headers = list(results[0].keys())
    for h in headers:
        table.add_column(h)

    for row in results:
        table.add_row(*[str(row.get(h, "")) for h in headers])

    console.print(table)
    console.print()  # Add an extra newline for cleaner spacing


@app.command()
def shell(
    mock: bool = typer.Option(True, "--mock/--no-mock", help="Enable/disable mock shard execution"),
    show_plan: bool = typer.Option(False, "--show-plan", help="Display query AST and execution plan tree"),
):
    """
    Launches an interactive distributed Neo4j Cypher shell.
    """
    console.print("[bold blue]Distributed Neo4j Coordinator Shell[/bold blue]")
    console.print(f"[gray]Mode: {'Mock Shard' if mock else 'Production Shard'} | Type 'exit' or 'quit' to log out.[/gray]\n")

    # Initialize Metadata Manager once for the shell session
    metadata_mgr = init_metadata_manager()

    while True:
        try:
            # Display interactive prompt
            prompt_db = f": {metadata_mgr.current_db}" if metadata_mgr.current_db else ""
            cypher = console.input(f"[bold green]<neo4j-BDR{prompt_db}>[/bold green] ").strip()
            
            # Skip empty inputs
            if not cypher:
                continue

            # Check for session exit command
            if cypher.lower() in ("exit", "quit"):
                console.print("[bold yellow]Goodbye![/bold yellow]")
                break

            # Intercept USE command
            if cypher.lower().startswith("use "):
                db_name = cypher[4:].strip()
                metadata_mgr.set_current_db(db_name)
                console.print(f"[bold green]Switched to database: '{db_name}'[/bold green]")
                continue

            # Execute the query block
            process_query(cypher, metadata_mgr, show_plan, mock)

        except (KeyboardInterrupt, EOFError):
            # Gracefully handle Ctrl+C or Ctrl+D without crashing the terminal
            console.print("\n[bold yellow]Session terminated. Goodbye![/bold yellow]")
            break


if __name__ == "__main__":
    app()