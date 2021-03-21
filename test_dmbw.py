import dbmw
import random

# db = dbmw.open('testdb', flag="c")

with dbmw.open("testdb", flag="c") as db:

    db['foo'] = str(random.randint(0, 9))
    # del db["foo"]
    print(db["foo"])

# db.close()