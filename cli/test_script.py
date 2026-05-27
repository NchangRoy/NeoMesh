import pexpect
import sys

child = pexpect.spawn('../venv/bin/python3 main.py --no-mock', encoding='utf-8')
child.logfile = sys.stdout

child.expect('Type \'exit\' or \'quit\' to log out.', timeout=5)
child.sendline('use fureh')
child.expect('Switched to database: \'fureh\'', timeout=5)
child.sendline('CREATE (p:Person{ name:"Alice",age:25});')
child.expect('<neo4j-BDR', timeout=5)
child.sendline('exit')
