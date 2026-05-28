from neo4j import GraphDatabase

for pwd in ["password123", "password", "neo4j", "admin", "1234", ""]:
    try:
        driver = GraphDatabase.driver("bolt://192.168.50.64:7687", auth=("neo4j", pwd))
        driver.verify_connectivity()
        print(f"Success with '{pwd}'")
        break
    except Exception as e:
        if "Authentication" in str(e) or "Unauthorized" in str(e):
            print(f"Failed with '{pwd}'")
        else:
            print(f"Other error with '{pwd}': {e}")
