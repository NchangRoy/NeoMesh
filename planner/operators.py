class PlanNode:
    def print_tree(self, indent="") -> str:
        raise NotImplementedError()

    def __repr__(self) -> str:
        return self.print_tree()


class RemoteScan(PlanNode):
    def __init__(self, shard: str, query: str, database: str = None):
        self.shard = shard
        self.query = query
        self.database = database

    def print_tree(self, indent="") -> str:
        db_info = f", database={self.database!r}" if self.database else ""
        return f"{indent}└── RemoteScan(shard={self.shard!r}, query={self.query!r}{db_info})\n"


class Union(PlanNode):
    def __init__(self, children: list[PlanNode]):
        self.children = children

    def print_tree(self, indent="") -> str:
        header = f"{indent}└── Union(children={len(self.children)})\n"
        child_branches = ""
        for i, child in enumerate(self.children):
            branch = child.print_tree(indent + "    ")
            if i < len(self.children) - 1:
                branch = branch.replace(indent + "    └──", indent + "    ├──", 1)
            child_branches += branch
        return header + child_branches


class HashJoin(PlanNode):
    def __init__(self, left: PlanNode, right: PlanNode, left_key: str, right_key: str):
        self.left = left
        self.right = right
        self.left_key = left_key  # e.g., 'u.id'
        self.right_key = right_key  # e.g., 'o.userId'

    def print_tree(self, indent="") -> str:
        header = f"{indent}└── HashJoin(left_key={self.left_key!r}, right_key={self.right_key!r})\n"
        left_branch = self.left.print_tree(indent + "    ")
        right_branch = self.right.print_tree(indent + "    ")
        # Adjust symbols slightly for nicer nesting
        left_branch = left_branch.replace(indent + "    └──", indent + "    ├──", 1)
        return header + left_branch + right_branch


class Projection(PlanNode):
    def __init__(self, child: PlanNode, items: list):
        self.child = child
        self.items = items  # List of ReturnItem AST elements or strings

    def print_tree(self, indent="") -> str:
        header = f"{indent}└── Projection(items={self.items!r})\n"
        child_branch = self.child.print_tree(indent + "    ")
        return header + child_branch


class Limit(PlanNode):
    def __init__(self, child: PlanNode, limit: int):
        self.child = child
        self.limit = limit

    def print_tree(self, indent="") -> str:
        header = f"{indent}└── Limit(limit={self.limit})\n"
        child_branch = self.child.print_tree(indent + "    ")
        return header + child_branch
