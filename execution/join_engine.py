import logging

logger = logging.getLogger(__name__)

def resolve_key_path(row: dict, key_path: str):
    """
    Resolves a property access path from a query record.
    E.g. row = {'u': {'id': 'u1'}}, key_path = 'u.id' -> returns 'u1'
    """
    parts = key_path.split('.')
    val = row
    for part in parts:
        if isinstance(val, dict) and part in val:
            val = val[part]
        else:
            return None
    return val


def hash_join(left: list[dict], right: list[dict], left_key: str, right_key: str) -> list[dict]:
    """
    Performs an in-memory hash join between two record sets.
    Maps keys to lists of rows to properly support one-to-many relations.
    """
    hashmap = {}
    
    # Build phase
    for row in left:
        val = resolve_key_path(row, left_key)
        if val is not None:
            if val not in hashmap:
                hashmap[val] = []
            hashmap[val].append(row)

    # Probe phase
    output = []
    for row in right:
        val = resolve_key_path(row, right_key)
        if val is not None and val in hashmap:
            for left_row in hashmap[val]:
                # Merge the record dicts
                output.append({**left_row, **row})

    return output
