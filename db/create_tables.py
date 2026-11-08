from db import engine
from schema import (
    Base,
    User,
    Credentials,
    MutualFundHolding,
    MutualFundTransaction

)
import sys
import os
from dotenv import load_dotenv
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")



def create_tables():
    # Import models so they register on Base.metadata
    _ = (
        User,
        Credentials,
        MutualFundHolding,
        MutualFundTransaction
    )
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully:")
    for table in Base.metadata.sorted_tables:
        print(f"  - {table.name}")

def reset_tables():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    if len(sys.argv) > 0:
        if sys.argv[1] == 'reset':
            reset_tables()
        else:
            create_tables()
        
